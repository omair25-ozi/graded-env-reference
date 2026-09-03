#!/usr/bin/env python3
"""MUST FAIL (memory).

The natural first solution: keep one accumulator per user for the whole
stream, then emit at the end.  Algorithmically it computes the right sessions;
it just holds every user it has ever seen instead of only the open ones.  This
is the mutant the ceiling exists to separate -- if it passes, the environment
is not measuring what it claims to.
"""
import json
import sys

IDLE_MS = 30_000

users = {}
done = []

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
