# System 3: experiment execution and verified results

Implements user step 4. Work in `experiments/<topic-id>-<hypothesis-id>/`. Consume validated plans from [System 2](02-hypothesis.md), preserve the [artifact contract](05-artifacts.md), and use the [shared coordinator and notifier](04-workflow-and-discord.md).

## Entry conditions and campaign behavior

Require a `PLAN_READY` hypothesis, immutable plan revision, current topic approval, accessible inputs, and remaining campaign budget. Recheck approval before queued work starts. Process hypotheses in the priority order recorded by System 2; begin with one experiment process at a time to keep resource accounting and recovery simple.

Complete all planned hypotheses unless a pre-specified campaign stopping rule, cancellation, essential blocker, or resource limit prevents it. Finding one supported hypothesis does not silently discard the others. Immediately report its verified outcome, and later send the complete campaign report. When all hypotheses fail to obtain support, still save and deliver the complete result.

## Execution stages

1. **Prepare.** Copy or link the frozen plan and input manifest into the work directory. Create an environment lock, record machine/accelerator details and source fingerprints, validate datasets/checksums, and reserve finite resources. Give every execution attempt a distinct run ID.
2. **Implement.** Build candidate and baseline entry points, config files, metric extraction, and analysis scripts. Reuse trustworthy reference code when suitable, recording exact revision and any modifications. Emit an implementation-change event for each coherent completed edit.
3. **Check correctness.** Verify algorithm invariants, objective/metric direction, constraints, known small examples, data separation, seed application, and output schema. Appropriate checks target scientific failure modes, not merely successful process exit.
4. **Reproduce baselines.** Compare against reported/reference behavior under compatible settings and an explicitly documented tolerance. If exact reproduction is impossible, explain the setting difference and validate a defensible comparison. An unexplained baseline failure blocks a positive comparative claim.
5. **Smoke test.** Use a cheap configuration to detect crashes, NaNs, invalid metrics, missing logs, unexpected resource use, and leakage. Smoke outcomes do not count as confirmatory evidence.
6. **Pilot and tune if specified.** Use development data and pilot seeds. Record all trials and freeze any allowed final plan revision before confirmation. Keep tuning budgets fair. Implement and validate generated commands against the frozen specification.
7. **Run confirmation.** Execute the planned run matrix, baselines, ablations, and robustness conditions. Record each run start/completion/failure, immutable config, seed, timestamps, stdout/stderr, exit status, resources, and raw metrics.
8. **Analyze.** Produce tables, figures, effect estimates, intervals, statistical comparisons where applicable, and guardrail checks from preserved raw data using a rerunnable script. Keep every attempted run and distinguish permitted exclusions, infrastructure failures, and scientific negative outcomes.
9. **Verify in detail.** Recompute summaries from raw metrics, audit fairness and data separation, inspect anomalies, rerun the prescribed confirmation from a clean environment, and check the mechanism ablation and robustness requirements. Judge the evidence against the frozen criteria.
10. **Report.** Write the complete result, update all hypothesis statuses, emit result and campaign events, and send a useful Discord summary. Notification delivery state is recorded separately from scientific completion.

## Reproducibility record

Each `runs/<run-id>/manifest.json` records campaign/topic/hypothesis IDs, approval and plan revisions, stage, attempt index, source revision or content hashes, dependency lock hash, machine details, exact command and working directory, sanitized environment allowlist, input/data/config hashes, seeds, start/end times, status, exit code, elapsed time, peak resource measurements where available, and relative artifact paths.

Do not rely on a Git commit alone: record dirty-source fingerprints when relevant, and use a source snapshot/hash when Git is unavailable. Do not pass the webhook or unrelated credentials into experiment subprocesses. Preserve raw outputs and analysis code so another execution can recreate the result without the agent's memory.

Every attempt gets a new directory. A retry may replace an infrastructure-invalid measurement only under the plan's pre-specified retry policy, with the original retained. Never retry a valid unfavorable outcome just to obtain a favorable one. Checkpoints are reusable only when code, inputs, config, environment, and plan hashes match and the algorithm supports valid resumption.

## Detailed support checklist

Before marking `SUPPORTED`, verify all applicable items:

- Correct implementation and valid measurements; no unexplained baseline reproduction failure.
- Same evaluation inputs and comparable declared budgets for candidate and baselines; report other resource differences.
- Primary outcome meets the frozen practical threshold and uncertainty/comparison rule, with appropriate independent units and multiplicity handling.
- Repeated runs and required conditions support the scoped claim; report variability and per-condition failures rather than only a favorable aggregate.
- Ablation or other discriminating check supports the claimed mechanism; confounding changes are isolated.
- No leakage from tuning into confirmation, selective exclusions, silent dropped failures, or retrospective threshold adjustment.
- Independent clean rerun/recomputation meets predeclared reproducibility tolerance; independence means a fresh execution/analysis path, not a second agent agreeing with a summary.
- All evidence, scripts, configs, manifests, and limitations are linked in the report.

If a check is inapplicable, the plan must explain why. A supported result is scoped evidence for a hypothesis, not a universal proof or a guarantee of publication novelty.

## Outcomes

| Outcome | Meaning |
| --- | --- |
| `SUPPORTED` | All planned support and detailed verification criteria pass within the stated setting |
| `NOT_SUPPORTED` | Valid completed tests fail the planned support criteria; report whether evidence favors the null or only lacks support |
| `INCONCLUSIVE` | Valid evidence is insufficient, uncertain, or mixed under the planned rule |
| `INVALID` | Implementation, data, or evaluation defects make the scientific measurement unusable |
| `BLOCKED` | Required resources, inputs, or environment are unavailable |
| `CANCELLED` | User stops the work; retain partial evidence |

Infrastructure failure and scientific failure are separate. Exhausting a budget without adequate measurement is `INCONCLUSIVE` or `BLOCKED`, not `NOT_SUPPORTED`. A valid null result with sufficient evidence can be informative, but lack of statistical significance alone does not prove equivalence.

Campaign statuses are `COMPLETED`, `PARTIAL`, `BLOCKED`, or `CANCELLED`. The report lists every planned hypothesis and its outcome, including ones never executed. "All hypotheses failed" must specify whether all valid hypotheses were unsupported or some were unevaluable.

## Failure, cancellation, and recovery

Use finite per-run timeouts, retry caps, and campaign limits. On timeout or cancellation, stop the owned process tree, preserve logs and valid checkpoints, release resources, and record the cause. Before retrying after a worker crash, identify whether its original process is still running; avoid launching a duplicate experiment. If evidence cannot be recovered reliably, label the attempt interrupted and launch a new attempt only under the retry policy.

Fix reproducible implementation defects within the selected question and budget, record the change, and rerun affected checks. Source changes invalidate dependent confirmatory measurements; keep older results as exploratory or invalid with reasons. A materially different hypothesis is a new plan, not a hidden patch to a failed confirmation.

On terminal cancellation, blockage, or exhausted resources, write a partial report with completed runs, missing work, and exact resumption requirements. Ordinary recovery remains automatic within the approved envelope; increasing paid compute or changing the research question requires updated user authorization.

## Final artifacts and Discord delivery

Save `results/<topic-id>-<campaign-id>.md` plus supporting `summary.json`, tables, and figures. The report contains the original question, approval and plan revisions, related work, every hypothesis, methods, resource accounting, raw evidence links, quantitative results, baseline/ablation/robustness checks, verdict rationale, limitations, negative findings, and reproduction instructions.

Send a per-hypothesis verified-outcome notification and a final campaign summary with headline effects/uncertainty, supported/unsupported/inconclusive counts, unevaluated hypotheses, major limitations, and result paths. Local paths are references, not remote downloads. Attach the final Markdown report when feasible; split oversized summaries and record all parts. Large evidence stays in local artifacts. After confirmed delivery, record Discord message IDs; on delivery failure, preserve the pending message and show it in status.

## Acceptance cases

- A valid approved plan moves automatically from implementation through confirmation to a fully linked report.
- A favorable single run, flawed baseline, leakage, or failed ablation cannot pass a plan requiring repeatable mechanism support.
- An all-negative campaign produces a complete report and Discord summary.
- Interrupted, invalid, and resource-limited campaigns preserve evidence and accurately report incomplete evaluation.
- Reanalysis from raw metrics recreates tables and verdicts within stated tolerances; rerun instructions are executable.
