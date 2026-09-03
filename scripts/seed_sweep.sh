#!/usr/bin/env bash
# Does the environment behave the same on every instance, or did it happen to
# work on one seed?
#
# An environment that passes the reference on the seed it was tuned against and
# fails it on the next one is worse than no environment: it reports a candidate
# as wrong for reasons the candidate cannot see or fix. The ceiling in
# particular is a property of the *instance distribution*, not of one instance,
# so it has to hold across seeds with the headroom intact.
#
# Prints, per seed, whether the reference passes and how much of the ceiling it
# actually used. The margin column is the number to watch: if it ever
# approaches zero the ceiling is too tight regardless of the verdict.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"

EVENTS="${EVENTS:-1200000}"
CONCURRENCY="${CONCURRENCY:-1500}"
CEILING_MIB="${CEILING_MIB:-32}"
SEEDS="${SEEDS:-1 2 3 20260904 99991 123456 777 31337}"

printf 'ceiling %s MiB, %s events, concurrency %s\n\n' \
    "$CEILING_MIB" "$EVENTS" "$CONCURRENCY"
printf '%-12s %-8s %10s %10s %9s\n' seed verdict 'peak RSS' sessions 'cpu (s)'
printf -- '----------------------------------------------------------\n'

fails=0
for seed in $SEEDS; do
  out="$("$PY" "$ROOT/grader/grade.py" \
      --seed "$seed" --events "$EVENTS" --concurrency "$CONCURRENCY" \
      --address-space-mib "$CEILING_MIB" \
      --cpu-seconds 900 --wall-seconds 900 \
      -- "$PY" "$ROOT/grader/reference.py" 2>/dev/null)"
  line="$(printf '%s' "$out" | "$PY" -c '
import json, sys
v = json.load(sys.stdin)
d = v.get("detail") or {}
print("%-8s %6.1f MiB %10s %9.1f" % (
    v["verdict"], v["resources"]["max_rss_mib"],
    d.get("records", "-"), v["resources"]["cpu_seconds"]))
print(v["verdict"])
')"
  printf '%-12s %s\n' "$seed" "$(printf '%s' "$line" | head -1)"
  if [ "$(printf '%s' "$line" | tail -1)" != "PASS" ]; then
    fails=$((fails + 1))
  fi
done

printf -- '----------------------------------------------------------\n'
if [ "$fails" -eq 0 ]; then
  printf 'reference passes on every seed\n'
else
  printf 'UNSTABLE: reference failed on %d seed(s)\n' "$fails"
  exit 1
fi
