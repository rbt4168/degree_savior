# System 1: idea discovery and literature review

Implements user steps 1 -> 2. Produces an evidence-backed candidate and stops at user selection. Shared lifecycle rules are in [workflow and Discord](04-workflow-and-discord.md); record formats are in [artifacts](05-artifacts.md).

## Inputs and outputs

Accept an idea through the agent interface, or a user request to search for ideas in a specified research area. Save the original wording, normalized question, motivation, domain, constraints, and source in `ideas/<idea-id>.md`. Broad inputs may generate a bounded shortlist; preserve the distinction between user ideas and agent suggestions.

Required outputs for a candidate are:

- `papers/<paper-id>.pdf` and `papers/<paper-id>.md` for every paper used as substantive evidence.
- `topic/<topic-id>-survey.md` containing a coherent literature survey and comparison table.
- `topic/<topic-id>.md` containing the specific question, possible contribution, novelty assessment, feasibility, evidence gaps, and recommendation.
- Recorded queries, screening decisions, refinement history, artifact hashes, and events in the shared state store and readable documents.

## Workflow

1. **Normalize the idea.** Specify the problem, population or benchmark, proposed mechanism, comparison, intended benefit, and known constraints. Identify missing information. Resolve ordinary search terms from context; ask the user only if the missing scope prevents meaningful investigation.
2. **Design the search.** Include exact phrases, synonyms, older terminology, related methods, negative findings, surveys, and recent preprints. Record sources, query strings, filters, timestamps, results inspected, and screening criteria. Include older foundational work and current work; do not silently impose only a recent-year window.
3. **Search and screen.** Start with OpenAlex for discovery and Crossref for DOI/metadata checks, then follow original publisher, author repository, and preprint links. Check current provider access requirements during implementation. Use at least two distinct discovery routes plus backward and forward citation tracing of the closest papers. If a route is unavailable, record reduced coverage.
4. **Resolve identities.** Verify title, authors, date, DOI or preprint identifier, version, and publication status against original records. Merge preprint and published versions where appropriate while retaining differences and provenance. Detect duplicates by identifiers and PDF hashes.
5. **Acquire full text.** Download an accessible PDF from a publisher, preprint server, or author/institutional repository. Validate response type, PDF structure, readable text, bibliographic match, and checksum. Follow redirects with bounded retries; download to a temporary path and finalize only after validation. If extraction requires OCR, verify quoted claims and equations visually.
6. **Write a study note.** Read the full paper, including relevant appendices. Extract the question, method, assumptions, proof or experimental design, datasets, baselines, key findings, limitations, and relationship to the idea. Distinguish author statements from agent interpretation. Record exact pages, sections, equations, tables, or figures for every claim used downstream.
7. **Build the literature survey.** Organize work by approaches and disagreements, not just paper-by-paper summaries. Compare close methods using the same dimensions. Explain the strongest existing answer to the proposed question and what remains untested.
8. **Check novelty and feasibility.** Compare the proposed contribution with the closest papers' full methods and claims. Inspect code or supplementary artifacts when needed to resolve apparent gaps. Assess dataset availability, implementation complexity, meaningful evaluation, resources, and likely confounders.
9. **Refine covered ideas.** If the main idea is already answered, derive a specific improvement from supported limitations or untested assumptions. Search that revised question separately. Perform one round, then optionally a second. Record the parent question and why the revision is different. Do not reset the counter when a candidate is renamed.
10. **Write the decision and notify.** Save all artifacts even when no viable gap is found. For a supported candidate, transition to `AWAITING_SELECTION` and send a Discord selection summary. Stop before hypothesis planning.

OpenAlex supports work search across indexed text; coverage is not equivalent to having read the original paper. Crossref exposes deposited bibliographic metadata and identifiers. These are discovery and identity tools, while the saved PDF supplies the research evidence. See [OpenAlex search](https://help.openalex.org/api/searching/) and [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/).

## Evidence quality and stopping rules

A paper with unavailable or unreadable full text can remain in the screening log with a metadata-only note. Its note must say `full_text_status: unavailable` or `unreadable`, and it cannot be included in the substantive evidence set. If it is likely to answer the question, the topic remains `EVIDENCE_BLOCKED` until resolved or the question is changed. Do not claim a PDF exists when only HTML or an abstract was retrieved.

Before a candidate is selectable, require:

- Locally validated PDFs and completed notes for all material evidence, particularly the nearest competitors.
- Recorded searches across the discovery routes and citation tracing, with a search date and bounded scope.
- A claim-to-evidence comparison explaining the proposed difference from the closest prior work.
- No unresolved likely direct match, contradictory claim, or critical missing full text.
- At least one feasible way to test the question within an explicit resource envelope.

"No directly matching work found in <scope> as of <date>" is acceptable. "No one has ever done this" is not. Tag evidence confidence and explain coverage limits without translating a subjective novelty score into certainty.

Record finite `max_queries`, `max_candidates`, `max_full_texts`, and `max_search_minutes` at job start. Stop when the planned searches and citation tracing produce no material new evidence, or when a bound is reached. If a bound prevents adequate review, use an unresolved outcome. Do not stop early because one search returned no matches. Refinement is capped at two rounds in addition to the original assessment.

## Topic decisions

| Decision | Meaning | Next action |
| --- | --- | --- |
| `CANDIDATE` | A bounded, evidence-backed gap and feasible test are identified | Set `AWAITING_SELECTION`; ask user to select the exact revision |
| `COVERED` | Closest work already answers the idea; no useful refinement survived | Save survey and explanation; notify; stop |
| `UNRESOLVED` | Search budget or ambiguity prevents a justified decision | Save gaps and suggested next steps; notify; await user direction |
| `EVIDENCE_BLOCKED` | Important full text or other essential evidence is missing | Save acquisition attempts and blocker; notify; stop dependent work |

Rejecting or deferring a candidate does not delete its PDFs, notes, or assessment. User-requested revision creates a new content revision and invalidates approval for an older question.

## Selection notification

Send the topic ID and revision, plain-language question, proposed contribution, closest competing papers, bounded novelty statement, evidence confidence, practical value, approximate resource needs, remaining limitations, and the relative paths to the topic and survey. State that step 3 is waiting for a decision through this interface.

Example:

```text
[topic.awaiting_selection] topic=<id> revision=<revision>
Question: <specific research question>
Closest work: <paper IDs and verified source links>
Proposed gap: <difference supported by evidence>
Feasibility: <data, implementation, resource estimate>
Artifacts: topic/<id>.md; topic/<id>-survey.md
Awaiting your selection here: approve, revise, reject, or defer.
```

Also notify separately for each completed query, screened candidate, PDF acquisition or failure, study note, survey, assessment, and refinement. Cached reuse emits an explicit reuse event rather than a fictitious new download event.

## Acceptance cases

- A new idea completes intake, archival, study notes, survey, and candidate assessment automatically, then cannot continue without selection.
- A known-covered idea is recognized from actual paper content; one or two bounded improvement attempts are recorded.
- A fabricated identifier, title/PDF mismatch, abstract-only claim, and unreadable PDF prevent unsupported conclusions.
- An unavailable nearest competitor yields an honest blocker rather than a novelty claim.
- Restarting reuses validated PDFs and notes while checking whether their versions or analysis need updating.
