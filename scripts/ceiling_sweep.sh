#!/usr/bin/env bash
# Find the lowest ceiling each candidate can survive.
#
# RLIMIT_AS bounds *address space*, not resident set. For CPython the two differ
# by a lot -- arenas, loaded shared objects and thread stacks are all mapped but
# not all resident -- so a ceiling picked from an RSS measurement is picked from
# the wrong number. This sweeps the actual enforced quantity.
#
# The output is the input to docs/design.md: the ceiling has to sit above the
# reference's survival point with real headroom, and below every wrong route's.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"

SEED="${SEED:-20260904}"
EVENTS="${EVENTS:-1200000}"
CONCURRENCY="${CONCURRENCY:-1500}"
STEPS="${STEPS:-16 20 24 32 40 48 64 96 128 192 256 384 512}"

CASES="
grader/reference.py
mutants/m01_accumulate_all.py
mutants/m02_returning_user_set.py
mutants/m03_sort_at_end.py
mutants/m12_batch_tiebreak.py
"

printf '%-34s %s\n' case 'lowest ceiling that does not kill it (MiB)'
printf -- '--------------------------------------------------------------------\n'

for rel in $CASES; do
  printf '%-34s ' "$rel"
  survived=""
  for mib in $STEPS; do
    out="$("$PY" "$ROOT/grader/grade.py" \
        --seed "$SEED" --events "$EVENTS" --concurrency "$CONCURRENCY" \
        --address-space-mib "$mib" --cpu-seconds 900 --wall-seconds 900 \
        -- "$PY" "$ROOT/$rel" 2>/dev/null)"
    killed="$(printf '%s' "$out" | "$PY" -c '
import json, sys
try:
    v = json.load(sys.stdin)
except Exception:
    print("1"); raise SystemExit
e = v["execution"]
tail = v.get("candidate_stderr_tail", "")
print("1" if (e["term_signal"] is not None
              or "MemoryError" in tail
              or "Cannot allocate memory" in tail) else "0")
')"
    if [ "$killed" = "0" ]; then
      survived="$mib"
      break
    fi
  done
  if [ -n "$survived" ]; then
    printf '%s\n' "$survived"
  else
    printf 'over %s\n' "${STEPS##* }"
  fi
done
