#!/usr/bin/env bash
# Measure the memory band the ceiling has to sit inside.
#
# Every candidate is run with a deliberately generous address-space limit, so
# nothing is killed and the number reported is what the program actually wants
# rather than what it was allowed. The ceiling in grader/grade.py is then
# chosen from these numbers, not guessed: it must sit above the reference's
# peak with enough headroom that a correct-but-unpolished solution still fits,
# and below the cheapest incorrect route.
#
# Run under a real Linux kernel. ru_maxrss on WSL2 and in a container is
# accurate; on Windows it is not.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"

SEED="${SEED:-20260904}"
EVENTS="${EVENTS:-1200000}"
CONCURRENCY="${CONCURRENCY:-1500}"
HEADROOM_MIB="${HEADROOM_MIB:-3072}"

CASES="
grader/reference.py
mutants/m01_accumulate_all.py
mutants/m02_returning_user_set.py
mutants/m03_sort_at_end.py
mutants/m12_batch_tiebreak.py
mutants/m10_fork_spread.py
"

printf '%-32s %-8s %10s %10s\n' case verdict 'peak RSS' 'cpu (s)'
printf -- '---------------------------------------------------------------\n'

for rel in $CASES; do
  out="$("$PY" "$ROOT/grader/grade.py" \
      --seed "$SEED" --events "$EVENTS" --concurrency "$CONCURRENCY" \
      --address-space-mib "$HEADROOM_MIB" \
      --cpu-seconds 900 --wall-seconds 900 \
      -- "$PY" "$ROOT/$rel" 2>/dev/null)"
  printf '%-32s ' "$rel"
  printf '%s\n' "$out" | "$PY" -c '
import json, sys
v = json.load(sys.stdin)
print("%-8s %6.1f MiB %10.1f" % (
    v["verdict"], v["resources"]["max_rss_mib"], v["resources"]["cpu_seconds"]))
'
done
