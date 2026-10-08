# Installation and operating guide for coding agents

Use this guide for actual setup, updates and recovery. Keep commands here; the
README is the product introduction. Read [AGENTS.md](../AGENTS.md),
[the plan](plan.md) and [verification](verification.md) first.
Examples use Windows PowerShell from the project root. Other platforms use the
matching virtual-environment interpreter. A workspace elsewhere can be selected
with the global root option before the subcommand; never publish its actual path.

## Inspect and install

Reuse existing environments, credentials and research. Do not delete them to
reset an installation. Check Python 3.10+ and the installed Codex login:

```powershell
python --version
codex --version
codex login status
```

If needed, guide the user through local login:

```powershell
codex login
```

Create the environment only if missing, then install and initialize:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements.lock -e .
.\.venv\Scripts\python.exe -m research_automation init
```

Reasoning uses the installed Codex CLI/local login, without a pinned model.
Before replacing code or dependencies, inspect active work and stop/recover the
coordinator while preserving completed artifacts and owned process records.

## Credentials and limits

Doctor reports configuration presence and login state, never secret values.
It does not prove every scholarly provider is currently accessible:

```powershell
.\.venv\Scripts\python.exe -m research_automation doctor
```

Reuse configured values. For missing values, provide an interactive local terminal
with hidden input; do not request secrets in chat or command arguments:

```powershell
.\.venv\Scripts\python.exe -m research_automation configure-secret DISCORD_WEBHOOK_URL
.\.venv\Scripts\python.exe -m research_automation configure-secret OPENALEX_API_KEY
```

Run only the command needed. Noninteractive agents must direct the user to a local
interactive input rather than reveal the secret. Values can also live in ignored
workspace `.env`. Nonempty process environment wins, then workspace `.env`, then
the external local secret store. Quotes/comments/BOM and empty fallback are
supported; interpolation and automatic export to subprocesses are disabled.
OpenAlex uses a Bearer header. Verify actual provider access during research and
record failures; do not promise permanent key-free access.

`research.example.json` documents configurable finite defaults. Copy it only when
the ignored `research.json` is missing and authorized changes are needed. Defaults
include 300 sec/run, 4 GiB process RAM, 150 attempts, two campaign hours and 2 GiB
research storage. No paid compute is provisioned. Authorization must cover increases.

## Validate and start

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m research_automation start
.\.venv\Scripts\python.exe -m research_automation status
```

Check the actual owner PID/create-time and status. One workspace allows one worker;
reuse an existing owner. Tests use isolated synthetic fixtures, never real research
approval or live webhook traffic. Logs are under ignored `state/`; redact them
before sharing. Unattended execution requires the computer to stay on, connected
and awake. No automatic startup task is installed.

## Optional CPU neural dependencies

Stop or recover active work before changing dependencies. If the approved plan
needs them, install the optional versions from the declared sources:

```powershell
.\.venv\Scripts\python.exe -m pip install numpy==2.2.6
.\.venv\Scripts\python.exe -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip check
```

Restart the coordinator to expose installed versions to planning. Only installed
allowed scientific packages are accepted. Generated experiment code cannot install,
download or spawn processes. Use recorded deterministic seeds, thread limits and
costs. CPU RAM monitoring does not account for GPU VRAM. A small pilot is not a
reproduction of a large published neural model.

## Research intake and selection

A user's idea authorizes intake; discovery requires a request to find directions:

```powershell
.\.venv\Scripts\python.exe -m research_automation submit "The user's research idea"
.\.venv\Scripts\python.exe -m research_automation submit "Requested area and constraints" --discover
```

Choose the intended mode, not both. Exactly two pinned initial queries may be
provided when useful; subsequent refinement still obeys evidence and approval:

```powershell
.\.venv\Scripts\python.exe -m research_automation submit "Research question" --query "First search phrase" --query "Second search phrase"
```

Read actual topic/survey/notes and current evidence before explaining the result.
Only explicit user selection permits approval of the exact current revision:

```powershell
$topicId = "Selected topic ID"
$revision = "Verified current revision"
$userInstruction = "The original explicit user instruction"
.\.venv\Scripts\python.exe -m research_automation approve $topicId --revision $revision --instruction $userInstruction
```

Approval queues planning and experiments automatically. Preserve finite authorized
overrides through `--limits` JSON. For an unfinished existing campaign, add
`--campaign` and pass only a larger `max_campaign_seconds` to record a separate
user time decision. It keeps the original selection and frozen plan and does not
queue another campaign. Use proper native-argument quoting for JSON on the host
shell, or structured Python CLI arguments; verify the recorded parsed values.
Updated coordinators read amendments at guard checks. Preserve completed runs when
reloading an older coordinator. Other scope/resources require their own authorization.

Apply only the decision actually requested by the user:

```powershell
.\.venv\Scripts\python.exe -m research_automation revise $topicId "User's revised question"
.\.venv\Scripts\python.exe -m research_automation defer $topicId "User's deferral instruction"
.\.venv\Scripts\python.exe -m research_automation reject $topicId "User's rejection instruction"
.\.venv\Scripts\python.exe -m research_automation cancel $topicId "User's cancellation instruction"
```

Silence, delivery, setup consent and another topic's approval never select a topic.
Keep particular algorithms, experiments and session policies in ignored local files.

## Stop, recover and inspect

Stop waits for the active job; cancellation interrupts a selected topic:

```powershell
.\.venv\Scripts\python.exe -m research_automation stop
.\.venv\Scripts\python.exe -m research_automation status
```

After fixing a blocker and checking current approval/provenance, resume the actual
blocked/interrupted job and start a worker if needed:

```powershell
$jobId = "Actual recoverable job ID"
.\.venv\Scripts\python.exe -m research_automation resume $jobId
.\.venv\Scripts\python.exe -m research_automation start
```

Foreground draining is available only when no background worker owns the workspace:

```powershell
.\.venv\Scripts\python.exe -m research_automation worker --drain
```

Inspect research events and notification receipts without starting another sender:

```powershell
.\.venv\Scripts\python.exe -m research_automation events --limit 30
.\.venv\Scripts\python.exe -m research_automation notifications
```

Recovery preserves papers, decisions, plans, measurements and receipts. It adopts
validated completions and permits bounded infrastructure retries; do not retry valid
negative science for a favorable outcome or resume revoked approval.

## Discord reports and repair

English embeds/PDFs are for validated studies, syntheses, selectable topics,
experiment conclusions, final results and substantive intervention requests.
Starts/finishes, queueing, downloads, saves, per-run progress and maintenance stay
local. Let the worker deliver its outbox; avoid duplicate manual messages.

Persistent live preferences can narrow the implemented allowlist:

```powershell
.\.venv\Scripts\python.exe -m research_automation notifications --allow-actions paper.note_saved literature.report topic.awaiting_selection hypothesis.verified campaign.result workflow.blocked selection.stale_rejected
```

This updates preferences and pending content, not immediate delivery. Preserve
local events, receipts and retry timing. Reports place title/source/publication date
first; identifiers belong in title parentheses. Separate checked topics each get
one English PDF and one embed. Keep full comparisons in the PDF, not local paths
or standalone paper IDs in fields. PDF tables wrap within page width; local
attachments are capped at 1 MiB. Larger evidence remains local.

Inspect failures and repair access first. Stop the worker/sender before choosing
one manual delivery action:

```powershell
.\.venv\Scripts\python.exe -m research_automation notifications --flush
.\.venv\Scripts\python.exe -m research_automation notifications --replay
```

Then inspect receipts and restart. Ambiguous responses can cause duplicates;
delivery does not change scientific status. Historical non-English evidence stays
intact; English presentation copies must preserve claims, numbers, sources and
identifiers, and do not count as new reading or validation.

## User-authorized Git publication

Publish only when requested. Inspect working changes, tracked files and the exact
staged tree. Use explicit generic file/directory paths rather than staging the whole
workspace blindly. Check both tracked and new candidates for secret values, webhook
tokens, personal absolute paths and research-specific content. Include `.gitignore`
coverage for credentials, configuration, environments, all research directories,
`local/` and `state/`. Ignore rules do not protect already tracked files.

```powershell
git status --short
git diff --check
git diff --cached --stat
git diff --cached --check
git ls-files
```

Do not delete local studies to make status clean. Preserve old private documentation
locally before replacing it with generic material. Run relevant tests and checks,
commit only the reviewed public changes, push to the intended remote/branch and
verify the remote commit. System maintenance remains local, not a Discord report.
