#!/usr/bin/env python3
"""Deterministic instance generator for the sessionization environment.

The generator emits an NDJSON event stream ordered by non-decreasing ``ts``.
Two properties are deliberate and load-bearing:

  * the number of *distinct* users over the whole stream is large, and
  * the number of *concurrently open* sessions at any instant is small.

That gap is the entire instance.  A solution that keeps one accumulator per
user it has ever seen scales with the first number; a solution that closes a
session once the watermark has passed it scales with the second.  The memory
ceiling in ``grader/grade.py`` is placed between the two, so the instance
discriminates between the algorithms rather than between implementations of
the same algorithm.

Everything is a pure function of ``--seed``, so no data is committed to the
repository; the grader regenerates the instance it grades.
"""

import argparse
import json
import random
import sys

IDLE_MS = 30_000

# A small fixed vocabulary.  Distinct-path counting is per session, so the
# vocabulary size bounds that set and keeps the legitimate working set honest:
# the floor of the problem is the open sessions, not the path strings.
PATHS = (
    "/", "/login", "/logout", "/search", "/cart", "/cart/add", "/checkout",
    "/orders", "/orders/detail", "/profile", "/settings", "/help",
    "/api/v1/items", "/api/v1/items/bulk", "/api/v1/pricing", "/static/app.js",
)


def generate(seed, n_events, concurrency, revisit_rate, retire_rate, out):
    """Write ``n_events`` NDJSON lines to ``out``.

    Returns a small dict of instance statistics, used by the design docs to
    justify where the memory ceiling sits.
    """
    rng = random.Random(seed)

    ts = 1_700_000_000_000  # fixed epoch: the instance must not depend on wall clock
    next_user = 0
    pool = []
    for _ in range(concurrency):
        pool.append("u%07d" % next_user)
        next_user += 1

    # Users that have left the active pool.  A bounded tail, so that some users
    # legitimately return after an idle gap and produce a *second* session --
    # the case that punishes a solution keying purely on "user seen before".
    retired = []
    revisits = 0

    for _ in range(n_events):
        # Non-decreasing, with genuine ties: equal timestamps are what make the
        # (last_ts, user) tie-break in the output ordering observable.
        ts += rng.choice((0, 1, 1, 2, 3, 5, 8, 13, 21, 34))

        idx = rng.randrange(len(pool))
        user = pool[idx]

        line = {
            "ts": ts,
            "user": user,
            "path": PATHS[rng.randrange(len(PATHS))],
            "bytes": rng.randrange(64, 65_536),
        }
        out.write(json.dumps(line, separators=(",", ":"), sort_keys=True))
        out.write("\n")

        if rng.random() < retire_rate:
            # Retire this slot and open a fresh one.  The retired user's session
            # closes on its own once the watermark advances past its idle gap.
            if len(retired) >= 4096:
                retired.pop(0)
            retired.append(user)

            if retired and rng.random() < revisit_rate:
                pool[idx] = retired.pop(rng.randrange(len(retired)))
                revisits += 1
            else:
                pool[idx] = "u%07d" % next_user
                next_user += 1

    return {
        "seed": seed,
        "events": n_events,
        "distinct_users": next_user,
        "pool_size": concurrency,
        "revisits": revisits,
        "idle_ms": IDLE_MS,
        "span_ms": ts - 1_700_000_000_000,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--events", type=int, default=1_200_000)
    ap.add_argument("--concurrency", type=int, default=1_500)
    ap.add_argument("--revisit-rate", type=float, default=0.15)
    ap.add_argument("--retire-rate", type=float, default=0.22)
    ap.add_argument("-o", "--output", default="-")
    ap.add_argument("--stats", action="store_true",
                    help="write instance statistics to stderr")
    args = ap.parse_args(argv)

    if args.output == "-":
        stats = generate(args.seed, args.events, args.concurrency,
                         args.revisit_rate, args.retire_rate, sys.stdout)
    else:
        with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
            stats = generate(args.seed, args.events, args.concurrency,
                             args.revisit_rate, args.retire_rate, fh)

    if args.stats:
        sys.stderr.write(json.dumps(stats, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
