# Shared workflow and Discord contract

Shared infrastructure for the three [research systems](../plan.md).

## Durable coordinator

SQLite stores generic typed records, jobs, artifact hashes, append-only events
and an outbox. One exclusive worker lock prevents concurrent coordinators for a
workspace. Queue state and real process identity, rather than chat claims,
establish whether unattended work is active.

State changes and their event/outbox rows can share a database transaction.
File publication uses temporary writes and atomic replacement; recovery reconciles
pending publications because files and SQLite cannot commit atomically together.
Matching finalized files can be adopted, while changed/orphan files need inspection.
Stable entity/content keys deduplicate known actions without hiding changed inputs.

```text
REVIEWING → AWAITING_SELECTION → APPROVED → PLANNING → EXECUTING → COMPLETED
REVIEWING → COVERED | UNRESOLVED | EVIDENCE_BLOCKED
AWAITING_SELECTION → REJECTED | DEFERRED | REVIEWING (user revision)
PLANNING | EXECUTING → BLOCKED | PARTIAL | CANCELLED
```

Scientific outcomes belong to hypotheses, independently of workflow status.
`COMPLETED` means processing finished, not that science succeeded.

## Human selection and budget decisions

Require the latest decision to be a user approval for the current topic revision,
question and evidence hash. Recheck document hashes and approval before planning,
execution and guard checks. Silence, recommendations and delivery never approve.
User revision, rejection, deferral or cancellation revokes incompatible work.
Resume cannot bypass stale evidence, current decisions or resource limits.

Explicit time extensions for an unfinished campaign use a separate persisted
decision with the user's instruction, old/new limits and original approval link.
Only elapsed time changes; original selection, frozen source/seeds/thresholds,
usage and other caps remain. Running updated coordinators read changes at guards.
Recovery of an older coordinator must retain completed measurements.

## Notification allowlist

Use English embeds for content or decisions, with English PDFs where available.
The implemented allowlist is:

| Action | Content |
| --- | --- |
| `paper.note_saved` | Validated individual paper study with PDF |
| `literature.report` | Substantive literature/topic/progress report |
| `topic.awaiting_selection` | Checked current candidate and selection PDF |
| `hypothesis.verified` | Experimental conclusion and validity limits |
| `campaign.result` | Complete campaign result and PDF |
| `workflow.blocked` | Substantive research issue needing intervention |
| `selection.stale_rejected` | Request to choose the current revision |

Unknown actions, starts/finishes, queueing, screening, tracing, download/save/reuse,
per-run events, duplicate result-save events, setup and maintenance remain local.
The paper-study exception reports findings, not an analysis-completed announcement.
Live workspace policy can narrow the allowlist; both recording and sending read
it. Filtering preserves local events, sent receipts and retry history.

Titles describe the report or needed decision and place an identifier in
parentheses. Paper title/source/publication date come first; retain verified date
precision and distinguish preprints. Do not put standalone paper IDs, full local
paths or credential values in report fields.

Each checked selectable topic revision gets one PDF and one bounded embed. Full
comparisons remain in the attachment. Recheck current evidence/revision before
publishing, deduplicate topic/revision delivery and keep separate-topic batch
reports local. Selection delivery never authorizes planning.

## Sending, retries and attachments

The worker's sender owns delivery. Do not run another manual flush concurrently.
An event/part row records pending or terminal status, attempt count, next retry,
error and confirmed Discord message ID. Markdown/PDF references are workspace-safe
relative paths; current research reports use PDF attachments with a local 1 MiB
limit. Oversized/unavailable attachments are reported or omitted with a visible
explanation, rather than claiming they were delivered.

Respect HTTP 429 retry timing; retry transient network/server failures finitely.
Permanent rejection remains inspectable. A connection failure after Discord
accepted a request can produce duplicates; stable event IDs and receipts help
identify them but cannot guarantee exactly-once remote delivery.

Notification failure does not change approval or scientific results. Approved
work can continue within the finite backlog cap, then must stop if durable
notification state or backlog cannot be managed. Never discard required reports.
The webhook is outbound only; topic decisions come through the chat/CLI.

## Credential and publication boundary

Resolve nonempty values from environment, ignored workspace `.env`, then external
local secrets. Do not print, commit, embed or pass webhook/API values to experiment
children. Use sanitized child environments and redact diagnostic messages.
Keep personal paths and runtime manifests in ignored research state. Public docs
and source use generic configuration and relative workspace examples.

## Acceptance

Exercise stale approval, restart at selection, interrupted publication/process,
cancel/recover, budget exhaustion, confirmed send, 429, timeout, permanent error,
large Unicode reports and replay. Preserve completed evidence and receipts;
fixtures demonstrate application behavior, not scientific findings.
