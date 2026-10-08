# Local artifact contracts

Markdown is the inspectable research record; SQLite coordinates jobs, approvals,
hashes and delivery. Templates describe required content, not completed science.
All topic-specific artifacts remain in ignored research directories.

## Shared conventions

Use stable filesystem-safe IDs, workspace-relative artifact links, source URLs,
ISO 8601 timestamps and SHA-256 hashes. Validate paths remain inside the intended
workspace. Never store credentials in research text or front matter. Local runtime
manifests may record actual execution paths for reproducibility; exclude them from
Git and public shared docs. Do not replace existing evidence to clear an error.

Separate paper author claims, observed results, interpretations and proposed
ideas. Archive scientific revisions and decisions; operational status does not
rewrite an approved question. English presentation copies preserve evidence,
numbers, units, sources and version history and are not new validation.

## Required artifacts

| Artifact | Required content |
| --- | --- |
| `ideas/<idea>.md` | Original wording, source, date, constraints and linked topic |
| `papers/<paper>.pdf` | Matched readable full text and content hash |
| `papers/<paper>.md` | Identity/version, reading scope, method, assumptions, evidence and limitations |
| `papers/<paper>-report.pdf` | English paper-study report for reading/delivery |
| `topic/<topic>-survey.md` | Queries, dates, coverage, comparisons, claims and unresolved evidence |
| `topic/<topic>.md` | Question, bounded gap, feasibility, limitations, revision and selection state |
| `hypothesis/<topic>-<hypothesis>.md/.json` | Approved provenance and frozen executable design |
| `local/` | Session-specific policies/designs and private working documents |
| `experiments/<topic>-<hypothesis>/<campaign>/` | Frozen plan/source/input/environment and all attempted runs |
| `results/<topic>-<campaign>.md/.pdf` | Every outcome, verification, costs and limitations |
| `results/<topic>-<campaign>/` | Summary, tables and supporting analysis |
| `state/` | Database, agent/worker records, checkpoints and delivery receipts |

## Paper and survey evidence

Paper identity includes title/authors, DOI or preprint ID, actual version,
source and publication precision. Record full-text and study status independently
from publication evidence tier. Unavailable text has no fabricated PDF path and
cannot satisfy an evidence requirement.

Each downstream claim links to the saved note, claim ID, exact page and validated
excerpt; printed and PDF page numbering may differ. Record relevant tables,
equations and appendices, actual experiments/proofs, findings and limits. Source
absence and author limitations must not be confused with demonstrated failure.

Surveys retain original question/refinements, exact searches, route/citation
coverage, inclusion/exclusion rules, sources/versions, closest-work comparisons,
claim ledger, contrary evidence, missing work and bounded refinement history.
Topic status mirrors the authoritative decision; editing Markdown cannot approve.

## Frozen plans and raw execution

Plans identify topic/revision, evidence/approval, campaign/hypothesis and content
hash. Define the mechanism/null, code/checks, units/splits/seeds, controls,
metric/unit/direction, practical thresholds, multiplicity, independent repeats,
fairness contract, costs, resources and stop rules. Hash-checked reviewed proposals
must pass the same validation. Keep old revisions and failed attempts.

The campaign directory holds `frozen-plan.json`, source, tests, environment record,
README and `runs/<run>/`. Each run stores request, process completion, manifest,
stdout/stderr and actual `metrics.json`. Optional checkpoints/diagnostics retain
their documented schema and hashes. Metric output identifies condition, seed,
unit, real candidate/baseline/ablation values, evaluation counts and input hash.
Missing or nonfinite measurements are invalid, never fabricated zeros.

Keep smoke, confirmation and repetition stage labels separate. Infrastructure
retries get distinct retained attempts, not overwritten scientific values.
`analysis/` preserves raw input, executed statistical source, statistics, audit,
result and a recomputation entry point. An unused generated helper is not evidence
that its analysis ran.

## Complete result and delivery

Reports include the selected question/revision, frozen plans, literature limits,
all planned hypotheses, all attempts/missing work, quantitative effects/intervals,
baseline/ablation checks, audit rationale, raw-data reproduction, actual resources,
deviations and scoped conclusions. Clearly distinguish negative, uncertain,
invalid, blocked and cancelled work. Summaries and effect tables must come from
validated raw data; a model's remembered result is insufficient.

English PDFs wrap table cells and repeat headers across pages. Confirm text and
source preservation; a readable layout does not validate scientific claims.
Selection PDFs are separate per checked revision. Attachment delivery uses the
actual bytes and MIME type, with its own size and retry limits.

Delivery receipts stay in local state, independently of the scientific outcome.
A queued path is not confirmed remote delivery. Translation, software fixtures
and notification success never grant approval or establish a research finding.
