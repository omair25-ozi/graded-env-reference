#!/usr/bin/env python3
"""MUST FAIL (type slip).

Every number is right; ``bytes`` is serialised as a float, so the record reads
``"bytes":1234.0`` where the reference writes ``"bytes":1234``.

This mutant exists to pin down the grader's comparison semantics.  The grader
deliberately falls back to a *structural* comparison when a line is not
byte-identical, so that a candidate is not punished for key order or spacing.
The question this asks is whether that tolerance was made so wide that it also
stopped distinguishing an integer from a float -- a slip that would let real
precision bugs through on any instance where the sums got large enough to
matter.
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
        "events": s[2],
        "bytes": float(s[3]),     # <-- the mutation
        "paths": len(s[4]),
    }, separators=(",", ":"), sort_keys=True) + "\n")


reference._emit = _emit
reference.sessionize(sys.stdin, sys.stdout)
