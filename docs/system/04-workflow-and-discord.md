# Shared workflow, human selection, and Discord notifications

This is shared infrastructure for the three systems, not a fourth research phase. See the [overall plan](../plan.md).

## Coordinator and persistent state

Use one local worker and SQLite initially. Persist jobs, topic revisions, approval decisions, campaign budgets, hypothesis/run records, artifact manifests, checkpoints, events, and an outbox. Save each meaningful action's state change and event/outbox entry in one transaction. A proposed minimal schema is:

| Record | Key fields |
| --- | --- |
| `jobs` | ID, phase, owner lease, status, attempt, next eligible time, checkpoint, error |
| `topics` | ID, revision/hash, evidence bundle hash, review decision, workflow status |
| `decisions` | ID, topic/revision, evidence hash, approve/reject/defer/revise, actor, original instruction, scope, limits, timestamp |
| `campaigns` | ID, approval ID, budget limits/usage, hypothesis order, status |
| `hypotheses` | ID, topic/campaign, plan revision/hash, workflow status, scientific outcome |
| `runs` | ID, hypothesis/plan, stage/attempt, process identity, config hash, status, manifest path |
| `artifacts` | Relative path, type, content hash, producer, revision, validation status |
| `events` | Stable event ID, sequence, timestamp, action, entity IDs, outcome, summary, artifact references |
| `outbox` | Event/part ID, payload hash, pending/sending/sent/dead status, attempts, next attempt, message ID |

Publish files with temporary writes and atomic rename, recording their expected hashes in an action checkpoint. Filesystem writes and SQLite commits are not one transaction: after a crash, reconcile finalized files against pending checkpoints before marking the action complete. An unmatched file is an orphan to inspect, not automatic proof that work succeeded.

Use an exclusive lease and compare-and-set transitions to prevent duplicate workers. A restart recovers unfinished jobs, validates committed artifacts, inspects stale process ownership, and replays the outbox. Idempotency keys combine entity ID, action type, and input revision/hash. A changed input creates a new action rather than falsely reusing old output.

## Workflow and selection gate

```text
IDEA_RECEIVED -> REVIEWING -> AWAITING_SELECTION
REVIEWING -> COVERED | UNRESOLVED | EVIDENCE_BLOCKED
AWAITING_SELECTION -> APPROVED | REJECTED | DEFERRED
AWAITING_SELECTION --revise--> REVIEWING (new revision)
APPROVED -> PLANNING -> EXECUTING -> VERIFYING -> COMPLETED
PLANNING | EXECUTING | VERIFYING -> BLOCKED | PARTIAL | CANCELLED
```

Individual hypotheses have separate planning/execution states and scientific outcomes. A campaign may execute and verify hypotheses sequentially; the topic's aggregate status does not imply every hypothesis is in the same stage. Keep review decisions, workflow statuses, and scientific verdicts separate.

Approval enforcement:

```text
require latest decision.action == approve
require decision.topic_id == current topic.id
require decision.topic_revision == current topic.revision
require decision.evidence_hash == current evidence bundle hash
require planned action fits decision.scope and decision.resource_limits
require campaign is not cancelled, rejected, or deferred
```

The interface resolves a user selection into an explicit record and returns the selected ID/revision to the user. Ambiguous selection among multiple topics requires clarification. Persist the original user instruction and actor; agents cannot author their own approval records. Check the guard before generating plans, creating execution jobs, and starting queued execution.

User silence does not change state. Selection notifications may be retried, but retrying does not authorize continuation. Reject/defer/cancel decisions stop dependent queued jobs and request cancellation of running jobs. A routine report/formatting edit does not invalidate selection; material changes to the question or evidence set do. Compute a canonical topic revision and evidence bundle hash from relevant content rather than volatile status timestamps.

## Budget and recovery contract

All limits are finite and durable: search queries/candidates/full texts/time, hypothesis count, experiment attempts/time/parallelism, disk use, agent/API spend, and paid compute. Reserve budget before dispatch; reconcile actual usage after completion. Include retries and verification runs in estimates. Pause expensive dispatch if limits would be exceeded, save a truthful partial report, and request a specific scope/budget decision when necessary.

Track owned process identity using more than a reusable PID, such as creation time and run ID. Only terminate the process tree launched by that run. Resume completed actions from validated artifacts. Maintain an append-only decision/event history even when artifacts receive newer revisions.

Status requests expose current phase, selection state, active jobs, completed artifacts, resources used/remaining, blockers, and pending/dead Discord deliveries. The implementation's worker must run independently of the chat turn; document how it is started and stopped when built.

## What "every single thing" means

Send one distinct event notification for each meaningful attempted/completed workflow action. Starts and terminal outcomes are separate events for long actions. Do not collapse individual paper or run outcomes into only a milestone summary. Streaming tokens, low-level reads, and every optimizer iteration stay in local logs; the notification units are auditable actions and artifacts.

| Phase | Required notifications |
| --- | --- |
| Intake | Idea accepted; discovery started; each candidate idea saved |
| Literature | Query started/completed/failed; each candidate screened/reused/excluded; PDF acquired/validated/reused/failed; note saved; survey saved; each comparison/refinement; review decision |
| Selection | Selection requested; approval/rejection/deferral/revision recorded; stale approval rejected |
| Planning | Planning started; each hypothesis drafted/revised; each plan saved/validated/blocked; execution queued |
| Implementation | Preparation; each coherent implementation change; each correctness check; baseline reproduction; smoke/pilot outcomes |
| Experiments | Each run queued/started/completed/failed/timed out/retried/cancelled; progress heartbeat for long runs; checkpoint saved |
| Analysis/results | Analysis saved; each verification outcome; each hypothesis verdict; report saved; campaign completed/partial/blocked/cancelled |
| Operations | Worker recovery; job error/recovery; budget limit; user cancellation/resume; notification backlog recovery |

Default long-action heartbeat: at most one per active action every five minutes, containing elapsed time and measurable progress. Polls do not generate messages. Notification-send attempts are recorded locally and do not recursively notify about themselves; backlog recovery gets one summary event after delivery works again.

## Webhook configuration and payload

Read `DISCORD_WEBHOOK_URL` from the coordinator's environment or ignored local secret store. Use the destination supplied by the user in this conversation. Persist neither the URL nor its token in the state database, research artifacts, tracked files, request logs, or child-process environments. Redact URLs and sensitive headers from exception text. A sample config uses a placeholder only.

Each message uses a Traditional Chinese embed with a stable event ID, sequence number, UTC time, phase/action, topic/hypothesis/run IDs where applicable, outcome, brief findings, artifact paths, and next state. Keep source titles, identifiers and paths literal. Research natural-language output is requested in Traditional Chinese. Sanitize mentions with `allowed_mentions: {"parse": []}`.

```json
{
  "embeds": [{
    "title": "論文研讀筆記已儲存",
    "description": "全文研讀與逐頁證據核對已完成。",
    "color": 3447003,
    "fields": [{"name": "論文編號", "value": "p-003", "inline": true}, {"name": "研究檔案", "value": "papers/p-003.md", "inline": false}],
    "footer": {"text": "事件 evt-0042 · 序號 42"}
  }],
  "allowed_mentions": {"parse": []}
}
```

Execute the webhook with `wait=true`; record the returned message ID only after confirmed success. Validate embed description, field and total text limits, and split longer events into numbered parts. The implementation keeps descriptions below 3,500 UTF-16 units, field values below 900, at most 25 fields, and aggregate text below a conservative 5,500-unit ceiling. Final result reports up to the local 1 MiB attachment policy accompany the embed summary; an upload-size rejection falls back to the summary without losing the local report. Incoming webhooks send channel messages; receiving approval from Discord would require a separate inbound integration. See the [official webhook reference](https://docs.discord.com/developers/resources/webhook) and [embed limits](https://docs.discord.com/developers/resources/message#embed-limits).

## Reliable delivery

1. Persist a sanitized payload in the outbox with the research state transition. The action is locally committed even if Discord is unavailable.
2. A single sender drains messages in sequence. Respect current per-route/global headers; do not hard-code a universal webhook rate. A `429` uses `retry_after` or `Retry-After`. See [Discord rate limits](https://docs.discord.com/developers/topics/rate-limits).
3. Use a finite request timeout and bounded exponential backoff with jitter for connection errors and eligible server failures. Proposed initial policy: 20-second timeout, five automatic transient retries, backoff starting at two seconds and capped at sixty seconds. Server-directed rate-limit waits use their specified time and are persisted, not busy-waited.
4. Invalid payloads are repaired once if possible. Invalid/deleted credentials or other permanent failures become `dead` deliveries with a local blocker and visible status; do not retry forever or lose the event.
5. After transient retries are exhausted, retain the message for explicit replay or recovery with a clear delivery status. A repaired destination can replay undelivered messages using their original event IDs.
6. An ambiguous timeout may happen after Discord accepted a message. Retrying can therefore duplicate it. Guarantee durable at-least-once attempts and visible deduplication IDs, not exactly-once delivery. Deduplicate locally after a confirmed message ID; explain possible duplicates on replay.

If the outbox cannot be durably written, stop new work until local recording recovers. If only Discord is down, continue already approved work within a finite configured backlog limit, then stop dispatching new actions until delivery/backlog management recovers. Never drop notifications silently. Preserve the final result and mark delivery pending; show scientific completion and delivery completion separately.

## Focused acceptance

Exercise missing/stale approval, restart while awaiting selection, crash between file rename and state commit, worker crash during an active subprocess, cancellation, and budget exhaustion. For delivery, exercise success, `429`, server error, ambiguous timeout, permanent rejection, oversized message parts, and replay. Verify every required action has a durable event/outbox record, experiments are not duplicated, and neither logs nor artifacts contain the webhook token.
