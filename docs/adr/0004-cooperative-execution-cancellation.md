# ADR 0004: Cooperative execution cancellation

## Problem and context

RepoGym could stop a command only after its wall-clock timeout. API consumers could not react to
operator requests, application shutdown, or a superseded evaluation without abandoning the
worker and its child processes.

## Current behavior

`Executor.execute` blocked until completion or timeout. Timeout owned process-tree cleanup, but
there was no reusable cancellation signal or distinct cancelled result.

## Alternatives considered

- Expose the raw `Popen` object. This leaks backend details and lets callers bypass cleanup.
- Raise asynchronously into the execution thread. This is unsafe and not portable.
- Accept a thread-safe one-way token and poll it alongside the timeout deadline.

## Decision

The executor protocol accepts an optional `CancellationToken`. Cancelling it is idempotent. A
pre-cancelled token prevents launch; an active cancellation terminates the exact captured process
tree through the same terminate/wait/kill path as timeout. A process observed as completed wins
over a simultaneous cancellation signal. Results carry separate `cancelled` and `timed_out`
flags. Verification fails clearly when interrupted; grading persists a cancelled result and
starts no remaining test or quality commands.

## External behavior and compatibility risk

The new protocol argument is optional, so existing callers and commands behave unchanged.
Execution and grade result schemas gain backward-compatible `cancelled` defaults. Custom
executors need to accept the optional token before advertising support for cancellable calls;
RepoGym does not pass it when no cancellation was requested.

## Verification

Tests cover cancellation before launch, repeated cancellation, nested descendants, unrelated
process safety inherited from the shared cleanup path, timeout distinction, abnormal completion,
verification interruption, grading short-circuiting, and persisted evidence. The Windows and
Ubuntu CI matrix validates platform-specific process behavior.
