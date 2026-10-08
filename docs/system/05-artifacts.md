# Artifact contracts and document templates

The Markdown documents are the human-readable research record. SQLite coordinates execution and delivery. A phase is complete only when its required documents and linked evidence pass validation. Templates below describe future outputs; placeholder content is never counted as completed research.

## Shared conventions

- Use stable lowercase slugs with a short ID suffix when necessary; avoid spaces, path separators, reserved Windows names, and excessively long paths. Validate all generated paths remain inside the workspace.
- Use relative artifact links, DOI/preprint IDs, source URLs, ISO 8601 UTC timestamps, and SHA-256 content hashes. Never put secret values in front matter.
- Record provenance, revision, status, producer, and links to input artifacts. Preserve earlier scientific decisions and plan revisions through snapshots or an append-only history.
- Separate verified observations, paper author claims, agent interpretations, and proposed ideas. A generated paragraph without a source is not evidence.
- Paper names use `<paper-id>.pdf` and `<paper-id>.md`; hypothesis names use `<topic-id>-<hypothesis-id>.md`; each campaign gets a unique result name so later runs do not overwrite earlier findings.

## Idea record: `ideas/<idea-id>.md`

```markdown
---
idea_id: <id>
created_at: <UTC timestamp>
source: user | agent_discovery
status: received | reviewing | assessed
topic_ids: []
---
# <Idea title>
## Original input
<Preserve the user's idea or discovery request.>
## Normalized research question
<Problem, proposed mechanism, expected benefit, scope.>
## Motivation and constraints
<Value, domain, known work, data/hardware constraints, search limits.>
## Discovery history
<Candidate generation and links to topic decisions.>
```

## Paper study note: `papers/<paper-id>.md`

```markdown
---
paper_id: <id>
title: <verified title>
authors: [<verified authors>]
year: <year>
doi: <DOI or null>
preprint_id: <identifier or null>
version: <version>
source_url: <original bibliographic source>
pdf_source_url: <download source or null>
retrieved_at: <UTC timestamp>
pdf_path: <local relative path or null>
pdf_sha256: <hash or null>
full_text_status: verified | unavailable | unreadable
study_status: complete | metadata_only | incomplete
related_topics: [<IDs>]
---
# <Paper title>
## Bibliographic verification and version history
<Metadata match, preprint/published relationship, corrections/retractions checked.>
## Research question and contribution
<Author claims, with PDF evidence locators.>
## Method and assumptions
<Algorithm/theory, equations, applicability, implementation details.>
## Evaluation or proof
<Data, baselines, budgets, metrics, repetitions, proof assumptions.>
## Main findings
<Numbers with units, uncertainty, and table/figure/page references.>
## Limitations and critical reading
<Author-stated limitations separately from agent interpretation.>
## Relationship to this idea
<What it already answers, what it does not, possible improvements.>
## Evidence ledger
| Claim ID | Claim | PDF locator | Evidence type | Confidence/limitations |
| --- | --- | --- | --- | --- |
| <id> | <claim> | <page, section/table/equation> | author claim / observed result / interpretation | <limits> |
## Reproduction resources
<Code/data links and revisions; access issues.>
```

Evidence locators specify both printed page and PDF page index when they differ. A metadata-only record has no fake local PDF path and cannot satisfy a topic's substantive evidence requirement. Store full papers from accessible sources; write original analytical notes rather than reproducing long copyrighted passages.

## Literature survey: `topic/<topic-id>-survey.md`

Required sections:

1. Review question, scope, search date, source coverage, exclusions, and search/resource bounds.
2. Search log: exact queries, filters, source, date, candidates inspected, screening decisions, and citation tracing.
3. Bibliography linking each evidence paper's note, PDF, verified source, and version.
4. Thematic synthesis of methods, findings, agreement/conflict, and assumptions.
5. Closest-work comparison table: method/contribution, data or setting, assumptions, baseline, outcome, limitations, and exact evidence links.
6. Claim ledger connecting topic claims to paper claim IDs and PDF locators, including contrary evidence.
7. Gap assessment, unresolved full text, coverage limits, and refinement history.

The survey should explain why the proposed gap matters and how it differs from the best existing answer. A list of paper abstracts alone does not satisfy this artifact.

## Topic record: `topic/<topic-id>.md`

```markdown
---
topic_id: <id>
idea_id: <id>
revision: <content revision>
review_decision: CANDIDATE | COVERED | UNRESOLVED | EVIDENCE_BLOCKED
workflow_status: <state>
search_as_of: <date>
survey_path: topic/<id>-survey.md
evidence_bundle_hash: <hash>
approval_id: <ID or null>
hypothesis_ids: []
---
# <Topic title>
## Research question and motivation
<Specific question and practical/scientific value.>
## Closest related work
<Competing claims with links to evidence.>
## Proposed gap and contribution
<Bounded novelty assessment and scope.>
## Feasibility and verification direction
<Data, implementation approach, plausible baselines, rough resource needs.>
## Evidence limitations and risks
<Coverage limits, counterevidence, missing inputs, confounders.>
## Improvement rounds
<Original assessment, up to two revisions, searches and decisions.>
## Selection decision
<Pending/approved/rejected/deferred; user instruction, revision, scope, limits.>
## Linked artifacts and history
<Survey, notes, hypotheses, campaigns, immutable decision records.>
```

The selection section mirrors the authoritative decision record; editing it alone cannot manufacture approval. Relevant paper versions, hashes, notes, and survey claims form the evidence bundle. Operational status updates do not change the approved scientific content revision.

## Hypothesis plan: `hypothesis/<topic-id>-<hypothesis-id>.md`

```markdown
---
hypothesis_id: <id>
topic_id: <id>
topic_revision: <revision>
approval_id: <id>
campaign_id: <id>
plan_revision: <revision>
plan_hash: <hash>
status: draft | PLAN_READY | PLAN_BLOCKED | frozen
work_directory: experiments/<topic-id>-<hypothesis-id>/
---
# <Falsifiable hypothesis>
## Evidence and rationale
<Survey and paper claim IDs; proposed mechanism.>
## Hypothesis, null, and disproof conditions
<Setting, predicted change, competing explanation.>
## Implementation specification
<Candidate, baseline, pseudocode, files, correctness checks.>
## Data and experimental design
<Sources/hashes, units, splits, seeds, controls, tuning, repetitions.>
## Metrics and frozen verdict criteria
<Primary metric/direction, meaningful threshold, guardrails, uncertainty,
comparison, multiplicity policy, supported/unsupported/inconclusive rules.>
## Execution stages and commands
<Environment, smoke/pilot/confirmation, ablation/robustness, output schema.>
## Verification and reproducibility
<Baseline tolerance, clean rerun, reanalysis, scoped success conditions.>
## Budget, retries, and stopping rules
<Finite per-run/campaign limits and infrastructure retry policy.>
## Deviations and revision history
<Changes, observations that motivated them, confirmatory contamination.>
```

The document's hash field is computed over canonical plan content excluding the hash itself and volatile workflow metadata. Archive the exact frozen plan with the campaign/run artifacts so later edits cannot change the interpretation of old runs.

## Experiment directory contract

`README.md` explains the approved question, frozen plan, environment setup, exact reproduction commands, and generated artifacts. `src/`, `configs/`, and focused correctness checks hold the implementation. Every run has a unique directory containing its manifest, logs, config/source provenance, and raw outputs. `analysis/` contains rerunnable analysis code and reports linked to their input hashes.

`metrics.json` uses a validated schema with the run/seed/instance IDs, metric names/units/direction, raw values, and measurement validity. Missing metrics remain explicit null/invalid entries with reasons, never fabricated zeros. Separate stage labels prevent pilot or smoke results from entering confirmation summaries. Large raw output may use CSV or another documented format referenced by the manifest.

## Complete result: `results/<topic-id>-<campaign-id>.md`

Required sections:

1. Executive result: scoped conclusion, campaign status, counts by hypothesis outcome, and limitations.
2. Question, literature context, selected topic revision, approval, and frozen hypothesis plans.
3. Methods: code/environment/data hashes, baselines, budgets, design, metrics, criteria, and all deviations.
4. Per-hypothesis evidence: planned/completed/invalid/missing runs, effect estimates/uncertainty, primary verdict, and failure reasons.
5. Detailed verification: baseline reproduction, correctness, ablation, robustness, clean rerun, and raw-data recomputation.
6. Negative and incomplete results: all hypotheses accounted for; distinguish insufficient evidence from evidence against the claim.
7. Reproduction instructions and links to manifests, raw metrics, scripts, configs, tables, figures, PDFs, and notes.
8. Resource usage, remaining caveats, and justified next steps without silently starting a new unapproved topic.
9. Delivery record: final Discord event/message IDs or a pending/failed status. Exclude delivery-only changes from the scientific result hash.

`results/<topic-id>-<campaign-id>/summary.json` carries the same IDs, verdicts, headline metrics, resource usage, and artifact links in machine-readable form. Report generation consumes validated raw evidence and frozen criteria rather than an agent's remembered outcome.

## Artifact acceptance checks

Validate required fields, IDs, allowed statuses, workspace-safe paths, link existence, content hashes, paper identity, evidence locators, current approval, frozen plan provenance, and complete hypothesis/run accounting. A phase cannot pass because Markdown headings exist: its required linked evidence must be real, readable, and sufficient for its claims.
