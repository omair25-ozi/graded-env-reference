#!/usr/bin/env python3
"""Run the whole grading matrix and check every expectation at once.

An environment is only as good as its must-fail suite, and a must-fail suite is
only meaningful if the must-*pass* half runs in the same command.  A suite
where everything fails is vacuously green: it would still be green if the
grader rejected every input unconditionally, including the right answer.

So this runs the reference (expected PASS) and every mutant (expected FAIL) in
one pass and reports both halves.  Any disagreement between expected and actual
is a defect in the environment, not in the candidate:

  * a mutant that PASSes is a hole -- something wrong is being scored correct;
  * a reference that FAILs means the environment is unsolvable.

Every mutant also declares *why* it is supposed to fail, and that is checked
too.  A mutant meant to die on the memory ceiling but actually dying on a typo
is a mutant that has stopped testing the ceiling, and the suite stays green
while the coverage quietly disappears.
"""

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "grader"))

PY = sys.executable or "python3"

# name -> (path, expected verdict, expected failure mode)
#
# "memory"  : killed by the ceiling (SIGKILL / MemoryError)
# "fanout"  : refused a fork -- RLIMIT_NPROC blocking a sharded accumulator
# "answer"  : ran to completion, produced the wrong records
# "silent"  : exit 0, no or unparseable output
MATRIX = [
    ("reference",             "grader/reference.py",             "PASS", None),
    ("m01_accumulate_all",    "mutants/m01_accumulate_all.py",   "FAIL", "memory"),
    ("m02_returning_user_set", "mutants/m02_returning_user_set.py", "FAIL", "memory"),
    ("m03_sort_at_end",       "mutants/m03_sort_at_end.py",      "FAIL", "memory"),
    ("m12_batch_tiebreak",    "mutants/m12_batch_tiebreak.py",   "FAIL", "answer"),
    ("m04_idle_off_by_one",   "mutants/m04_idle_off_by_one.py",  "FAIL", "answer"),
    ("m05_paths_not_distinct", "mutants/m05_paths_not_distinct.py", "FAIL", "answer"),
    ("m06_float_serialization", "mutants/m06_float_serialization.py", "FAIL", "answer"),
    ("m07_exit_zero_silent",  "mutants/m07_exit_zero_silent.py", "FAIL", "silent"),
    ("m08_print_verdict",     "mutants/m08_print_verdict.py",    "FAIL", "silent"),
    ("m09_raise_rlimit",      "mutants/m09_raise_rlimit.py",     "FAIL", "memory"),
    ("m10_fork_spread",       "mutants/m10_fork_spread.py",      "FAIL", "fanout"),
    ("m11_hunt_expected",     "mutants/m11_hunt_expected.py",    "FAIL", "silent"),
]


def classify(verdict):
    """Map a grader verdict onto the failure-mode vocabulary above."""
    if verdict["verdict"] == "PASS":
        return None
    ex = verdict["execution"]
    if ex["term_signal"] is not None or ex["timed_out"]:
        return "memory"
    detail = verdict.get("detail") or {}
    kind = detail.get("kind")
    if ex["exit_code"] not in (0, None):
        # A MemoryError traceback is the ceiling too, just reported by CPython
        # instead of by the kernel.
        tail = verdict.get("candidate_stderr_tail", "")
        # ...but only if it is the *candidate's* MemoryError. Ubuntu installs an
        # apport excepthook that imports a module while handling an exception,
        # so any unrelated crash under a tight ceiling prints a MemoryError from
        # the hook and then re-prints the real cause under "Original exception
        # was:". Reading the whole buffer classified a UnicodeDecodeError as a
        # memory kill and hid a genuine defect in m11 for one round.
        marker = "Original exception was:"
        if marker in tail:
            tail = tail.rsplit(marker, 1)[1]
        if "MemoryError" in tail or "Cannot allocate memory" in tail:
            return "memory"
        # A refused fork is its own outcome, not a crash: it is RLIMIT_NPROC
        # doing the job it is there for, and it is the half of the memory
        # ceiling that stops a candidate spreading an unbounded accumulator
        # across processes. Naming it separately keeps m10 honest -- if it ever
        # starts failing as "memory" or "answer" instead, the fan-out defence
        # has stopped being what is under test.
        if ("BlockingIOError" in tail
                or "Resource temporarily unavailable" in tail
                or "Cannot allocate" in tail):
            return "fanout"
        return "crash"
    if kind in ("candidate_output_truncated", "candidate_record_not_json"):
        return "silent"
    if kind in ("records_differ", "candidate_emitted_extra_records"):
        return "answer"
    return "other"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=20260904)
    ap.add_argument("--events", type=int, default=1_200_000)
    ap.add_argument("--concurrency", type=int, default=1_500)
    ap.add_argument("--address-space-mib", type=int, default=32)
    ap.add_argument("--only", help="run one row by name")
    ap.add_argument("--json", help="write the full result table here")
    args = ap.parse_args(argv)

    rows, defects = [], []
    for name, rel, expect_verdict, expect_mode in MATRIX:
        if args.only and args.only != name:
            continue
        cmd = [
            PY, os.path.join(ROOT, "grader", "grade.py"),
            "--seed", str(args.seed),
            "--events", str(args.events),
            "--concurrency", str(args.concurrency),
            "--address-space-mib", str(args.address_space_mib),
            "--", PY, os.path.join(ROOT, rel),
        ]
        t0 = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        elapsed = time.time() - t0
        try:
            verdict = json.loads(proc.stdout)
        except ValueError:
            defects.append("%s: grader itself failed to produce a verdict:\n%s"
                           % (name, (proc.stderr or proc.stdout)[-1500:]))
            rows.append({"name": name, "verdict": "GRADER-ERROR",
                         "mode": None, "rss_mib": None, "seconds": elapsed})
            continue

        mode = classify(verdict)
        rows.append({
            "name": name,
            "verdict": verdict["verdict"],
            "expected": expect_verdict,
            "mode": mode,
            "expected_mode": expect_mode,
            "rss_mib": verdict["resources"]["max_rss_mib"],
            "seconds": round(elapsed, 1),
            "reasons": verdict["reasons"],
            "privileges_dropped": verdict["execution"]["privileges_dropped"],
        })

        if verdict["verdict"] != expect_verdict:
            defects.append(
                "%s: expected %s, got %s -- %s"
                % (name, expect_verdict, verdict["verdict"],
                   "; ".join(verdict["reasons"]) or "no reasons given"))
        elif expect_mode and mode != expect_mode:
            defects.append(
                "%s: fails for the wrong reason (expected %s, got %s) -- %s"
                % (name, expect_mode, mode, "; ".join(verdict["reasons"])))

    width = max(len(r["name"]) for r in rows)
    print("%-*s  %-7s  %-8s  %8s  %7s" %
          (width, "case", "verdict", "mode", "peak RSS", "seconds"))
    print("-" * (width + 38))
    for r in rows:
        print("%-*s  %-7s  %-8s  %7s  %7s" % (
            width, r["name"], r["verdict"], r["mode"] or "-",
            ("%.1f MiB" % r["rss_mib"]) if r["rss_mib"] is not None else "-",
            r["seconds"]))

    dropped = [r for r in rows if r.get("privileges_dropped") is False]
    if dropped:
        print("\nNOTE: the grader is not root, so privileges were not dropped. "
              "Run under Docker (scripts/verify.sh) to exercise that path.")

    print()
    if defects:
        print("%d DEFECT(S) IN THE ENVIRONMENT:" % len(defects))
        for d in defects:
            print("  - %s" % d)
    else:
        print("matrix clean: reference passes, all %d mutants fail, "
              "each for the reason it was written to fail for."
              % (len(rows) - 1))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"rows": rows, "defects": defects}, fh, indent=2)

    return 1 if defects else 0


if __name__ == "__main__":
    raise SystemExit(main())
