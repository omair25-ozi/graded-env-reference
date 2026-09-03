# Grading image.
#
# The container is not decoration. Two properties of the grade only exist
# inside it:
#
#   * The grader starts as root, so it can actually drop privileges before
#     running candidate code. Outside a container it typically runs as an
#     ordinary user, `setresuid` is unavailable, and the candidate runs with
#     the grader's own rights -- readable in every verdict as
#     "privileges_dropped": false.
#
#   * `docker run --memory` installs a cgroup `memory.max` over the whole
#     process tree. RLIMIT_AS is per-process and does not bound a candidate
#     that shards its accumulator across children; see
#     mutants/m10_fork_spread.py, which defeated an RLIMIT_AS-only build of
#     this grader. RLIMIT_NPROC caps the fan-out, and the cgroup catches what
#     is left.
#
# PIN THIS BY DIGEST BEFORE USING IT TO GRADE ANYTHING.
#
# A base image that drifts changes the interpreter's memory baseline, and the
# ceiling was measured against that baseline -- so a silent base-image update
# moves the pass/fail boundary without a single line of this repository
# changing. The tag below is deliberately left unpinned rather than pinned to a
# digest I could not verify on the machine this was built on:
#
#     docker pull python:3.12-slim
#     docker inspect --format='{{index .RepoDigests 0}}' python:3.12-slim
#
# then replace the tag with `python:3.12-slim@sha256:<digest>` and re-run
# scripts/ceiling_sweep.sh to confirm the band still holds.
FROM python:3.12-slim

# `nobody` exists in this base image; the grader looks it up rather than
# hardcoding 65534, and falls back if the base ever changes.
RUN set -eux; id nobody

WORKDIR /env
COPY grader/ /env/grader/
COPY task/ /env/task/
COPY mutants/ /env/mutants/
COPY scripts/ /env/scripts/
COPY tests/ /env/tests/

# Root owns everything and nothing is group- or world-writable: the candidate
# runs as `nobody` and must not be able to edit the grader that is about to
# grade it.
RUN set -eux; \
    chown -R root:root /env; \
    chmod -R go-w /env

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# Default: run the full must-pass/must-fail matrix.
CMD ["python3", "/env/scripts/verify.py"]
