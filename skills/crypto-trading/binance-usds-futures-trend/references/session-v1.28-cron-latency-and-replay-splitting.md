# Session v1.28: Cron latency and replay-splitting lesson

## What changed

A user asked why a single agent cron could not handle the full testnet workflow and then pointed out that a run scheduled for 22:05 Beijing time only notified at 22:17 Beijing time.

## Durable lesson

For this trading skill, the clean operational shape is:

- one agent-type hourly cron owns the end-to-end testnet trading flow;
- the hourly hot path should focus on preflight, reconciliation, cycle execution, and post-cycle snapshotting;
- runtime replay should usually live in a separate daily read-only analyzer cron.

This reduces notification latency and makes timing easier to reason about.

## Timing interpretation rule

When debugging slow cron delivery, distinguish:

1. scheduled trigger time;
2. actual execution-completion time from the cron output/runtime evidence;
3. message delivery time.

If there is no delivery error, late notification usually means the job itself was still running.

## Evidence from the session

- The cron job was scheduled at `5 * * * *`.
- The job output file was finalized at `22:17:14` Beijing time.
- The report contained intermediate timestamps for BTC cycle, Alt cycle, replay, and post-run signed snapshot, showing the work itself consumed the elapsed time rather than Telegram delivery failing.

## Follow-up guidance

If this behavior recurs, inspect the cron output file timestamp and the latest runtime/order journal timestamps before assuming the notification layer is delayed.
