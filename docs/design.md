# Design notes

Why each number in this environment is the number it is, and what the
measurements said when they disagreed with me.

---

## 1. A ceiling only discriminates if it has a floor

A memory ceiling is a difficulty lever only when the minimum working set is
*unavoidable*. If a candidate can make the working set arbitrarily small by
tuning some free parameter — a block size, a batch size, a flush interval —
then the ceiling measures nothing except whether they found the dial.

Here the floor is structural: to emit a session you must have accumulated it,
and a session cannot be emitted until the watermark has passed it. So every
correct solution holds *at least* the currently-open sessions. The generator
controls that number directly (`--concurrency`, default 1500) and it cannot be
traded away.

The gap the ceiling exploits:

| quantity | scale |
| --- | --- |
| distinct users over the stream | ~225,000 |
| sessions emitted | ~356,000 |
| sessions open at any instant | ~1,500 |

Two orders of magnitude, and no parameter a candidate controls moves it.

## 2. The band, measured on the enforced quantity

`RLIMIT_AS` bounds **address space**, not resident set. For CPython the two
differ substantially — arenas, shared objects and thread stacks are mapped
without being resident — so a ceiling chosen from an RSS measurement is chosen
from the wrong number. `scripts/ceiling_sweep.sh` sweeps the quantity that is
actually enforced.

| candidate | peak RSS | lowest ceiling it survives |
| --- | --- | --- |
| `reference` | 13.3 MiB | **20 MiB** |
| `m12_batch_tiebreak` (bounded, wrong order) | 13.4 MiB | 20 MiB |
| `m02_returning_user_set` | 34.9 MiB | **48 MiB** |
| `m01_accumulate_all` | 324.9 MiB | **384 MiB** |
| `m03_sort_at_end` | 316.5 MiB | 384 MiB |

The ceiling must exceed the reference's 20 MiB with enough headroom that a
correct-but-unpolished solution still fits, and stay below 48 MiB or the
tightest wrong route survives. **32 MiB** sits at 1.6x the reference's
requirement with a 16 MiB margin below the nearest failure.

Framed on the discriminating quantity rather than the total, the headroom is
larger than 1.6x looks: roughly 10 MiB of the reference's 20 is bare
interpreter, fixed for every candidate. The ceiling allows ~22 MiB of program
above that baseline where the reference needs ~10.

Stability across instances (`scripts/seed_sweep.sh`, 8 seeds, ceiling 32 MiB):
reference passes on every seed, 13.2–13.5 MiB, 355.7k–357.0k sessions. The
ceiling is a property of the distribution, not of one lucky instance.

## 3. Two things I got wrong, and how they were caught

Both were caught by measuring, not by review. Neither would have been visible
in a suite that only checked that mutants fail.

### A no-op mutant that looked like coverage

The second mutant was originally a lazy-deletion heap of `(last_ts, user)`:
one push per event, stale entries reclaimed only on reaching the top. I
asserted this was unbounded — a bounded accumulator with an unbounded index
over it, which is a genuinely good failure to test for.

It is not unbounded. Timestamps are non-decreasing, so a stale entry carries an
*old* key, surfaces at the top of the heap almost immediately, and is reclaimed
within one idle window. The heap holds roughly the events in a 30-second
window, about 3.4k entries.

Measured: **13.4 MiB against the reference's 13.2, and it PASSED.**

It was a mutant that sat in the must-fail matrix contributing nothing while
appearing to test the ceiling. Replaced by `m02_returning_user_set.py`, whose
unbounded structure — a set of every user ever seen, kept to answer a question
nobody asked — is unbounded for a reason that survives contact with the input
distribution.

The general shape: **a mutant is only coverage if it has been measured
failing.** Reasoning about whether a structure is bounded is exactly the skill
being tested, which is a good reason not to trust one's own answer.

### A mutant failing for the wrong reason

`m11_hunt_expected` is supposed to demonstrate that the expected answer is
unreachable: it walks the filesystem looking for it, finds nothing, and exits 0
with no output — a forged pass that fails on the *content* check.

Its first two versions failed on **memory** instead:

1. it accumulated every path it saw into a list, and died on the ceiling;
2. once that was fixed, it hit a `UnicodeDecodeError` on a binary file whose
   name matched one of its needles — and Ubuntu's apport excepthook then
   imported a module *while handling the exception*, raising `MemoryError`
   under the tight ceiling and printing that above the real cause.

The second one also exposed a bug in the classifier: `scripts/verify.py`
searched the whole stderr buffer for `MemoryError`, so it read the excepthook's
failure as the candidate's. It now truncates at apport's `Original exception
was:` marker before classifying.

This is the reason every mutant declares an expected *failure mode* and not
just an expected verdict. On verdict alone, all three versions of m11 were
green. The suite was reporting coverage of the "cannot find the answer"
property that it did not have.

## 4. The fan-out hole

`RLIMIT_AS` is per-process. `m10_fork_spread.py` shards users across K
children, holds 1/K of the unbounded accumulator in each, and k-way merges
their sorted output through a parent that stays small. Every individual process
is compliant; the sum is not.

Against an `RLIMIT_AS`-only build: **PASS, 48.6 MiB peak, correct output.**

Three things bound it now, in increasing order of how much they can be relied
on:

1. **`RLIMIT_NPROC` = 4.** Caps K. Sound only while
   `max_processes x address_space` stays below what the cheapest wrong route
   needs — `4 x 32 MiB = 128 MiB` against 384 MiB. Equivalently: sharding that
   route under a 32 MiB ceiling needs at least twelve processes.
   **Changing either number without re-checking that inequality re-opens the
   hole**, which is why the arithmetic is written out at the constant's
   definition in `grader/grade.py` rather than here.
2. **`--pids-limit`** on the container, independent of the per-user
   `RLIMIT_NPROC` accounting.
3. **cgroup `memory.max`** via `docker run --memory`. The only limit here that
   applies to the sum over a process tree. Every verdict reports
   `limits.tree_bound_source` — `cgroup` or `rlimit_as x max_processes` — so a
   run without it is visibly weaker rather than silently weaker.

## 5. Privilege ordering

The drop is `setgroups([])`, then `setresgid`, then `setresuid`, then an
attempted `setresuid(0,0,0)` that is *required to fail*.

`setuid` is the one-way door: after it the process can no longer call `setgid`
or `setgroups`. Dropping the uid first therefore strands the process holding
root's supplementary groups — quieter than not dropping at all, and worse,
because it looks dropped. The verification step exists because a privilege drop
that silently did not take produces a grade that is worthless in a way nothing
downstream can detect.

Related: the grading directory is `0700` root-owned, the generated input is
`0600`, and the candidate reaches its input only through a descriptor the
grader opened before dropping. So the candidate can read the stream and cannot
enumerate, replace, or hard-link anything beside it.

## 6. Resource accounting

`max_rss_bytes` comes from `os.wait4()`, which returns the rusage of **that**
child.

The alternative — `resource.getrusage(RUSAGE_CHILDREN)` in the grader — is
cumulative across every child the grader has ever reaped. In a matrix runner
that grades thirteen candidates in one process, it reports the high-water mark
of whichever earlier candidate was greediest, for every subsequent candidate.
The failure is invisible: the numbers are plausible, monotonic, and wrong.

## 7. What is not covered

Stated because a coverage claim with no boundary is not a claim.

- **The container path is unrun.** Docker was unavailable on the build machine.
  `env/Dockerfile` and `scripts/verify.sh` are written but untested, and every
  number in this document was produced with `"privileges_dropped": false`. The
  privilege-drop code path has therefore never executed. It is the first thing
  to run on a machine with a daemon.
- **The base image is unpinned**, deliberately — see the note at the top of
  `env/Dockerfile`. A drifting base moves the interpreter baseline the ceiling
  was measured against.
- **Single language.** Every candidate here is CPython, so the ceiling is
  calibrated against one interpreter's baseline. A Rust or C submission would
  have a far smaller floor and the band would need re-deriving; as written, the
  environment is only fair to solutions in the language it was measured with.
- **No wall-clock difficulty.** The reference finishes in 5.6 s CPU against a
  120 s limit. Time is not a lever here and is not claimed as one — a timeout
  tight enough to bite would fail slow-but-correct solutions rather than wrong
  ones.
