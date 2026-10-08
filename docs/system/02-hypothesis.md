# System 2: hypothesis and verification planning

Implements user step 3 after topic selection. Automatically hands valid plans to System 3. Save plans in `hypothesis/`. See [workflow](04-workflow-and-discord.md) and [artifact templates](05-artifacts.md).

## Entry conditions

Read `topic/<topic-id>.md`, its survey, linked paper notes, and verified local PDFs. Require a persisted user approval matching the current topic revision and evidence bundle. Approval records the selected question and resource envelope. The coordinator checks it before any plan is generated and again before experiment execution.

Never infer approval from a positive novelty assessment, Discord delivery, elapsed time, or an unrelated approved topic. If the question or essential evidence changes, return to `AWAITING_SELECTION`. If ordinary feasibility details are missing, resolve them from the approved scope; record a blocker only when required input cannot be obtained.

## Outputs

Write one plan per hypothesis to `hypothesis/<topic-id>-<hypothesis-id>.md`. Each references its approved topic revision, evidence bundle, parent campaign, and plan revision. Plan content becomes immutable for a confirmatory run; edits create another revision and record why it changed.

The topic record also lists the campaign's hypothesis IDs and processing order. Planning is bounded by `max_hypotheses` and the shared budget. Prefer a small set of distinct explanations with discriminating tests rather than many minor parameter variants.

## Planning procedure

1. State the unresolved question and the mechanism expected to produce a useful result. Link this rationale to the survey and specific evidence.
2. Write a falsifiable hypothesis and explicit null or competing explanation. State when the hypothesis would fail and the conditions in which it is intended to apply.
3. Select a minimal implementation that can distinguish the proposed mechanism from the strongest relevant baseline. Identify reusable code, reference algorithms, data, and licensing/access requirements.
4. Define the experimental units, datasets or problem instances, controls, seed policy, train/validation/test roles where applicable, and exclusions. Separate development/tuning data from confirmatory evaluation.
5. Specify fair baseline and candidate budgets: objective evaluations, data access, tuning trials, compute, memory, and wall time as appropriate. Select the fairness criterion explicitly; record other resource dimensions as secondary metrics.
6. Freeze the primary metric, meaningful improvement threshold, guardrails, uncertainty method, comparison/test, multiplicity handling, sample size or repeat count, and verdict rule before seeing confirmatory results.
7. Define implementation checks, baseline reproduction, a smoke run, exploratory pilot, confirmatory runs, mechanism ablation, and robustness tests. State what each stage proves and what failure means.
8. Specify exact expected files, entry points, command arguments, configuration schema, output schema, runtime environment, dependencies, and analysis procedure. Before implementation exists, identify which commands must be created; the runner must validate them before execution.
9. Estimate total resources across all hypotheses, retries, baselines, ablations, and verification. Fit the whole campaign inside the approved envelope.
10. Validate completeness and internal consistency. Repair ordinary omissions automatically. Queue `PLAN_READY` plans for implementation without another routine human selection gate.

## Minimum contents of a workable plan

| Field | Required detail |
| --- | --- |
| Provenance | Topic ID/revision, approval ID, survey, evidence IDs/locators, hypothesis and plan IDs |
| Hypothesis | Mechanism, target setting, predicted effect, null/alternative explanation, disproof conditions |
| Implementation | Algorithm or intervention, baseline implementation, pseudocode, files to build/reuse, correctness checks |
| Inputs | Dataset sources and hashes, preprocessing, instance generation, splits, seed policy, exclusions |
| Evaluation | Primary metric and direction, practical threshold, secondary metrics, guardrails, fair resource allocation |
| Design | Experimental unit, paired/unpaired structure, repetitions, sample-size rationale, pilot/confirmatory separation |
| Analysis | Effect size, interval method, applicable statistical comparison, multiplicity policy, missing-data handling |
| Verification | Baseline reproduction tolerance, ablation, robustness criteria, rerun/reproduction requirements |
| Execution | Commands, configs, dependencies, output schema, timeouts, limits, cancellation/recovery behavior |
| Decisions | Conditions for supported, unsupported, inconclusive, blocked, and invalid outcomes |
| Resources | Per-stage and total estimates, finite retry cap, stop rule, campaign processing order |

For stochastic optimization, if selected as the domain, define objective direction, instance families, dimensions, evaluation budget, constraints, stopping rule, initialization, and seed pairing. Count independently generated instances or runs correctly; iterations within one optimization run are not independent samples. For other research domains, adapt the experimental unit and validation rules to that domain rather than forcing this example onto them.

## Scientific decision contract

The plan must define what counts as support before confirmatory execution. A typical rule requires the planned effect to clear a practical threshold with appropriate uncertainty, meet guardrails, pass mechanism checks, and reproduce under the prescribed rerun and robustness conditions. The exact rule belongs to the hypothesis; a universal p-value or seed count is insufficient.

If there is too little information to choose a confirmatory sample size, use a labeled pilot to estimate variability and cost. Pilot results cannot serve as confirmatory evidence. Freeze the finalized design after the pilot and use held-out confirmatory data/seeds as appropriate. Account for pilot resources in the approval envelope.

Exploratory parameter tuning and debugging may inform a new plan revision. Record which observations informed the change. Do not move thresholds after observing confirmatory outcomes and call the revised rule pre-specified. A materially different mechanism or research question returns to topic selection; execution details may be refined within scope with a documented revision.

## Automatic handoff and blockers

On successful validation, save the plan and its hash, emit `hypothesis.plan_ready`, and queue an experiment job carrying the immutable plan revision and approval ID. System 3 checks the guard again and starts implementation automatically.

If a required dataset is unavailable, a baseline cannot be identified, criteria are incoherent, or the plan exceeds approved resources, mark that hypothesis `PLAN_BLOCKED` with a concrete reason. Repair it within scope if possible; otherwise notify the user and include it in the eventual campaign report. Other independent valid hypotheses may proceed inside the same approved campaign. When none can proceed, write an incomplete/blocked campaign report rather than inventing an experiment.

## Notifications and acceptance

Send notifications when selection is accepted, hypothesis drafting starts, each plan/revision is saved, validation succeeds or fails, a blocker is found or resolved, and automatic experiment handoff occurs. Include IDs, the predicted effect, baseline, primary metric, pass rule, resource estimate, and artifact path in the plan-ready message.

Acceptance requires that missing or stale approval produces no plans; an approved topic produces a feasible falsifiable plan; a plan without baselines or frozen verdict criteria fails validation; and a valid plan automatically starts System 3. Confirm that changed confirmatory criteria create a new revision with contamination recorded rather than silently rewriting the old plan.
