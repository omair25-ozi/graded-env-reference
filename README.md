# graded-env-reference

A reference **agent-evaluation environment**: one task, an exactly-graded
verifier, an enforced memory ceiling that separates algorithms rather than
implementations, and a must-fail suite that demonstrates the grader cannot be
fooled.

It exists to show what a defensible graded environment looks like end to end.
The task itself is deliberately small — you can read the whole specification in
a minute. Everything interesting is in the harness around it.

```
$ python3 scripts/verify.py

case                     verdict  mode      peak RSS  seconds
-------------------------------------------------------------
reference                PASS     -         13.5 MiB     17.5
m01_accumulate_all       FAIL     memory    26.6 MiB      5.7
m02_returning_user_set   FAIL     memory    26.9 MiB     10.1
m03_sort_at_end          FAIL     memory    26.6 MiB      5.8
m12_batch_tiebreak       FAIL     answer    13.4 MiB     11.3
m04_idle_off_by_one      FAIL     answer    13.4 MiB     12.4
m05_paths_not_distinct   FAIL     answer    13.3 MiB     11.1
m06_float_serialization  FAIL     answer    13.3 MiB     11.1
m07_exit_zero_silent     FAIL     silent    12.0 MiB      5.5
m08_print_verdict        FAIL     silent    11.9 MiB      5.5
m09_raise_rlimit         FAIL     memory    26.7 MiB      5.8
m10_fork_spread          FAIL     fanout    24.1 MiB      5.7
m11_hunt_expected        FAIL     silent    11.8 MiB      5.6

matrix clean: reference passes, all 12 mutants fail, each for the reason it
was written to fail for.
```

## The task

Sessionize an event stream: read 1.2M NDJSON events ordered by non-decreasing
timestamp, emit one record per user session, in the order sessions *close*.
Full specification in [`task/instruction.md`](task/instruction.md).

The stream has ~225,000 distinct users but only ~1,500 sessions open at any
instant. A solution that keeps state per user it has ever seen needs 384 MiB.
One that closes a session once the watermark has passed it needs 20. The
ceiling is set at 32.

## Four things that make it hard to fake

**1. The instance and the answer are both derived, never stored.**
There is no input file to edit and no expected output to copy: both are pure
functions of `--seed`. The expected answer is streamed out of the reference
*after* the candidate exits and compared record by record, so it never exists
on disk at all. `mutants/m11_hunt_expected.py` searches the filesystem for it
and reports what it can see; there is nothing to find.

**2. The candidate's output is a file it cannot read back.**
stdout is redirected to a file the grader opens `O_WRONLY`, mode 0600, owned by
root, *before* dropping privileges. The candidate writes its answer through the
descriptor and can neither re-open it nor read it. Nothing it prints is ever
interpreted as a verdict — `mutants/m08_print_verdict.py` prints `PASS`, a JSON
verdict blob and a pytest summary line, and merely emits an unparseable first
record.

**3. The ceiling is enforced, not measured.**
`RLIMIT_AS` — address space, not `RLIMIT_DATA`, which modern allocators bypass
via `mmap` — is set **soft equal to hard** before `execvp`. A process may
always raise its soft limit to its hard limit, so setting only the soft limit is
decorative; `mutants/m09_raise_rlimit.py` does exactly that and reports on
stderr that the kernel refused it.

**4. The must-fail suite runs with the must-pass half, in one command.**
A suite where everything fails is vacuously green — it would look identical if
the grader rejected the correct answer too. Every mutant also declares *why*
it should fail, and that is checked: a mutant meant to die on the ceiling but
actually dying on a typo has silently stopped providing coverage.

## The measured hole, and the fix

`RLIMIT_AS` is **per-process**. `mutants/m10_fork_spread.py` shards the
unbounded accumulator across 8 children, keeps every individual process under
the ceiling, and k-way merges their sorted output in a parent that stays small.

Against an `RLIMIT_AS`-only build of this grader, **it passed** — 48.6 MiB peak,
correct output. That is not a hypothetical; it is in the measurement log.

The fix is that the process cap is part of the memory ceiling, and the two have
to be chosen together. The pair is sound only while

```
max_processes  x  address_space  <  address space the cheapest wrong route needs
        4      x     32 MiB      =  128 MiB   <   384 MiB
```

Put the other way round: sharding that route under a 32 MiB ceiling takes at
least twelve processes, and the cap is four. Under Docker a cgroup
`memory.max` bounds the process tree directly, which is the real fix; every
verdict reports which of the two is actually in force via
`limits.tree_bound_source`.

## Quickstart

Needs Linux (or WSL2). `RLIMIT_AS`, `setresuid` and `ru_maxrss` do not work on
Windows, and a run there will report numbers that are not measuring anything.

```bash
python3 tests/test_reference.py     # reference vs brute-force oracle, 3005 instances
python3 scripts/verify.py           # the full must-pass/must-fail matrix (~2 min)
bash scripts/ceiling_sweep.sh       # lowest ceiling each candidate survives
bash scripts/seed_sweep.sh          # reference stability across seeds
```

Grade one program:

```bash
python3 grader/grade.py --seed 20260904 -- python3 my_solution.py
```

Under the container, which is the only configuration where privileges are
actually dropped and the process tree is actually bounded:

```bash
bash scripts/verify.sh
```

## Repository

| path | |
| --- | --- |
| `task/instruction.md` | the specification given to the candidate |
| `task/generate.py` | deterministic instance generator |
| `grader/reference.py` | the bounded reference solution |
| `grader/sandbox.py` | rlimits, privilege drop, `wait4` accounting |
| `grader/grade.py` | the verifier |
| `mutants/` | 12 wrong solutions, each with the reason it must fail |
| `tests/test_reference.py` | differential test against a brute-force oracle |
| `scripts/` | matrix, ceiling sweep, seed sweep, container runner |
| `docs/design.md` | why every number is the number it is |

## Provenance of the numbers

Every figure in this README was measured on the machine that built it: WSL2
Ubuntu, CPython 3.14.4, 12 CPUs, 5.6 GB RAM. The matrix, the ceiling sweep and
the seed sweep are all reproducible with the commands above.

Two honest caveats. The grading path under Docker is **not** exercised in those
numbers — Docker was unavailable on the build machine, so the container layer
is written but unrun, and the matrix above was produced with
`"privileges_dropped": false`. And the base image in `env/Dockerfile` is
deliberately left on a tag rather than pinned to a digest I could not verify;
pin it before grading anything real.

## License

MIT. See [LICENSE](LICENSE).
