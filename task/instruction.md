# Task: bounded-memory sessionization

Read an event stream on **stdin** and write session records to **stdout**.

## Input

One JSON object per line, ordered by **non-decreasing** `ts`. Equal timestamps
occur and are not an error.

```json
{"bytes":4096,"path":"/checkout","ts":1700000000123,"user":"u0000042"}
```

| field   | type   | meaning                          |
| ------- | ------ | -------------------------------- |
| `ts`    | int    | event time, milliseconds         |
| `user`  | string | opaque user identifier           |
| `path`  | string | requested path                   |
| `bytes` | int    | response size                    |

## Sessions

`IDLE_MS = 30000`.

A **session** is a maximal run of one user's events in which consecutive events
are at most `IDLE_MS` apart. A gap of *strictly more* than `IDLE_MS` ends the
session; a gap of exactly `IDLE_MS` does not. A user may have many sessions
over the stream.

## Output

One JSON object per line:

```json
{"bytes":81920,"end_ts":1700000030000,"events":12,"paths":5,"start_ts":1700000000123,"user":"u0000042"}
```

| field      | meaning                                                     |
| ---------- | ----------------------------------------------------------- |
| `start_ts` | `ts` of the session's first event                            |
| `end_ts`   | `ts` of the session's last event                             |
| `events`   | number of events in the session                              |
| `bytes`    | exact integer sum of `bytes` over the session                |
| `paths`    | number of **distinct** `path` values in the session          |

### Ordering

Output is in **close order**, not start order.

A session *closes* at the first moment the stream's watermark — the current
event's `ts`, or end-of-stream — exceeds `end_ts + IDLE_MS`. Emit sessions in
the order they close. Sessions that close on the same watermark advance are
emitted ordered by `(end_ts, user)` ascending.

## Limits

The program is run with:

- **`RLIMIT_AS` = 32 MiB**, soft and hard. Exceeding it is a `SIGKILL`, not an
  exception you can catch.
- `RLIMIT_NPROC` = 4, `RLIMIT_CPU` = 120 s, wall clock 180 s.
- stdin is the event stream; stdout is your answer; exit status must be 0.

The stream contains on the order of 1.2 million events and 225,000 distinct
users, but far fewer sessions are open at any one instant. **The limit is not
incidental to the task — it is the task.** A solution that keeps state for
every user it has seen will not fit; one that keeps state only for sessions
that can still be extended fits with room to spare.

Anything written to stderr is ignored. Nothing you print to stdout other than
session records is read as a result.
