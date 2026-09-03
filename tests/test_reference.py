#!/usr/bin/env python3
"""Differential test: the streaming reference against a brute-force oracle.

The reference is the definition of a correct answer, so it is the one thing in
the repository that cannot be checked by the grader.  It is checked here
instead, against an implementation written to be obviously right rather than
bounded: group every event by user, split each user's events on idle gaps, then
sort the resulting sessions into the order the specification requires.

If these two ever disagree, the environment is grading the wrong answer.
"""

import io
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "grader"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "task"))

import reference   # noqa: E402
import generate    # noqa: E402

IDLE_MS = reference.IDLE_MS


def oracle(events):
    """Obviously-correct, unbounded-memory sessionization."""
    by_user = {}
    for i, ev in enumerate(events):
        by_user.setdefault(ev["user"], []).append((i, ev))

    sessions = []
    for user, evs in by_user.items():
        cur = None
        for _, ev in evs:
            if cur is not None and ev["ts"] - cur["last"] > IDLE_MS:
                sessions.append(cur)
                cur = None
            if cur is None:
                cur = {"user": user, "start": ev["ts"], "last": ev["ts"],
                       "n": 0, "bytes": 0, "paths": set()}
            cur["last"] = ev["ts"]
            cur["n"] += 1
            cur["bytes"] += ev["bytes"]
            cur["paths"].add(ev["path"])
        if cur is not None:
            sessions.append(cur)

    # A session becomes closeable at the first event whose ts exceeds
    # last + IDLE_MS; sessions never closed during the stream close at EOF.
    ts_list = [ev["ts"] for ev in events]

    def close_index(session):
        target = session["last"] + IDLE_MS
        for i, ts in enumerate(ts_list):
            if ts > target:
                return i
        return len(ts_list)  # closed by end-of-stream

    sessions.sort(key=lambda s: (close_index(s), s["last"], s["user"]))
    return [{
        "user": s["user"], "start_ts": s["start"], "end_ts": s["last"],
        "events": s["n"], "bytes": s["bytes"], "paths": len(s["paths"]),
    } for s in sessions]


def streaming(events):
    buf = io.StringIO()
    inp = io.StringIO("".join(json.dumps(e) + "\n" for e in events))
    reference.sessionize(inp, buf)
    return [json.loads(l) for l in buf.getvalue().splitlines()]


def random_events(rng, n):
    """Small, adversarial streams: heavy ties, few users, gaps around IDLE_MS."""
    events, ts = [], 1_700_000_000_000
    users = ["u%d" % i for i in range(rng.randint(1, 6))]
    for _ in range(n):
        # Deliberately straddle the idle boundary in both directions.
        ts += rng.choice((0, 0, 1, 5, IDLE_MS - 1, IDLE_MS, IDLE_MS + 1,
                          IDLE_MS * 2))
        events.append({
            "ts": ts,
            "user": rng.choice(users),
            "path": rng.choice(("/a", "/b", "/c")),
            "bytes": rng.randrange(1, 1000),
        })
    return events


def main():
    rng = random.Random(1)
    failures = 0

    for trial in range(3000):
        events = random_events(rng, rng.randint(0, 40))
        got, want = streaming(events), oracle(events)
        if got != want:
            failures += 1
            if failures <= 2:
                sys.stderr.write("FAIL trial %d\n  events=%s\n  got =%s\n  want=%s\n"
                                 % (trial, json.dumps(events), json.dumps(got),
                                    json.dumps(want)))

    # Also exercise the real generator's distribution, not just the adversarial one.
    for seed in range(5):
        buf = io.StringIO()
        generate.generate(seed, 4000, 25, 0.15, 0.22, buf)
        events = [json.loads(l) for l in buf.getvalue().splitlines()]
        if streaming(events) != oracle(events):
            failures += 1
            sys.stderr.write("FAIL generator seed %d\n" % seed)

    if failures:
        sys.stderr.write("%d differential failures\n" % failures)
        return 1
    sys.stdout.write("ok: 3005 instances, streaming == oracle\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
