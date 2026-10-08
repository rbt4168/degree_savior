# System 2: hypothesis planning

Implements user step 3 after explicit topic selection, then automatically queues
[System 3](03-experiments.md). See [workflow](04-workflow-and-discord.md).

## Entry and provenance

Read the actual topic, survey, paper notes and validated evidence. Require the
latest user approval to match the exact current topic revision and evidence hash.
Preserve the user's instruction, question and authorized resources. A review
recommendation, translated report or delivered message does not grant approval.

Freeze each executable hypothesis as Markdown and canonical JSON in the local
`hypothesis/` directory. Record topic/campaign/approval IDs, evidence claims,
content hashes and plan provenance. Archived source is the contract for later
confirmation; do not alter it silently after observing results.

## Workable plan contract

| Element | Required content |
| --- | --- |
| Question | Mechanism, target setting, prediction, null and disproof conditions |
| Evidence | Validated paper claim IDs and relation to the proposed change |
| Implementation | Actual candidate, baseline, ablation, source and correctness checks |
| Inputs | Sources/hashes, preprocessing, splits, exclusions and data access |
| Units | Independent experimental unit, pairing, repetitions and seed policy |
| Evaluation | Primary metric/unit/direction, practical thresholds and guardrails |
| Analysis | Frozen comparisons, multiplicity, uncertainty and verdict rule |
| Reproduction | Fresh-process repeats, tolerance and raw-data reanalysis |
| Resources | Per-run and whole-campaign allocation, retries and stopping rules |

Specify what every comparison isolates and why the baseline is defensible.
Published algorithms must not be called reproduced without matched implementation
and evidence. Same evaluation cap does not imply equal consumed computation;
record cost dimensions beyond the frozen fairness contract.

The runner supports `equal_actual` evaluation counts or an explicit `common_cap`
contract. Use the former by default. Never pad measurements to fake equal budgets.
Define experimental units correctly: iterations or tasks within a shared training
run are not independent seed units. Keep development/smoke seeds separate from
confirmation and disclose modest sample size without inventing a power result.

## Validation and supported implementation

Validate schema, evidence references, workspace-safe relative paths, source ASTs,
available dependencies, run count and remaining campaign/hypothesis allocations.
Generated experiment code cannot install packages, access the network, spawn
processes or use prohibited dynamic execution. Optional NumPy/PyTorch imports are
accepted only when installed and included in the recorded environment.
The local runner monitors process RAM; CPU neural experiments are supported,
while a GPU allocation needs separately implemented monitoring and authorization.

A hash-checked reviewed local proposal can enter the same planner without a new
model-generated design. It must still pass current approval, evidence, schema and
source checks. Reviewed content is not a bypass or a fabricated measurement.

Prefer a small set of distinct falsifiable hypotheses. Match all stages, retries
and verification to the remaining allocation, rather than restarting the original
budget. Repair batches preserve parent evidence and usage, and freeze new seeds
before new confirmation. Invalid or exploratory historical data remain labelled.

## Handoff and changes

Valid plans queue experiments automatically; do not add another routine approval
gate. Record genuine blockers for missing inputs or unsupported designs.
Evidence/question changes invalidate the old selection. Explicit elapsed-time
extensions may retain the same unfinished campaign and frozen science; they do
not authorize changed data, models, thresholds or other resource dimensions.

Plan acceptance means the test is executable and interpretable, not that the
hypothesis is likely to win. Topic-specific algorithms, fitness functions,
sample counts and model configurations belong in local plans, never this shared
system specification.
