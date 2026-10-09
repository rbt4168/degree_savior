# Diagnostic recovery after an uncertain or invalid result

This is a required coding-agent workflow after a recorded `INVALID` or
`INCONCLUSIVE` hypothesis or campaign result. Apply it automatically within the
current approved question and remaining resources. Do not wait for the user to
request each diagnostic. Follow [execution rules](03-experiments.md),
[approval and recovery](04-workflow-and-discord.md) and
[artifact contracts](05-artifacts.md).

The goal is to determine whether the experiment can meaningfully test its
hypothesis, including whether a valid negative result is credible. A diagnostic
supports a parameter choice or implementation assumption; it does not establish
that the research hypothesis is supported. Never keep changing settings until a
favorable result appears.

## Trigger, preservation and diagnosis

1. Read the actual frozen plan, executed source, inputs, manifests, measurements,
   statistical analysis, audit and result. Check actual worker/process state and
   existing diagnostic records before dispatching work, avoiding duplicate runs.
2. Preserve the original verdict, all attempts, logs and reports. Identify whether
   the problem is an implementation/design failure, leakage or unfair comparison,
   incomplete execution, insufficient learning/search, missing measurements,
   sampling uncertainty, or a valid small/mixed effect. Rank suspected causes
   using cited evidence rather than the desired conclusion.
3. Audit **every experiment parameter**, including inherited defaults, hidden
   sampler/decoder settings and derived counts. Compare the intended value and
   units with the effective value actually executed. Trace values through source
   and run manifests rather than relying on the narrative plan.
4. Build a parameter-evidence ledger. Reuse valid prior small experiments when
   their implementation, data regime and parameter interactions match. Record
   missing evidence explicitly and automatically plan the smallest meaningful
   experiments to fill it. Do not rerun a valid diagnostic solely for a better score.

## Parameter-evidence ledger

For every parameter, record its name, stage, intended/effective value and unit,
why it matters, linked diagnostic protocol/source/raw result, applicability to
the main experiment, pass criterion, observed estimate and uncertainty, status,
and proposed action. Use `PASS`, `FAIL`, `UNTESTED` or `CONSTRAINED` for parameter
checks, keeping these separate from scientific hypothesis verdicts.

`CONSTRAINED` requires an explicit explanation: a user-fixed setting, physical
limit, mathematical convention or policy choice may not admit a meaningful
empirical optimum. Verify its execution and consequences instead of claiming a
small experiment proves it optimal. Missing, failed or inconclusive diagnostics
remain visible; do not fill the ledger with assumed passes.

| Parameter group | Required diagnostic evidence where applicable |
| --- | --- |
| Data | Distinguish independent tasks, observations per task, original/generated/total counts, and actual unique structures. Check generator constraints, depth/complexity, constants, noise, sparsity, support and train/test distribution. Verify splits and leakage independently. |
| Search or induction | Check representation and fitness against independently known cases. Sweep population, generations/evaluation calls and sample counts; measure success rate across independent seeds, including whether the target property exists in retained elites and whether the deployed selection actually chooses it. |
| Generation | Test rule membership, termination, diversity, distribution fidelity and executable input/output consistency. Distinguish newly generated instances from new independent source observations. |
| Model and training | Check model size/capacity, encoder/decoder, objective, optimization, batch size, training budget and diffusion/sampling settings. Measure reconstruction or task performance over a small sample-count and training-budget study; verify the baseline can learn a suitable positive control. |
| Evaluation and analysis | Check numerical versus structural recovery, inference/selection/constant-fitting rules, held-out complexity, independent repetitions, metric implementation, intervals, practical thresholds and fairness dimensions. Verify inference uses only permitted information. |
| Runtime and resources | Verify completed updates/generations, checkpoints and logging, actual CPU/GPU use, memory, time and storage, including preprocessing, generation, training and inference. Diagnose premature stopping separately from scientific failure. |

Write training units explicitly: epochs, optimizer updates, examples presented,
diffusion noise steps and inference steps are different quantities. Record their
relationship for each arm using its actual dataset size, batching and sampling
scheme. Matching optimizer updates does not mean matching epochs or total compute.
Never silently reinterpret an ambiguous user-specified unit; ask if the intended
setting cannot be established from the recorded instruction.

## Small experiment design and execution

Before each batch, freeze its diagnostic question, applicable parameter subset,
candidate values, data/splits, independent seeds, controls, metric, pass/fail
criterion, resource allocation and stop rule. Record exploratory choices honestly;
post-result diagnostics do not become preregistered main-experiment evidence.

Use focused sweeps to find an adequate supported operating range, rather than
exhaustively crossing every parameter. Check important interactions, especially
sample count versus search effort, data complexity versus model capacity, and
dataset size versus training effort. Small experiments must retain the structural
or sparse-data conditions that matter to the hypothesis; success on trivial cases
does not validate a harder target regime. Label reduced-scale limitations.

Use known-generating-process benchmarks and independent verification algorithms
when appropriate to measure structural recovery. Ground truth may evaluate a
diagnostic, but cannot select the learned rule/model for the main experiment.
Report success counts with denominators and seed uncertainty. Finding the correct
structure somewhere in the population differs from selecting it by the declared
fitness. Numerical fit alone does not establish structural identity.

Exercise each pipeline stage and its handoff before another expensive full run.
Tests with known expected answers can verify software or statistical formulas;
label them as validation fixtures, never as evidence that the research works.
Empirical parameter adequacy requires actual measurements on a relevant diagnostic
benchmark, including baseline behavior and failures. Inspect both output streams
and saved results, not only process exit codes or generated assertions.

Reuse the installed supervisor, sanitized environment, approval guards and
durable records where applicable. The current worker does not automatically
implement arbitrary domain-specific sweeps: the coding agent must prepare and
verify a suitable local diagnostic harness when the existing runner is insufficient.
Do not claim unattended diagnostics are running merely because these instructions
exist. Resume matching completed checks after interruption without overwriting them.

## Decisions, user help and stopping

After the bounded checks, explain which settings are adequate, which failed, and
which remain unverified. Repair demonstrated implementation faults or propose
settings supported by the diagnostics; preserve the prior frozen plan and record
all changes. Recheck parameter interactions affected by a change. A large rerun
requires applicable diagnostic evidence and resolved essential validity failures.

Freeze a new follow-up plan before independent confirmation. Use confirmation
data and seeds not consumed by diagnostic selection; do not merge exploratory
measurements into the original confirmatory statistics. A new result has its own
provenance and cannot retroactively overwrite the earlier verdict or thresholds.
Changing the research question or evidence requires current-revision selection.

Continue routine checks within current authorization without a second approval
gate. Ask the user when an ambiguity changes the scientific comparison, a setting
conflicts with an explicit user constraint, needed inputs/domain knowledge are
missing, or meaningful checks require additional resources or revoked/stale
approval. Give the concrete evidence, unresolved choice, recommendation and
estimated compute requirements; do useful independent checks while awaiting a
reply. Record authorized increases through the approval CLI. Never treat silence
as permission or automatically increase budgets.

Bound the diagnostic rounds and resources in advance. Stop when the relevant
parameter checks are adequate, the evidence reveals a valid limitation, or further
work cannot resolve the uncertainty within authorization. If evidence stays
uncertain, retain `INCONCLUSIVE` and describe what would resolve it; if essential
validity still fails, retain `INVALID`. Diagnostics need not produce `SUPPORTED`.
A valid `NOT_SUPPORTED` result does not trigger repeated tuning for a win.

## Research record and reporting

Store the ledger and diagnostic design under `local/<topic>/diagnostics/`, execution
and raw artifacts under `experiments/<topic>-diagnostics-<diagnostic>/`, and a
combined Markdown/PDF report under `results/`. Retain parameter grids, repetitions,
success counts, failures, resource use, analysis source, applicability limits and
the rationale for each accepted or rejected change.

Report substantive diagnostic findings, experimental conclusions and requests for
human intervention using the existing English report/Discord contract. Routine
starts, checkpoints and file saves stay local. Include the ledger and complete
recovery history in the topic archive after any subsequently confirmed
`SUPPORTED` or `NOT_SUPPORTED` conclusion.
