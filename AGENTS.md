# Research interface integration

This workspace implements the three systems in docs/plan.md. Use the installed local
CLI to connect this chat interface to the persistent worker. On Windows the interpreter
is `.venv/Scripts/python.exe`; run `python -m research_automation --root <workspace>`
with that interpreter. The console alias `research` is also installed in the venv.

For setup, updates, recovery, and command examples, read
[docs/installation-guide.md](docs/installation-guide.md). Keep executable commands
in that guide; README.md is the user-facing introduction and agent setup message.

- A user's research idea authorizes `submit <idea>`. A request to find ideas uses
  `submit <research-area> --discover`. Start the worker with `start` if needed.
- Inspect `status`, the topic Markdown, survey, and paper notes before summarizing
  findings. Use the actual files, not remembered model output.
- Topic approval belongs to the user. **Never run `approve` unless the user explicitly
  selects that topic for hypothesis planning and experiments.** Identify the topic and
  exact current revision; preserve the user's original instruction in `--instruction`.
  If the choice is ambiguous among topics or changed questions, clarify it first.
- `approve <id> --revision <revision> --instruction <user-instruction>` automatically
  queues planning and experiments. Do not add another routine approval gate at step 3.
- Follow user requests to reject, defer, revise, cancel or resume through the CLI.
  Resume cannot bypass stale or revoked approval. Increased limits must reflect an
  explicit user-authorized budget, passed as JSON to `approve --limits`.
- Discord is for research actions only: literature, topic selection, hypotheses,
  experiments, findings, and research blockers. Keep setup, code/document edits,
  general interface completion, and worker lifecycle updates local. The worker
  already notifies research events with Traditional Chinese embeds; avoid duplicates.
- Keep routine analysis start/end/reuse, file downloads/validation/reuse, and file
  saves local as well. Still notify selectable topics, research findings/results,
  and substantive evidence or workflow blockers.
- Exception: notify validated single-paper analysis completion with its question,
  contribution, findings, limitations, source, and PDF study report. Generic agent
  completion remains silent. Send requested research progress reports as PDF
  attachments with Traditional Chinese embeds; mark unverified directions clearly.
- When a checked topic becomes selectable, send its question, related work,
  bounded gap, limitations, and topic ID/revision to Discord. A preliminary lead or
  evidence-blocked review is not a verified candidate; keep the selection gate.
- Credentials resolve from the process environment, the ignored workspace `.env`,
  then the external local secret store (nonempty values win). Never print values,
  add them to research artifacts or Git, or pass them to experiment subprocesses.
- Synthetic validation fixtures are application tests. Never treat them as an approved
  research topic or a real scientific finding.
