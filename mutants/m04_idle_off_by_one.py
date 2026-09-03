#!/usr/bin/env python3
"""MUST FAIL (session boundaries).

Identical to the reference except that a gap of exactly IDLE_MS ends the
session (``>=`` where the spec says ``>``).  Bounded, fast, correctly ordered,
and wrong on precisely the events that land on the boundary.

The generator emits gaps of exactly IDLE_MS on purpose, so this is a graded
difference rather than a latent one -- a mutant that only fails on inputs the
environment never produces proves nothing.
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
        if s[1] + IDLE_MS > watermark:        # spec: >=
            break
        open_s.popitem(last=False)
        ready.append((s[1], user, s))
    ready.sort(key=lambda r: (r[0], r[1]))
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
