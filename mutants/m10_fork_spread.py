#!/usr/bin/env python3
"""MUST FAIL -- and this is the mutant that probes the ceiling's real weakness.

``RLIMIT_AS`` is a **per-process** limit.  A candidate that refuses to stream
can still refuse to stream *in parallel*: shard users across K children, let
each child hold 1/K of the unbounded accumulator so that no single process
crosses the ceiling, then k-way merge the children's sorted output in a parent
whose own footprint stays small.  Total resident memory is K times the ceiling
and every individual process is compliant.

If this passes, the environment does not have a memory ceiling; it has a
per-process memory ceiling, which is a different and much weaker claim.  Two
things are supposed to stop it:

  * ``RLIMIT_NPROC``, which caps the fan-out, and
  * the container's cgroup ``memory.max`` (see ``env/Dockerfile`` and
    ``scripts/verify.sh``), which is the only limit that actually applies to
    the *sum* over a process tree.

Keeping this mutant in the matrix is what stops the second of those from being
quietly dropped later as redundant.  Its result is reported honestly in
docs/design.md whichever way it lands.
"""
import heapq
import json
import os
import sys

IDLE_MS = 30_000
SHARDS = int(os.environ.get("M10_SHARDS", "8"))


def child_main(read_fd, write_fd):
    """Accumulate an unbounded shard, then emit it sorted."""
    users, done = {}, []
    with os.fdopen(read_fd, "r", encoding="utf-8") as inp:
        for line in inp:
            if not line.strip():
                continue
            ev = json.loads(line)
            s = users.get(ev["user"])
            if s is not None and ev["ts"] - s[1] > IDLE_MS:
                done.append((ev["user"], s))
                s = None
            if s is None:
                users[ev["user"]] = [ev["ts"], ev["ts"], 1, ev["bytes"],
                                     {ev["path"]}]
            else:
                s[1] = ev["ts"]
                s[2] += 1
                s[3] += ev["bytes"]
                s[4].add(ev["path"])
    for user, s in users.items():
        done.append((user, s))
    users.clear()
    done.sort(key=lambda r: (r[1][1], r[0]))
    with os.fdopen(write_fd, "w", encoding="utf-8") as out:
        for user, s in done:
            out.write("%d\t%s\t%s\n" % (s[1], user, json.dumps({
                "user": user, "start_ts": s[0], "end_ts": s[1],
                "events": s[2], "bytes": s[3], "paths": len(s[4]),
            }, separators=(",", ":"), sort_keys=True)))


def main():
    to_child, from_child, pids = [], [], []
    for _ in range(SHARDS):
        in_r, in_w = os.pipe()
        out_r, out_w = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(in_w)
            os.close(out_r)
            for fd in to_child:
                os.close(fd)
            for fd in from_child:
                os.close(fd)
            try:
                child_main(in_r, out_w)
            except BaseException:
                os._exit(1)
            os._exit(0)
        os.close(in_r)
        os.close(out_w)
        to_child.append(in_w)
        from_child.append(out_r)
        pids.append(pid)

    writers = [os.fdopen(fd, "w", encoding="utf-8") for fd in to_child]
    for line in sys.stdin:
        if not line.strip():
            continue
        # Shard on the user field without parsing the whole record.
        i = line.find('"user":"')
        j = line.find('"', i + 8)
        writers[hash(line[i + 8:j]) % SHARDS].write(line)
    for w in writers:
        w.close()

    # Children only write after their input hits EOF, so no deadlock: the
    # parent has finished feeding every shard before it starts draining any.
    readers = [os.fdopen(fd, "r", encoding="utf-8") for fd in from_child]
    for line in heapq.merge(*readers, key=lambda l: (int(l.split("\t", 1)[0]),
                                                     l.split("\t", 2)[1])):
        sys.stdout.write(line.split("\t", 2)[2])
    for r in readers:
        r.close()

    bad = 0
    for pid in pids:
        _, status = os.waitpid(pid, 0)
        if status != 0:
            bad += 1
    sys.stderr.write("shards=%d failed=%d\n" % (SHARDS, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
