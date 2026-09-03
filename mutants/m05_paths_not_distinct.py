#!/usr/bin/env python3
"""MUST FAIL (wrong field).

Bounded and correctly ordered; reports the session's event count in the
``paths`` field instead of the number of distinct paths.  Written as a patch
over the reference so that the mutation is the whole file and cannot silently
drift from the thing it is supposed to mutate.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "grader"))
import reference  # noqa: E402


def _emit(out, user, s):
    out.write(json.dumps({
        "user": user, "start_ts": s[0], "end_ts": s[1],
        "events": s[2], "bytes": s[3],
        "paths": s[2],            # <-- the mutation: total, not distinct
    }, separators=(",", ":"), sort_keys=True) + "\n")


reference._emit = _emit
reference.sessionize(sys.stdin, sys.stdout)
