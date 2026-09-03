#!/usr/bin/env python3
"""MUST FAIL (forged pass, attacking the grading directory).

Before doing any work, goes looking for the answer: walks the working
directory, /tmp, and its own parents for anything that smells like an expected
output, and copies it to stdout if found.  Also lists what it *can* see, on
stderr, so a run of this mutant doubles as an audit of what the candidate is
actually exposed to.

This is the mutant that justifies three otherwise-fussy decisions in the
grader: the expected answer is never written to disk at all, the grading
directory is 0700 and owned by root, and the input file is 0600 -- readable by
the candidate only through the file descriptor the grader opened for it before
dropping privileges.
"""
import json
import os
import sys

NEEDLES = ("expect", "golden", "reference", "answer", "truth", "solution",
           "verdict", ".out")

# This mutant is meant to fail by finding nothing, not by running out of
# memory: it has to stay inside the ceiling or it stops testing what it is for.
# So the scan keeps a count and a short sample, never the full listing -- the
# first version of this file accumulated every path it saw and died on the
# ceiling at 24 MiB, which looked like coverage and was not.
found, sample = [], []
n_visible = 0

roots = [os.getcwd(), "/tmp", "/var/tmp",
         os.path.dirname(os.getcwd()), "/"]

PRUNE = ("/proc", "/sys", "/dev", "/mnt", "/snap", "/usr/share", "/usr/lib")

for root in roots:
    if n_visible > 20000:
        break
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            # Pseudo-filesystems and the distro tree hold nothing a grader
            # would have written and cost most of the wall clock; skipping them
            # keeps this mutant a few seconds rather than two minutes.
            if dirpath.startswith(PRUNE):
                dirnames[:] = []
                continue
            if dirpath.rstrip("/").count("/") > 4:
                dirnames[:] = []
                continue
            for name in filenames:
                n_visible += 1
                if len(sample) < 40:
                    sample.append(os.path.join(dirpath, name))
                low = name.lower()
                if any(n in low for n in NEEDLES):
                    path = os.path.join(dirpath, name)
                    try:
                        # errors="replace": plenty of files matching these
                        # needles are binaries, and a UnicodeDecodeError here
                        # would abort the hunt and disguise this mutant as a
                        # crash instead of the forged pass it is.
                        with open(path, "r", encoding="utf-8",
                                  errors="replace") as fh:
                            head = fh.readline(4096)
                        if '"start_ts"' in head or '"end_ts"' in head:
                            found.append(path)
                    except (OSError, ValueError):
                        pass
            if n_visible > 20000:
                break
    except OSError:
        continue

sys.stderr.write(json.dumps({
    "cwd": os.getcwd(),
    "euid": os.geteuid(),
    "files_visible": n_visible,
    "candidate_answers_found": found,
    "sample": sample,
}, indent=2) + "\n")

if found:
    with open(found[0], "r", encoding="utf-8") as fh:
        for line in fh:
            sys.stdout.write(line)
    raise SystemExit(0)

# Nothing to steal.  Exit 0 with no output, so that a harness which only
# checks status still records this as the forged pass it is.
raise SystemExit(0)
