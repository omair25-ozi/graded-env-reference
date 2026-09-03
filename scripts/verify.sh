#!/usr/bin/env bash
# Run the grading matrix inside the container, which is the only configuration
# in which the environment's claims are all actually true:
#
#   --memory / --memory-swap  a cgroup ceiling over the whole process tree, so
#                             the per-process RLIMIT_AS cannot be sidestepped
#                             by sharding across children
#   (runs as root)            so the grader can drop to `nobody` before exec
#   --network none            candidate code has no network
#   --read-only + tmpfs       nothing on disk is writable except the grading
#                             directory, which is 0700 root-owned
#   --pids-limit              a second brake on fan-out, independent of
#                             RLIMIT_NPROC
#
# The cgroup is set well above the 32 MiB task ceiling on purpose: it is a
# backstop against the *sum* over a process tree, not a second copy of the
# per-process limit. Setting it to 32 MiB would kill the grader along with the
# candidate, since the grader shares the container.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${IMAGE:-graded-env-reference:local}"
TREE_MIB="${TREE_MIB:-256}"

echo "==> building $IMAGE"
docker build -f "$ROOT/env/Dockerfile" -t "$IMAGE" "$ROOT"

echo "==> running the matrix (tree ceiling ${TREE_MIB} MiB)"
exec docker run --rm \
  --memory="${TREE_MIB}m" \
  --memory-swap="${TREE_MIB}m" \
  --pids-limit=128 \
  --network=none \
  --read-only \
  --tmpfs /tmp:rw,exec,size=1g \
  "$IMAGE" \
  python3 /env/scripts/verify.py "$@"
