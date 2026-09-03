#!/usr/bin/env python3
"""MUST FAIL (forged pass, attacking the ceiling itself).

Tries to lift the memory ceiling before doing the unbounded thing:

  1. raise ``RLIMIT_AS`` back to infinity,
  2. failing that, raise the soft limit to the hard limit,
  3. failing that, run unbounded anyway and hope the ceiling was decorative.

Step 2 is the one that matters.  A harness that sets only the soft limit --
which is the common mistake, because setting the soft limit is what every
example in the documentation shows -- is defeated here in a single call, with
no privileges required.  The reason ``sandbox.py`` sets soft == hard is
precisely this mutant.

It reports which step succeeded on stderr, so a run that *does* fail still says
whether it failed because the ceiling held or because the candidate crashed for
some unrelated reason.
"""
import json
import resource
import sys

soft, hard = resource.getrlimit(resource.RLIMIT_AS)
attempts = {"initial_soft": soft, "initial_hard": hard}

try:
    resource.setrlimit(resource.RLIMIT_AS,
                       (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
    attempts["raise_to_infinity"] = "succeeded"
except (ValueError, OSError) as exc:
    attempts["raise_to_infinity"] = "refused: %s" % exc

try:
    resource.setrlimit(resource.RLIMIT_AS, (hard, hard))
    attempts["raise_soft_to_hard"] = "succeeded"
except (ValueError, OSError) as exc:
    attempts["raise_soft_to_hard"] = "refused: %s" % exc

attempts["final"] = resource.getrlimit(resource.RLIMIT_AS)
sys.stderr.write(json.dumps(attempts, indent=2) + "\n")

IDLE_MS = 30_000
users, done = {}, []

for line in sys.stdin:
    if not line.strip():
        continue
    ev = json.loads(line)
    s = users.get(ev["user"])
    if s is not None and ev["ts"] - s[1] > IDLE_MS:
        done.append((ev["user"], s))
        s = None
    if s is None:
        users[ev["user"]] = [ev["ts"], ev["ts"], 1, ev["bytes"], {ev["path"]}]
    else:
        s[1] = ev["ts"]
        s[2] += 1
        s[3] += ev["bytes"]
        s[4].add(ev["path"])

for user, s in users.items():
    done.append((user, s))
done.sort(key=lambda r: (r[1][1], r[0]))
for user, s in done:
    sys.stdout.write(json.dumps({
        "user": user, "start_ts": s[0], "end_ts": s[1],
        "events": s[2], "bytes": s[3], "paths": len(s[4]),
    }, separators=(",", ":"), sort_keys=True) + "\n")
