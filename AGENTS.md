# Research interface integration

This workspace implements the three systems in [docs/plan.md](docs/plan.md).
Use its installed CLI to connect the chat interface to the persistent worker.
On Windows use `.venv/Scripts/python.exe`; on other platforms use the workspace's
virtual-environment interpreter. Operating commands belong in
[docs/installation-guide.md](docs/installation-guide.md), not the README.

## Intake and approval

- A user's research idea authorizes intake; a request to find ideas authorizes
  discovery within the requested area. Start the worker when needed.
- Read actual status, topic, survey and paper notes before summarizing findings.
- Never approve without explicit user selection of the exact current topic
  revision. Preserve the original instruction and scope. Clarify ambiguous choices.
- Approval automatically queues planning and experiments. Do not add a routine
  second approval gate between planning and execution.
- Revise, reject, defer, cancel and resume through the CLI according to the user.
  Recovery cannot bypass stale or revoked approval. Record explicitly authorized
  budget increases through the approval CLI and its limits argument.
- An existing unfinished campaign can receive an explicit elapsed-time extension
  without changing its original selection, frozen scientific plan or other caps.

## Evidence and reporting

- Honor the workspace literature policy. Under major-venue-only policy, only
  independently verified selected conference/journal publications supply hard
  evidence; all other sources are supplements. Publication identity and full-text
  validation are separate checks. Missing evidence never proves no research gap.
- Preserve the user's detailed question and refinements in reading and synthesis.
  Inspect methods, assumptions, actual experiments and limitations, not keywords.
- Describe novelty as a bounded recorded review. Disclose incomplete coverage and
  unavailable close work. Do not manufacture citations, measurements or findings.
- Use English for research summaries, embeds and PDF reports. Retain technical
  terminology, source titles, identifiers, dates, units and evidence excerpts.
- Each checked selectable topic gets one English PDF and one concise embed for
  its current revision. A preliminary lead is not a verified candidate.
- Validated paper studies include question, contribution, findings, limitations,
  source and PDF. Put title/source/publication date first; retain date precision
  and distinguish preprint dates. Put the identifier in parentheses in the title.
- Notify only validated paper studies, literature/topic reports, selection,
  experiment conclusions, results and substantive intervention requests.
  Routine starts, finishes, queueing, downloads, saves and maintenance stay local.
  Unknown actions default to silence. Follow persistent notification preferences.
- The worker owns queued Discord delivery. Do not flush a second sender while it
  runs. Inspect actual receipts; delivery is distinct from scientific completion.

## Local data and publication

- Read `local/research-instructions.md` when present for session-specific policy.
  Keep topic-specific designs in ignored local research directories. Shared docs
  describe reusable behavior and must not encode one user's research topic.
- Credentials resolve from nonempty process environment, workspace `.env`, then
  the external local secret store. Never print values, publish them, put them in
  research artifacts or pass them to experiment subprocesses.
- Preserve completed papers, decisions, frozen plans, measurements and receipts
  on update or recovery. Synthetic validation fixtures are application tests,
  never approved topics or scientific findings.
- Git publication requires user authorization. Stage explicit generic application
  files and inspect the complete proposed tree. Exclude local studies, topics,
  experiments, results, state, credentials and personal absolute paths. Keep
  executable publication checks in the installation guide.
