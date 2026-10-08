# System 1: literature and bounded gap review

Implements user steps 1–2. A checked candidate stops at user selection.
See [workflow](04-workflow-and-discord.md) and [artifacts](05-artifacts.md).

## Inputs and outputs

Accept the user's original idea and constraints, or an explicit discovery request
for an area. Preserve the full wording and refinements alongside the normalized
question. Outputs are original intake, query/screening logs, validated paper PDFs
and notes, a thematic survey, a topic assessment and its evidence revision.
Research outputs are local; shared docs never contain particular studies.

## Review procedure

1. Specify the problem, proposed mechanism, alternatives and intended setting.
   Resolve ordinary terms from context; clarify missing scope only when needed.
2. Search exact terms, synonyms, foundational and current work, contrary evidence
   and close alternatives. Record source, query, date, filtering and coverage.
   Explicitly pinned queries remain unchanged for their designated initial round.
3. Use distinct discovery routes and backward/forward citation tracing. Official
   source seeds aid retrieval but do not count as independent discovery searches.
   Record unavailable providers instead of fabricating search results.
4. Verify identity and version against authoritative metadata. Deduplicate IDs,
   titles and full-text hashes while preserving preprint/published distinctions.
5. Acquire accessible full text. Validate real PDF structure, readable text,
   bibliographic match and content hash before finalizing the local file.
6. Read methods, relevant appendices, assumptions, evaluations and limitations.
   State actual baselines, budgets, findings and contrary evidence. Distinguish
   author claims, observed results and reviewer interpretation.
7. Validate downstream claim excerpts against their actual PDF pages. Preserve
   failed notes; bounded correction may use those pages, never invented evidence.
8. Synthesize by mechanisms and disagreements, comparing the closest methods on
   common dimensions. An abstract list or absent keyword is insufficient.
9. Assess a bounded difference and feasible test. If covered, investigate one
   improvement round and optionally a second, preserving ancestry and limits.
10. Save the outcome and limitations. Deliver only checked selectable topics or
    substantive reports/intervention requests; never begin planning here.

## Evidence policy

Publication verification and full-text study are separate. Under workspace
major-venue-only policy, a paper is hard evidence only when official publication
proof matches the selected venue and host policy. Preprints, other venues and
unverified records remain supplements. Without that policy the usual verified
full-text requirements still apply. Supplements can expose close mechanisms or
collision risks but cannot alone establish a gap under a strict policy.

Missing/unreadable full text remains explicitly unavailable; no fake local PDF
or completed study is recorded. Critical likely direct matches prevent a verified
gap until resolved or the scope is revised. Any permitted bounded-selection
exception must be recorded locally and disclose the missing work; it never grants
experiment approval. OCR-required or oversized text needs supported review rather
than a claim to have read everything.

Use “No directly matching work found in the reviewed sources as of the recorded
date,” with actual scope and uncertainty. Never claim that nobody has done it.
Finite query/candidate/full-text/time limits bound work; exhausted or incomplete
coverage is unresolved, not proof of no gap.

| Decision | Meaning |
| --- | --- |
| `CANDIDATE` | Checked bounded question and feasible direction; awaits user selection |
| `COVERED` | Closest work answers the idea; bounded refinements found no justified candidate |
| `UNRESOLVED` | Coverage, budget or ambiguity prevents a justified assessment |
| `EVIDENCE_BLOCKED` | Required evidence cannot be validated |

## Reading and selection reports

A validated single-paper report includes title, source, publication date, question,
contribution, findings, limitations and an English study PDF. Retain the date's
verified precision; a preprint date and notification time are not publication.

Each checked selectable revision receives one English PDF and one concise embed.
Include question, close work, bounded gap, feasibility and limitations, with the
identifier in the title and current revision. Full comparison and source ledger
remain in the PDF. Separate-topic delivery suppresses joint batch notifications;
local batch artifacts can still preserve the collective review.

Search, acquisition, screening, tracing and ordinary analysis lifecycle events
stay local. A preliminary lead or evidence-blocked direction must be labelled
unverified. Delivery and translation do not validate evidence or select a topic.

## Acceptance

Verify intake reaches archived evidence and a persistent selection pause; title
or PDF mismatch, invalid excerpts and unavailable close work cannot create false
evidence; covered questions respect two refinement rounds; restart reuses only
hash-validated artifacts. User refinements must reach reading and synthesis.
