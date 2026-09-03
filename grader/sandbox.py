#!/usr/bin/env python3
"""Process isolation for candidate code.

The grader runs untrusted code.  Three things have to be true before that code
starts, and the order they are established in is not interchangeable:

  1. **The ceiling is on address space, not on the data segment.**
     ``RLIMIT_DATA`` bounds ``brk``, which modern allocators bypass -- CPython's
     arenas, and anything that reaches for ``mmap`` directly, sail straight
     through it.  ``RLIMIT_AS`` bounds the whole mapping, which is the number
     the environment actually means.

  2. **Soft and hard limits are set to the same value.**
     A process may always *raise* its soft limit up to its hard limit.  Setting
     only the soft limit is decorative: the candidate resets it in one call.
     Only the hard limit is irreversible for an unprivileged process.

  3. **Privileges are dropped last, and in the order groups, gid, uid.**
     ``setuid`` is the one-way door -- after it, the process can no longer call
     ``setgid`` or ``setgroups``.  Dropping the uid first therefore strands the
     process with root's supplementary groups, which is a quieter hole than
     never having dropped at all.  The drop is verified by attempting to regain
     root and requiring that it fail.

The child is also given its own session (``setsid``) so that a process which
forks children can be killed as a group rather than leaving orphans behind that
outlive the grade.
"""

import json
import os
import resource
import signal
import sys

# Set both soft and hard for every limit; see note 2 above.
_LIMITS = (
    ("RLIMIT_AS", resource.RLIMIT_AS),
    ("RLIMIT_CPU", resource.RLIMIT_CPU),
    ("RLIMIT_FSIZE", resource.RLIMIT_FSIZE),
    ("RLIMIT_NOFILE", resource.RLIMIT_NOFILE),
    ("RLIMIT_NPROC", resource.RLIMIT_NPROC),
)


class Limits(object):
    def __init__(self, address_space_bytes, cpu_seconds, wall_seconds,
                 output_bytes=256 << 20, open_files=64, processes=64):
        self.address_space_bytes = address_space_bytes
        self.cpu_seconds = cpu_seconds
        self.wall_seconds = wall_seconds
        self.output_bytes = output_bytes
        self.open_files = open_files
        self.processes = processes

    def as_dict(self):
        return {
            "address_space_bytes": self.address_space_bytes,
            "cpu_seconds": self.cpu_seconds,
            "wall_seconds": self.wall_seconds,
            "output_bytes": self.output_bytes,
        }


def _apply_limits(limits):
    resource.setrlimit(resource.RLIMIT_AS,
                       (limits.address_space_bytes, limits.address_space_bytes))
    resource.setrlimit(resource.RLIMIT_CPU,
                       (limits.cpu_seconds, limits.cpu_seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE,
                       (limits.output_bytes, limits.output_bytes))
    resource.setrlimit(resource.RLIMIT_NOFILE,
                       (limits.open_files, limits.open_files))
    resource.setrlimit(resource.RLIMIT_NPROC,
                       (limits.processes, limits.processes))
    # Core dumps would be written as the candidate and can be large.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _drop_privileges(uid, gid):
    """Irreversibly become (uid, gid).  Must be the last privileged act."""
    os.setgroups([])          # before setgid, and certainly before setuid
    os.setresgid(gid, gid, gid)
    os.setresuid(uid, uid, uid)
    # Verify the door is shut.  If root can be regained the grade is worthless,
    # so fail closed rather than grade under a false assumption.
    try:
        os.setresuid(0, 0, 0)
    except OSError:
        return
    raise RuntimeError("privilege drop did not take: regained uid 0")


def tree_limit_bytes():
    """The cgroup v2 memory ceiling covering this process tree, or None.

    ``RLIMIT_AS`` is per-process, so it does not bound a candidate that shards
    its work across children (``mutants/m10_fork_spread.py`` does exactly
    that, and defeated an RLIMIT_AS-only build of this grader).  A cgroup
    ``memory.max`` is the only limit here that applies to the *sum* over a
    process tree, and it is set from outside the container -- ``docker run
    --memory``.  The grader reports whether it is present so that a run
    without it is visibly weaker rather than silently weaker.
    """
    for path in ("/sys/fs/cgroup/memory.max",                 # v2, unified
                 "/sys/fs/cgroup/memory/memory.limit_in_bytes"):  # v1
        try:
            with open(path, "r") as fh:
                raw = fh.read().strip()
        except OSError:
            continue
        if raw == "max":
            return None
        try:
            value = int(raw)
        except ValueError:
            continue
        # cgroup v1 reports a sentinel near 2^63 when unlimited.
        if value >= (1 << 62):
            return None
        return value
    return None


def unprivileged_ids():
    """(uid, gid) to grade as, or None when the grader is not root."""
    if os.geteuid() != 0:
        return None
    import pwd
    for name in ("nobody", "nfsnobody", "daemon"):
        try:
            ent = pwd.getpwnam(name)
        except KeyError:
            continue
        if ent.pw_uid != 0:
            return (ent.pw_uid, ent.pw_gid)
    return (65534, 65534)


def run(argv, stdin_path, stdout_path, stderr_path, limits, cwd=None):
    """Run ``argv`` under the sandbox.  Returns a result dict.

    Never raises on candidate misbehaviour -- a candidate that dies, hangs, or
    is killed by a limit is a *grading outcome*, not a grader error.
    """
    ids = unprivileged_ids()

    pid = os.fork()
    if pid == 0:
        # ---- child: no exception may escape, or we would return a second
        # ---- copy of the grader into the caller's control flow.
        try:
            os.setsid()

            fd = os.open(stdin_path, os.O_RDONLY)
            os.dup2(fd, 0)
            if fd != 0:
                os.close(fd)
            fd = os.open(stdout_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.dup2(fd, 1)
            if fd != 1:
                os.close(fd)
            fd = os.open(stderr_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.dup2(fd, 2)
            if fd != 2:
                os.close(fd)

            if cwd:
                os.chdir(cwd)

            _apply_limits(limits)
            if ids is not None:
                _drop_privileges(ids[0], ids[1])

            os.execvp(argv[0], argv)
        except BaseException:
            os._exit(127)
        os._exit(127)

    # ---- parent
    timed_out = {"v": False}

    def _on_alarm(signum, frame):
        timed_out["v"] = True
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass

    previous = signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(int(limits.wall_seconds))
    try:
        _, status, rusage = os.wait4(pid, 0)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        # Reap anything the candidate left behind in its process group.
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass

    if os.WIFSIGNALED(status):
        exit_code, term_signal = None, os.WTERMSIG(status)
    else:
        exit_code, term_signal = os.WEXITSTATUS(status), None

    return {
        # ru_maxrss from wait4 belongs to *this* child.  Reading
        # RUSAGE_CHILDREN in the grader instead would accumulate across every
        # candidate graded in the same process and silently report the high
        # water mark of an earlier one.
        "max_rss_bytes": rusage.ru_maxrss * 1024,
        "cpu_seconds": rusage.ru_utime + rusage.ru_stime,
        "exit_code": exit_code,
        "term_signal": term_signal,
        "timed_out": timed_out["v"],
        "privileges_dropped": ids is not None,
    }


if __name__ == "__main__":
    sys.stderr.write(json.dumps({
        "euid": os.geteuid(),
        "can_drop_privileges": unprivileged_ids() is not None,
    }, indent=2) + "\n")
