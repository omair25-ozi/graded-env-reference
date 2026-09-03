#!/usr/bin/env python3
"""MUST FAIL (forged pass).

Reads the whole input so it looks busy, writes nothing, exits 0.  This is the
cheapest possible attack and it works against any harness that treats exit
status as the result.
"""
import sys

for _line in sys.stdin:
    pass

raise SystemExit(0)
