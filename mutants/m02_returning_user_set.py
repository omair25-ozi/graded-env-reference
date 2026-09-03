#!/usr/bin/env python3
"""MUST FAIL (memory), and it is the interesting one.

This mutant has the *right algorithm*.  It watermarks, it closes sessions as
soon as they can no longer be extended, and its open-session map is correctly
bounded -- its output is byte-identical to the reference.

It fails anyway, on one auxiliary structure: a set of every user it has ever
seen, kept so it could answer "is this a returning visitor?".  Nobody asked for
that field and it is never emitted; it is the kind of thing that accumulates in
a solution while the part the author is thinking about stays correctly bounded.

The accumulator is bounded.  The *bookkeeping beside* the accumulator is not.

An environment whose ceiling only catches ``m01_accumulate_all`` is testing
whether the candidate knows to stream.  One that also catches this is testing
whether they checked that *every* structure they added is bounded, which is the
skill that actually transfers.

--------------------------------------------------------------------------
A NOTE ON WHAT USED TO BE HERE, because the mistake is more instructive than
the fix.  This slot originally held a lazy-deletion heap of ``(last_ts, user)``
-- one push per event, stale entries reclaimed only on reaching the top --
which I asserted was unbounded.  It is not.  Timestamps are non-decreasing, so
a stale entry carries an *old* key, surfaces at the top of the heap almost
immediately, and is reclaimed within one idle window; the heap is bounded by
the events in a 30-second window, about 3.4k entries.  Measured: 13.4 MiB
against the reference's 13.2 MiB, and it PASSED.

It was a no-op mutant -- a case that sat in the must-fail matrix looking like
coverage while testing nothing.  It was caught by measuring it rather than by
reasoning about it, which is the only way these are ever caught.
"""
import json
import sys
from collections import OrderedDict

IDLE_MS = 30_000

open_s = OrderedDict()
ever_seen = set()          # <-- the mutation: grows with distinct users
out = sys.stdout


def flush(watermark):
    ready = []
    while open_s:
        user, s = next(iter(open_s.items()))
        if s[1] + IDLE_MS >= watermark:
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

    user = ev["user"]
    _returning = user in ever_seen
    ever_seen.add(user)

    s = open_s.get(user)
    if s is None:
        open_s[user] = [ts, ts, 1, ev["bytes"], {ev["path"]}]
    else:
        s[1] = ts
        s[2] += 1
        s[3] += ev["bytes"]
        s[4].add(ev["path"])
        open_s.move_to_end(user)

flush(float("inf"))
