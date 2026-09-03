#!/usr/bin/env python3
"""MUST FAIL (ordering), while staying comfortably inside the ceiling.

Sessions, fields and totals are all exactly right, and the footprint is the
reference's.  The only difference is the tie-break inside a closing batch:
sessions that close on the same watermark advance are emitted ordered by
``(user, last_ts)`` instead of ``(last_ts, user)``.

This mutant exists because the two ordering failures in this suite -- this one
and ``m03_sort_at_end`` -- would otherwise both be masked by memory.  m03 wants
316 MiB, so at the real ceiling it dies before its ordering is ever compared,
and the ordering rule would be untested despite appearing twice in the matrix.
A rule the grader never actually exercises is a rule the environment does not
really have.

The generator emits runs of identical timestamps specifically so that closing
batches contain more than one session and this difference is observable.
"""
import json
import sys
from collections import OrderedDict

IDLE_MS = 30_000

open_s = OrderedDict()
out = sys.stdout


def flush(watermark):
    ready = []
    while open_s:
        user, s = next(iter(open_s.items()))
        if s[1] + IDLE_MS >= watermark:
            break
        open_s.popitem(last=False)
        ready.append((s[1], user, s))
    ready.sort(key=lambda r: (r[1], r[0]))       # <-- the mutation
    for _, user, s in ready:
        out.write(json.dumps({
            "user": user, "start_ts": s[0], "end_ts": s[1],
            "events": s[2], "bytes": s[3], "paths": len(s[4]),
        }, separators=(",", ":"), sort_keys=True) + "\n")


for line in sys.stdin:
    if not line.strip():
        continue
    ev = json.loads(line)
    ts = ev["ts"]
    flush(ts)
    s = open_s.get(ev["user"])
    if s is None:
        open_s[ev["user"]] = [ts, ts, 1, ev["bytes"], {ev["path"]}]
    else:
        s[1] = ts
        s[2] += 1
        s[3] += ev["bytes"]
        s[4].add(ev["path"])
        open_s.move_to_end(ev["user"])

flush(float("inf"))
