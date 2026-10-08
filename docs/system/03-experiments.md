# System 3: experiment execution and verification

Implements user step 4 from a validated [hypothesis plan](02-hypothesis.md).
Work in `experiments/<topic>-<hypothesis>/<campaign>/`; preserve
[artifact contracts](05-artifacts.md) and [workflow](04-workflow-and-discord.md).

## Frozen execution

Require current approval, unchanged plan/evidence/source, accessible inputs and
remaining resources. Process planned hypotheses sequentially. Preserve every
attempt and all hypotheses; one favorable result does not discard the others.

1. Prepare source/input snapshots, frozen plan and environment fingerprint.
2. Run the declared correctness checks, inspecting both output streams and the
   actual algorithms. A passing assertion or subprocess is insufficient evidence.
3. Run three development smoke units with seeds outside confirmation. The current
   runner uses the declared evaluation budget; these are not automatically cheap
   runs. Their results never enter confirmatory statistics.
4. Execute every planned condition and independent paired seed, producing actual
   candidate/baseline/ablation measurements and declared evaluation counts.
5. Repeat the first three confirmation seeds in each condition in fresh processes.
   Preserve input fingerprints and compare all declared primary values within
   the frozen tolerance. Repetition checks execution stability, not new units.
6. Analyze raw confirmation/reproduction using the installed runner analysis.
   Save inputs, statistical source, statistics and a recomputation entry point.
7. Audit source, correctness logs, manifests, measurements, costs, independent
   units, leakage, baselines, mechanism isolation and reproducibility. Each audit
   check must cite an exact permitted artifact. Treat model audit as fallible.
8. Save every hypothesis outcome and complete campaign report, even when every
   valid hypothesis is negative or work is incomplete. Queue research reports.

Optional domain-specific pilots, tuning, diagnostics or interaction analyses need
an explicit frozen specification; the runner does not automatically implement
every scientific design described in prose.

## Statistics and decisions

For each condition, analyze paired candidate-minus-baseline and
candidate-minus-ablation effects in the declared metric direction. The implemented
percentile bootstrap uses 5,000 resamples. Alpha is divided by campaign hypothesis
count, condition count and two comparisons. Require the planned independent seed
coverage and distinguish independent units from samples inside a run.

`SUPPORTED` requires both lower bounds above their practical thresholds in all
mandatory conditions and successful repetition. `NOT_SUPPORTED` requires each
condition to clearly fail at least one required effect with successful repetition.
Other uncertainty or mixed conditions are `INCONCLUSIVE`. Read condition-level
effects, not only the aggregate label; lack of support is not universal disproof.

The scientific audit can downgrade a result: correctness, fair-budget or leakage
failure makes it `INVALID`; other failed validity checks make it `INCONCLUSIVE`.
Mechanism isolation concerns the design, and may pass for a valid negative result.
The exact executed analysis must reproduce the persisted statistics; an unused
generated analysis helper cannot replace it.

| Outcome | Interpretation |
| --- | --- |
| `SUPPORTED` | Frozen support and verification criteria pass in the tested scope |
| `NOT_SUPPORTED` | Valid evidence clearly fails the required effects under the frozen rule |
| `INCONCLUSIVE` | Evidence is uncertain, mixed or lacks required validity support |
| `INVALID` | Scientific measurements/design fail essential validity checks |
| `BLOCKED` | Resources, inputs or supported execution are insufficient |
| `CANCELLED` | User stops the work; partial evidence remains |

## Cost, guardrails and recovery

Every attempt records source/input/environment hashes, exact command, seed/stage,
process identity, outputs, exit state, elapsed time and measured memory. Local
manifests may contain runtime paths for reproduction; they remain ignored and
must never be published as generic project files. Credentials are excluded from
the experiment environment. Record actual preprocessing/generation/training and
inference costs when relevant; a shared cap alone cannot prove total-cost fairness.

The supervisor enforces timeout, process-RAM and output caps, verifies worker
ownership and stops owned children on cancellation or lost ownership. The
coordinator checks campaign time, run count, disk, approval and notification
backlog. GPU memory is not independently monitored.

On restart, validated completed runs are reused. A persisted successful completion
can be adopted without dispatching again. Infrastructure interruption gets a
distinct retained attempt and at most one retry per logical unit. Failed scientific
runs are not silently retried; valid negative outcomes are never rerun for a win.
Changed source invalidates affected confirmation, requiring a recorded new plan.

Record explicit user-authorized time extensions separately from the original
selection. Keep completed runs, original approval, frozen content and other caps.
Budget exhaustion is incomplete evidence, not scientific disproof.

## Final report

Write Markdown plus an English PDF and machine-readable summary. Include the
question, selected revision, plans, all outcomes, methods, estimates/intervals,
audit, limitations, costs, deviations, raw manifests and reproduction paths.
Per-hypothesis conclusions and the final report are allowed Discord content;
individual-run and file lifecycle events remain local. Confirmed delivery is
tracked separately and does not change the scientific verdict.
