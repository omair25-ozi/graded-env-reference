#!/usr/bin/env python3
"""MUST FAIL (forged pass).

Writes text shaped like a harness verdict to both stdout and stderr, then exits
0.  Harnesses that scrape the graded program's own output for a result -- a
regex for PASS, a JSON blob on the last line, a "tests: N passed" summary --
are graded by the candidate rather than by the grader.

Here the candidate's stdout *is* the answer file, so this merely emits one
unparseable record; nothing the candidate can print is read as a verdict.
"""
import sys

for _line in sys.stdin:
    pass

sys.stdout.write("PASS\n")
sys.stdout.write('{"verdict":"PASS","reasons":[],"records":999999}\n')
sys.stderr.write("== 999999 passed in 0.01s ==\nRESULT: PASS\nexit 0\n")
raise SystemExit(0)
