from __future__ import annotations

import io
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET

from pypdf import PdfReader

from . import schemas
from .common import BudgetExceeded, ResearchError, digest, file_hash, markdown, now, safe_path
from .config import secrets
from .network import fetch, fetch_json
from .reports import pdf_report
from .publications import classify, major_only, title_key


def paper_id(record):
    identity = record.get("doi") or record.get("preprint_id") or " ".join(re.findall(r"\w+", record["title"].lower()))
    return "p-" + digest(identity.lower())[:12]


def from_openalex(work):
    locations = [work.get("best_oa_location"), work.get("primary_location"), *(work.get("locations") or [])]
    pdfs = list(dict.fromkeys(x["pdf_url"] for x in locations if x and x.get("pdf_url")))
    return {
        "title": work.get("title") or "", "authors": [x["author"]["display_name"] for x in work.get("authorships", [])],
        "year": work.get("publication_year"), "publication_date": work.get("publication_date"),
        "doi": (work.get("doi") or "").replace("https://doi.org/", ""),
        "preprint_id": "", "source_url": work.get("doi") or work["id"], "pdf_urls": pdfs,
        "openalex_id": work["id"], "references": work.get("referenced_works") or [],
        "abstract": " ".join(work.get("abstract_inverted_index", {}).keys()) if work.get("abstract_inverted_index") else "",
        "provider": "openalex",
    }


def from_crossref(work):
    publication_date = None
    for field in ("published-online", "published-print", "published", "issued"):
        parts = (work.get(field, {}).get("date-parts") or [[]])[0]
        if parts:
            publication_date = "-".join(str(value) if i == 0 else f"{value:02d}" for i, value in enumerate(parts[:3]))
            break
    return {
        "title": (work.get("title") or [""])[0], "authors": [" ".join((x.get("given", ""), x.get("family", ""))).strip() for x in work.get("author", [])],
        "year": (work.get("published", {}).get("date-parts") or [[None]])[0][0],
        "publication_date": publication_date,
        "doi": work.get("DOI", ""), "preprint_id": "", "source_url": work.get("URL", ""),
        "pdf_urls": [x["URL"] for x in work.get("link", []) if "pdf" in x.get("content-type", "").lower()],
        "references": [x["DOI"] for x in work.get("reference", []) if x.get("DOI")],
        "abstract": re.sub(r"<[^>]*>", "", work.get("abstract", "")), "provider": "crossref",
    }


class ScholarlySources:
    def __init__(self, root):
        key = secrets(root)["OPENALEX_API_KEY"]
        self.headers = {"Authorization": f"Bearer {key}"} if key else {}

    def search(self, provider, query):
        if provider == "openalex":
            url = "https://api.openalex.org/works?" + urllib.parse.urlencode({"search": query, "per-page": 4})
            return [from_openalex(x) for x in fetch_json(url, headers=self.headers)["results"]]
        if provider == "crossref":
            url = "https://api.crossref.org/works?" + urllib.parse.urlencode({"query.bibliographic": query, "rows": 4})
            return [from_crossref(x) for x in fetch_json(url)["message"]["items"]]
        if provider == "arxiv":
            url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"search_query": "all:" + query, "max_results": 4})
            feed = ET.fromstring(fetch(url))
            ns = {"a": "http://www.w3.org/2005/Atom"}
            records = []
            for entry in feed.findall("a:entry", ns):
                identifier = entry.findtext("a:id", "", ns).replace("http://", "https://")
                records.append({"title": " ".join(entry.findtext("a:title", "", ns).split()), "authors": [a.findtext("a:name", "", ns) for a in entry.findall("a:author", ns)], "year": entry.findtext("a:published", "", ns)[:4], "publication_date": entry.findtext("a:published", "", ns)[:10], "doi": "", "preprint_id": identifier.rsplit("/", 1)[-1], "source_url": identifier, "pdf_urls": [identifier.replace("/abs/", "/pdf/")], "references": [], "abstract": entry.findtext("a:summary", "", ns), "provider": "arxiv"})
            return records
        raise ResearchError("Unknown scholarly source")

    def trace(self, record, direction):
        if record.get("openalex_id"):
            if direction == "forward":
                url = "https://api.openalex.org/works?" + urllib.parse.urlencode({"filter": "cites:" + record["openalex_id"].rsplit("/", 1)[-1], "per-page": 2})
                return [from_openalex(x) for x in fetch_json(url, headers=self.headers)["results"]]
            return [from_openalex(fetch_json("https://api.openalex.org/works/" + identifier.rsplit("/", 1)[-1], headers=self.headers)) for identifier in record.get("references", [])[:2]]
        if direction == "backward":
            return [from_crossref(fetch_json("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe=""))["message"]) for doi in record.get("references", [])[:2]]
        if record.get("doi"):
            work = fetch_json("https://api.openalex.org/works/https://doi.org/" + urllib.parse.quote(record["doi"], safe=""), headers=self.headers)
            return self.trace(from_openalex(work), direction)
        return []


def normalized(text):
    return " ".join(re.findall(r"\w+", text.lower()))


def validate_pdf(data, record):
    if not data.lstrip().startswith(b"%PDF-"):
        raise ResearchError("Source returned a non-PDF response")
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ResearchError("Encrypted paper PDF is not readable")
        pages = [page.extract_text() or "" for page in reader.pages]
    except ResearchError:
        raise
    except Exception:
        raise ResearchError("Paper PDF cannot be parsed") from None
    text = "\n".join(pages)
    if len(text.strip()) < 200:
        raise ResearchError("Paper requires OCR or has insufficient readable text")
    if len(text) > 400000:
        raise ResearchError("Paper exceeds the full-text context bound; segmented review is required")
    title_words = set(re.findall(r"\w{4,}", record["title"].lower()))
    first_pages = set(re.findall(r"\w{4,}", " ".join(pages[:2]).lower()))
    matched = title_words & first_pages
    doi_match = bool(record.get("doi") and normalized(record["doi"]) in normalized(" ".join(pages[:2])))
    if not doi_match and (not title_words or len(matched) < min(3, len(title_words)) or len(matched) / len(title_words) < 0.6):
        raise ResearchError("PDF bibliographic identity does not match the discovered paper")
    return pages


def validate_note(note, pages):
    if not note["identity_verified"] or len(note["claims"]) < 2:
        raise ResearchError("Study note lacks verified identity or substantive evidence")
    identifiers = set()
    for claim in note["claims"]:
        if claim["id"] in identifiers:
            raise ResearchError("Duplicate paper claim ID")
        identifiers.add(claim["id"])
        if not 1 <= claim["page"] <= len(pages) or len(claim["quote"].strip()) < 12:
            raise ResearchError("Study note has an invalid page or empty evidence quote")
        if normalized(claim["quote"]) not in normalized(pages[claim["page"] - 1]):
            raise ResearchError("Evidence quote was not found on its claimed PDF page")


def study(ctx, record, review_request=""):
    identifier = record["id"]
    stored = ctx.store.maybe("paper", identifier)
    if (stored and stored.get("note") and stored.get("full_text_status") == "verified"
            and stored.get("publication") == record.get("publication")
            and stored.get("evidence_role", "hard") == record.get("evidence_role", "hard")):
        path = safe_path(ctx.root, stored["pdf_path"])
        if path.is_file() and file_hash(path) == stored["pdf_sha256"] and safe_path(ctx.root, stored["note_path"]).is_file() and file_hash(safe_path(ctx.root, stored["note_path"])) == stored["note_sha256"]:
            ctx.emit("paper.reused", paper=identifier, path=stored["note_path"])
            return dict(stored, evidence_role=record.get("evidence_role", "hard"))
    pages, pdf_data, error = None, None, "No accessible PDF source was discovered"
    ctx.reserve("full_texts", "max_full_texts", key=identifier)
    for url in record["pdf_urls"][:3]:
        ctx.emit("paper.download_started", paper=identifier, source=url)
        try:
            pdf_data = fetch(url.replace("http://", "https://", 1))
            pages = validate_pdf(pdf_data, record)
            break
        except ResearchError as failure:
            error = str(failure)
            ctx.emit("paper.download_failed", paper=identifier, reason=error)
    record = dict(record)
    record.update({"retrieved_at": now(), "full_text_status": "unavailable", "note_path": f"papers/{identifier}.md"})
    if pages is None:
        record["acquisition_error"] = error
        ctx.write(record["note_path"], markdown({"paper_id": identifier, "full_text_status": "unavailable", "study_status": "metadata_only", "source_url": record["source_url"]}, record["title"], [("Evidence gap", error), ("Discovery metadata", "This record cannot be used as substantive evidence.\n\n" + record.get("abstract", ""))]))
        ctx.store.put("paper", identifier, record, "paper.evidence_blocked", error)
        return record
    record["pdf_path"] = ctx.write(f"papers/{identifier}.pdf", pdf_data)
    record["pdf_sha256"] = file_hash(safe_path(ctx.root, record["pdf_path"]))
    ctx.emit("paper.pdf_validated", paper=identifier, pages=len(pages), path=record["pdf_path"])
    study_input = {"metadata": record, "review_request": review_request,
                   "pages": [{"pdf_page": i + 1, "text": text} for i, text in enumerate(pages)]}
    note = ctx.ask("Read the entire paper, including relevant appendices, against the supplied review_request. Explain the implemented data flow, representation, objective and assumptions in method/assumptions. In evaluation/findings, identify datasets, budgets, baselines, ablations and uncertainty actually reported. Separate what the paper demonstrates, author-stated limitations, and reviewer-identified questions it does not test; an untested question is not proof of novelty or impossibility. Use PDF page references for important comparisons. Write a critical study note with at least two claim IDs, exact short evidence quotes totaling at most 25 words, and 1-based PDF pages. Every quote must contain at least 12 characters. Distinguish author claims from interpretation. Extract real reference DOIs when visible; do not invent them.", study_input, schemas.STUDY)
    for attempt in range(3):
        try:
            validate_note(note, pages)
            break
        except ResearchError as failure:
            if attempt == 2:
                raise
            # A schema-valid answer can still fail scientific evidence checks.
            # Retain it and request a bounded repair with the actual source pages.
            ctx.emit("agent.note_validation_failed", paper=identifier, reason=str(failure))
            note = ctx.ask(
                "Repair this rejected study note against the supplied PDF pages. Keep at least two substantive claims. "
                "Every quote must contain at least 12 characters and appear verbatim on its 1-based PDF page. "
                "Use short excerpts, totaling at most 25 words. Remove claims without verifiable evidence; do not invent "
                "or silently change numeric findings. Return the entire corrected note, preserving uncertainty.",
                {**study_input, "rejected_note": note, "validation_error": str(failure), "repair_attempt": attempt + 1},
                schemas.STUDY,
            )
    record.update({"note": note, "full_text_status": "verified", "page_count": len(pages)})
    sections = [("Bibliographic verification", f"Authors: {', '.join(record['authors'])}\n\nSource: {record['source_url']}\n\nPDF: [{identifier}.pdf]({identifier}.pdf)"), ("Research question", note["research_question"]), ("Contribution", note["contribution"]), ("Method and assumptions", note["method"] + "\n\n" + note["assumptions"]), ("Evaluation", note["evaluation"]), ("Findings", note["findings"]), ("Author limitations", note["author_limitations"]), ("Agent interpretation", note["interpretation"]), ("Relevance", note["relevance"])]
    ledger = "\n\n".join(f"### {claim['id']} ({claim['kind']}, PDF page {claim['page']})\n\n{claim['claim']}\n\nEvidence excerpt: {claim['quote']}" for claim in note["claims"])
    sections.extend([("Evidence ledger", ledger), ("Reproduction resources", note["code_url"] or "No code URL verified")])
    role = record.get("evidence_role", "hard")
    publication = record.get("publication")
    sections.insert(0, ("Publication and evidence tier", (f"Verified major-venue evidence: {publication['venue']}; publication source: {publication['source_url']}" if publication else "Publication evidence has not been verified.") + ("\n\nSupplementary literature; cannot establish prior-work coverage or a verified research gap." if role == "supplement" else "")))
    ctx.write(record["note_path"], markdown({"paper_id": identifier, "doi": record["doi"], "preprint_id": record["preprint_id"], "year": record["year"], "pdf_path": record["pdf_path"], "pdf_sha256": record["pdf_sha256"], "full_text_status": "verified", "study_status": "complete", "retrieved_at": record["retrieved_at"]}, record["title"], sections))
    record["note_sha256"] = file_hash(safe_path(ctx.root, record["note_path"]))
    record["report_path"] = ctx.write(f"papers/{identifier}-report.pdf", pdf_report(record["title"], sections))
    ctx.store.put("paper", identifier, record, "paper.note_saved",
                  event_key=f"paper-note:{identifier}:{record['note_sha256']}",
                  event_data={"paper": identifier, "title": record["title"],
                              "evidence_role": role,
                              "source": record["source_url"], "question": note["research_question"],
                              "contribution": note["contribution"], "findings": note["findings"],
                              "relevance": note["relevance"], "limitations": note["author_limitations"],
                              "result": record["report_path"]})
    return record


def evidence_valid(assessment, papers, strict=False):
    available = {p["id"]: {c["id"] for c in p["note"]["claims"]} for p in papers if p.get("full_text_status") == "verified" and (not strict or p.get("evidence_role") == "hard")}
    for entry in assessment["evidence"]:
        if entry["paper_id"] not in available or entry["claim_id"] not in available[entry["paper_id"]]:
            raise ResearchError("Topic assessment references missing or unverified paper evidence")
    if assessment["decision"] == "CANDIDATE" or (strict and assessment["decision"] == "COVERED"):
        if not assessment["evidence"] or not assessment["closest_papers"] or any(p not in available for p in assessment["closest_papers"]):
            raise ResearchError("Candidate lacks full-text evidence for its closest related work")


def review(ctx):
    topic = ctx.store.get("topic", ctx.job["entity"])
    sources = ctx.service.sources
    state = ctx.data.setdefault("review", {"round": 0, "history": [], "question": topic["original_idea"], "queries": {}})
    while state["round"] <= 2:
        round_index = state["round"]
        search_plan = ctx.ask("Normalize this idea into one specific research question and return two complementary scholarly search queries including method synonyms. Discovery requests may propose one bounded research idea. Do not claim novelty yet.", {"idea": state["question"], "original_input": topic["original_idea"], "source": topic["source"], "prior_rounds": state["history"]}, schemas.SEARCH)
        requested_queries = topic.get("search_queries") if round_index == 0 else None
        queries = list(dict.fromkeys(q.strip() for q in (requested_queries or search_plan["queries"]) if q.strip()))[:2]
        if len(queries) < 2:
            raise ResearchError("Search plan must contain two distinct queries")
        records, routes = {}, set()
        for query in queries:
            for provider in ("openalex", "crossref", "arxiv"):
                cache_key = digest([round_index, provider, query])
                if cache_key not in state["queries"]:
                    ctx.reserve("queries", "max_queries", key=cache_key)
                    ctx.emit("literature.query_started", provider=provider, query=query)
                    try:
                        found = sources.search(provider, query)
                        result = {"provider": provider, "query": query, "timestamp": now(), "papers": found, "error": None}
                        ctx.emit("literature.query_completed", provider=provider, query=query, count=len(found))
                    except (ResearchError, ValueError, KeyError, ET.ParseError) as error:
                        result = {"provider": provider, "query": query, "timestamp": now(), "papers": [], "error": str(error)}
                        ctx.emit("literature.query_failed", provider=provider, reason=str(error))
                    state["queries"][cache_key] = result
                    ctx.checkpoint()
                result = state["queries"][cache_key]
                if result["error"] is None:
                    routes.add(provider)
                for paper in result["papers"]:
                    if not paper["title"]:
                        continue
                    identifier = paper_id(paper)
                    paper = dict(paper, id=identifier)
                    # Prefer richer identifiers/PDF locations across duplicate DOI records.
                    if identifier in records:
                        prior = records[identifier]
                        pdf_urls = list(dict.fromkeys(prior["pdf_urls"] + paper["pdf_urls"]))
                        prior.update({k: v for k, v in paper.items() if v and not prior.get(k)})
                        prior["pdf_urls"] = pdf_urls
                    else:
                        ctx.reserve("candidates", "max_candidates", key=identifier)
                        records[identifier] = paper
                # Two working independent discovery routes suffice; arXiv is fallback.
                if len(routes) >= 2 and provider == "crossref":
                    break
        # Officially inspected papers supplement keyword discovery. Keep their
        # provenance separate; seeds do not count as independent search routes.
        for seed in topic.get("review_seeds", []):
            identifier = next((identifier for identifier, paper in records.items()
                               if title_key(paper["title"]) == title_key(seed["title"])), paper_id(seed))
            if identifier not in records:
                ctx.reserve("candidates", "max_candidates", key=identifier)
                records[identifier] = dict(seed, id=identifier)
            else:
                records[identifier]["pdf_urls"] = list(dict.fromkeys(seed["pdf_urls"] + records[identifier]["pdf_urls"]))
        if topic.get("review_seeds"):
            state["queries"]["official_seeds"] = {
                "provider": "official_seed", "query": "independently inspected publication pages",
                "timestamp": topic.get("seeds_verified_at", now()),
                "papers": topic["review_seeds"], "error": None}
        if not records:
            raise ResearchError("No scholarly candidates retrieved; cannot make a novelty assessment")
        records = {identifier: classify(ctx.store, paper) for identifier, paper in records.items()}
        screening = ctx.ask("Screen every supplied paper ID for this question: closest (potentially answers it), relevant, or excluded. Metadata is discovery only. Do not exclude a likely direct match because its full text is missing.", {"question": search_plan["question"], "papers": list(records.values())}, schemas.SCREEN)
        screens = {p["paper_id"]: p for p in screening["papers"]}
        if set(screens) != set(records):
            raise ResearchError("Screening must account for every discovered paper exactly once")
        ordered = sorted(records, key=lambda p: (
            screens[p]["relevance"] == "excluded", records[p]["evidence_role"] != "hard",
            screens[p]["relevance"] != "closest"))
        papers, missing = [], []
        for identifier in ordered:
            screen = screens[identifier]
            ctx.emit("paper.screened", paper=identifier, relevance=screen["relevance"], reason=screen["reason"])
            if screen["relevance"] == "excluded":
                continue
            cached_paper = ctx.store.maybe("paper", identifier)
            if ctx.data["usage"].get("full_texts", 0) >= ctx.config["max_full_texts"] and not (cached_paper and cached_paper.get("full_text_status") == "verified"):
                if screen["relevance"] == "closest" and records[identifier]["evidence_role"] == "hard":
                    missing.append(identifier)
                continue
            paper = study(ctx, records[identifier], topic["original_idea"])
            papers.append(paper)
            if screen["relevance"] == "closest" and paper["evidence_role"] == "hard" and paper["full_text_status"] != "verified":
                missing.append(identifier)
        # Citation tracing for the nearest paper, cached as durable search records.
        traced = []
        nearest = records[ordered[0]]
        for direction in ("backward", "forward"):
            trace_key = digest([round_index, nearest["id"], direction])
            if trace_key not in state["queries"]:
                ctx.reserve("queries", "max_queries", key=trace_key)
                ctx.emit("literature.citation_trace_started", paper=nearest["id"], direction=direction)
                try:
                    found = sources.trace(nearest, direction)
                    result = {"provider": "citation_trace", "query": direction + ":" + nearest["id"], "timestamp": now(), "papers": found, "error": None}
                except (ResearchError, ValueError, KeyError) as error:
                    result = {"provider": "citation_trace", "query": direction + ":" + nearest["id"], "timestamp": now(), "papers": [], "error": str(error)}
                state["queries"][trace_key] = result
                ctx.emit("literature.citation_trace_completed", paper=nearest["id"], direction=direction, count=len(result["papers"]), error=result["error"])
                ctx.checkpoint()
            for record in state["queries"][trace_key]["papers"]:
                record = classify(ctx.store, dict(record, id=paper_id(record)))
                if record["id"] not in records:
                    ctx.reserve("candidates", "max_candidates", key=record["id"])
                    traced.append(record)
                    records[record["id"]] = record
        if traced:
            trace_screen = ctx.ask("Screen each citation-traced paper for potential direct overlap (closest), relevance, or exclusion. Explain each decision.", {"question": search_plan["question"], "papers": traced}, schemas.SCREEN)
            traced_screens = {p["paper_id"]: p for p in trace_screen["papers"]}
            if set(traced_screens) != {p["id"] for p in traced}:
                raise ResearchError("Citation screening is incomplete")
            for record in traced:
                screen = traced_screens[record["id"]]
                screens[record["id"]] = screen
                ctx.emit("paper.screened", paper=record["id"], relevance=screen["relevance"], reason=screen["reason"])
                if screen["relevance"] != "excluded":
                    cached_paper = ctx.store.maybe("paper", record["id"])
                    if ctx.data["usage"].get("full_texts", 0) < ctx.config["max_full_texts"] or (cached_paper and cached_paper.get("full_text_status") == "verified"):
                        paper = study(ctx, record, topic["original_idea"])
                        papers.append(paper)
                        if screen["relevance"] == "closest" and paper["evidence_role"] == "hard" and paper["full_text_status"] != "verified":
                            missing.append(record["id"])
                    elif screen["relevance"] == "closest" and record["evidence_role"] == "hard":
                        missing.append(record["id"])
        # Publication proofs can be verified while a long review is running.
        # Rebuild changed notes before freezing the final scientific evidence.
        for index, paper in enumerate(papers):
            current = classify(ctx.store, paper)
            if current.get("publication") != paper.get("publication") or current["evidence_role"] != paper["evidence_role"]:
                papers[index] = study(ctx, current, topic["original_idea"])
        missing = [p["id"] for p in papers if p["evidence_role"] == "hard"
                   and p.get("full_text_status") != "verified"
                   and screens[p["id"]]["relevance"] == "closest"] + [identifier for identifier in missing
                   if identifier not in {p["id"] for p in papers}]
        strict = major_only(ctx.store)
        hard_papers = [p for p in papers if p["evidence_role"] == "hard"]
        assessment = ctx.ask("Write a mechanism-level thematic literature synthesis and bounded gap assessment addressing the full review_request, based only on verified paper notes/claims. Compare what each closest method implements, its assumptions, what experiments or proofs establish, and what remains untested. Explain whether apparent gains are new information, an inductive prior, regularization, or an evaluation confound. Distinguish a missing experiment from a genuinely unsupported capability; do not infer novelty from a missing keyword combination. Account for contrary evidence and closest work. If covered, propose one specific deeper improvement question for the next search round. Never claim global absence of prior work. Missing potentially direct matches block a candidate. In major_only mode, ONLY papers with evidence_role=hard can support decisions, evidence entries, closest_papers, or critical_missing_ids. Other papers are supplements: discuss their mechanisms and risks separately, but never use them alone to declare COVERED, CANDIDATE, or a hard evidence blocker. Use bare supplied IDs, not IDs with appended titles. Insufficient major-venue coverage means UNRESOLVED.", {"question": search_plan["question"], "review_request": topic["original_idea"], "papers": hard_papers, "supplements": [p for p in papers if p["evidence_role"] != "hard"], "major_only": strict, "screening": list(screens.values()), "missing_closest": missing, "search_log": list(state["queries"].values()), "prior_rounds": state["history"], "round": round_index}, schemas.ASSESS)
        critical = [identifier for identifier in assessment["critical_missing_ids"] if not strict or records.get(identifier, {}).get("evidence_role") == "hard"]
        if missing or critical:
            assessment["decision"] = "EVIDENCE_BLOCKED"
        elif strict and not any(p.get("full_text_status") == "verified" for p in hard_papers):
            assessment["decision"] = "UNRESOLVED"
        if len(routes) < 2 and assessment["decision"] == "CANDIDATE":
            assessment["decision"] = "UNRESOLVED"
        evidence_valid(assessment, papers, strict=strict)
        record = {"round": round_index, "question": search_plan["question"], "assessment": assessment, "paper_ids": [p["id"] for p in papers], "screening": list(screens.values())}
        ctx.write_json(f"topic/{topic['id']}-review-r{round_index}.json", record)
        state["history"].append(record)
        ctx.emit("topic.assessed", decision=assessment["decision"], round=round_index, question=assessment["question"])
        if assessment["decision"] == "COVERED" and assessment["improvement_question"].strip() and round_index < 2:
            state["round"] += 1
            state["question"] = assessment["improvement_question"]
            ctx.emit("topic.refinement_started", round=state["round"], question=state["question"])
            ctx.checkpoint()
            continue
        topic.update({"question": assessment["question"], "assessment": assessment, "papers": [p["id"] for p in papers], "review_history": state["history"], "status": "AWAITING_SELECTION" if assessment["decision"] == "CANDIDATE" else assessment["decision"], "search_as_of": now()})
        inventory = "\n".join(f"- [{p['title']}](../{p['note_path']}); evidence_role={p['evidence_role']}" + (f"; publication={p['publication']['venue']}; source={p['publication']['source_url']}" if p.get("publication") else "; publication unverified or outside selected venues") + (f"; [PDF](../{p['pdf_path']})" if p.get("full_text_status") == "verified" else "; full text unavailable") for p in papers)
        search_log = "\n\n".join(f"- {x['timestamp']} / {x['provider']} / {x['query']} / candidates={len(x['papers'])} / error={x['error']}" for x in state["queries"].values())
        evidence = "\n".join(f"- {e['paper_id']} / {e['claim_id']}: {e['interpretation']}" for e in assessment["evidence"])
        ctx.write(f"topic/{topic['id']}-survey.md", markdown({"topic_id": topic["id"], "search_as_of": topic["search_as_of"]}, "Literature survey: " + topic["question"], [("Scope and coverage", assessment["coverage_limits"]), ("Search log", search_log), ("Bibliography", inventory), ("Thematic synthesis and closest-work comparison", assessment["synthesis"]), ("Evidence ledger", evidence), ("Gap assessment and feasibility", assessment["proposed_gap"] + "\n\n" + assessment["feasibility"]), ("Refinement history", json.dumps(state["history"], ensure_ascii=False, indent=2))]))
        ctx.service.save_topic(topic, ctx)
        if topic["status"] == "AWAITING_SELECTION":
            from .surveys import publish_selectable_topic
            ctx.guard()
            publish_selectable_topic(ctx.service, topic)
        else:
            ctx.emit("topic.review_closed", topic=topic["id"], revision=topic["revision"], decision=assessment["decision"])
        ctx.checkpoint()
        return
