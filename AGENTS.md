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
- Send a completed interface action to Discord with `notify <summary>` using a
  Traditional Chinese summary. All notifications must use Traditional Chinese embeds.
  The worker
  already records and notifies each research action; avoid duplicating its events.
- Credentials are stored outside the repository; do not print them, add them to
  research artifacts, or pass them to experiment subprocesses.
- Synthetic validation fixtures are application tests. Never treat them as an approved
  research topic or a real scientific finding.
