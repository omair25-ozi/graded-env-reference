#!/usr/bin/env python3
"""Reference solution: bounded-memory sessionization.

Reads the NDJSON event stream on stdin, writes one NDJSON session record per
line to stdout, and holds only the *currently open* sessions in memory.

The two facts that make the bound achievable:

  1. The input is ordered by non-decreasing ``ts``, so the current event's
     timestamp is a watermark: no future event can extend a session whose last
     event is more than ``IDLE_MS`` behind it.
  2. Because ``ts`` is non-decreasing, touching a user makes it the *most*
     recently active of all open sessions.  An ``OrderedDict`` used as an LRU
     therefore keeps open sessions in ascending ``last_ts`` order for free, so
     the sessions eligible to close are always a prefix of it.

Together those give O(open sessions) memory and O(1) amortised work per event,
with no auxiliary index that grows with the stream.  The obvious alternative --
a heap of ``(last_ts, user)`` with lazy deletion -- is *algorithmically* fine
but pushes one entry per event and never reclaims the stale ones, so its
footprint grows with the stream rather than with the open set.  That failure is
shipped as ``mutants/m02_lazy_heap.py``.
"""

import json
import sys
from collections import OrderedDict

IDLE_MS = 30_000


def _emit(out, user, s):
    # sort_keys and a compact separator make the byte stream canonical, so the
    # grader can compare records without re-parsing ambiguity.
    out.write(json.dumps({
        "user": user,
        "start_ts": s[0],
        "end_ts": s[1],
        "events": s[2],
        "bytes": s[3],
        "paths": len(s[4]),
    }, separators=(",", ":"), sort_keys=True))
    out.write("\n")


def sessionize(inp, out, idle_ms=IDLE_MS):
    # user -> [start_ts, last_ts, n_events, total_bytes, {paths}]
    # Insertion order is activity order, which (given non-decreasing ts) is
    # ascending last_ts.
    open_s = OrderedDict()

    def flush(watermark):
        """Close every session that can no longer be extended."""
        ready = []
        while open_s:
            user, s = next(iter(open_s.items()))
            if s[1] + idle_ms >= watermark:
                break  # ordered by last_ts: nothing further can be ready either
            open_s.popitem(last=False)
            ready.append((s[1], user, s))
        # Sessions closing on the same watermark advance are ordered by
        # (last_ts, user).  The batch is bounded by the open set, never the
        # stream, so this sort does not reintroduce unbounded memory.
        ready.sort(key=lambda r: (r[0], r[1]))
        for _, user, s in ready:
            _emit(out, user, s)

    for line in inp:
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
            s[3] += ev["bytes"]  # integers throughout: the grade is exact
            s[4].add(ev["path"])
            open_s.move_to_end(ev["user"])

    # End of stream is an infinite watermark: everything still open closes now.
    flush(float("inf"))


def main():
    sessionize(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
