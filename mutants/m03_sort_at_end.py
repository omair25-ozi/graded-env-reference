#!/usr/bin/env python3
"""MUST FAIL (ordering, and memory as a consequence).

Closes sessions correctly and on time, but buffers every closed session so it
can sort the whole output by (start_ts, user) at the end -- the ordering a
reader assumes when they skim the spec for "sorted" and stop reading before the
sentence that says emission order is *close* order.

Buffering the output to sort it is the same mistake as buffering the input,
one step later.
"""
import json
import sys
from collections import OrderedDict

IDLE_MS = 30_000

open_s = OrderedDict()
closed = []


def flush(watermark):
    while open_s:
        user, s = next(iter(open_s.items()))
        if s[1] + IDLE_MS >= watermark:
            break
        open_s.popitem(last=False)
        closed.append((user, s))


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

closed.sort(key=lambda r: (r[1][0], r[0]))
for user, s in closed:
    sys.stdout.write(json.dumps({
        "user": user, "start_ts": s[0], "end_ts": s[1],
        "events": s[2], "bytes": s[3], "paths": len(s[4]),
    }, separators=(",", ":"), sort_keys=True) + "\n")
