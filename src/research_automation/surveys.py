"""Bundle completed literature checks without bypassing topic selection."""
from .common import ResearchError, digest, markdown, now
from .messages import VALUES
from .reports import pdf_report


def publish_selectable_topic(service, topic):
    """One evidence-checked topic revision, one PDF, one selection notification."""
    current = service.store.get("topic", topic["id"])
    if current["status"] != "AWAITING_SELECTION" or current["revision"] != topic["revision"]:
        raise ResearchError("Only the current checked candidate may be sent for selection")
    if digest(service.evidence_bundle(current)) != current.get("evidence_bundle_hash"):
        raise ResearchError("Frozen topic evidence differs; regenerate its review before sending")
    assessment = current["assessment"]
    bibliography, related = [], []
    for identifier in current.get("papers", []):
        paper = service.store.get("paper", identifier)
        publication = paper.get("publication") or {}
        source = publication.get("source_url") or paper["source_url"]
        date = service.store.notification_data("paper.note_saved", {"paper": identifier})["published_date"]
        entry = (f"{paper['title']}\nSource: {source}\nPublication date: {date}; "
                 f"venue: {publication.get('venue', 'Unverified / supplementary source')}; "
                 f"evidence tier: {VALUES.get(paper.get('evidence_role'), 'Unverified')}")
        bibliography.append(entry)
        if identifier in assessment["closest_papers"]:
            related.append(entry)
    sections = [
        ("Research question", current["question"]),
        ("Selection and evidence scope", f"Topic: {current['id']}; revision: {current['revision']}. "
         "Awaiting your selection; no planning or experiments are authorized by this report.\n\n" + assessment["coverage_limits"]),
        ("Closest related work", "\n\n".join(related)),
        ("Method comparison", assessment["synthesis"]),
        ("Bounded gap", assessment["proposed_gap"]),
        ("Feasible verification route", assessment["feasibility"]),
        ("Claim evidence", "\n\n".join(f"{e['paper_id']} / {e['claim_id']}: {e['interpretation']}" for e in assessment["evidence"])),
        ("References", "\n\n".join(bibliography)),
    ]
    from .presentation import english_sections
    sections = english_sections(service.agent, sections, service.config["agent_timeout_seconds"])
    stem = f"topic/{current['id']}-{current['revision']}-selection"
    title = current["question"]
    pdf = pdf_report(title, sections)
    if len(pdf) > 1024 * 1024:
        raise ResearchError("Single-topic PDF exceeds the attachment limit")
    service.write(stem + ".md", markdown({"topic": current["id"], "revision": current["revision"]}, title, sections))
    service.write(stem + ".pdf", pdf)
    service.store.event("topic.awaiting_selection", {
        "topic": current["id"], "revision": current["revision"], "question": current["question"],
        "closest_papers": "\n\n".join(related), "gap": assessment["proposed_gap"],
        "feasibility": assessment["feasibility"], "limitations": assessment["coverage_limits"],
        "result": stem + ".pdf"}, key=f"topic-selection-pdf:{current['id']}:{current['revision']}")
    return stem + ".pdf"


def publish_ready_batches(service):
    published = 0
    for batch in service.store.list("survey_batch"):
        topics = [service.store.get("topic", identifier) for identifier in batch["topic_ids"]]
        if not topics:
            continue
        jobs = [service.store.db.execute(
            "SELECT status FROM jobs WHERE kind='review' AND entity=? ORDER BY rowid DESC LIMIT 1",
            (topic["id"],)).fetchone() for topic in topics]
        if any(not job or job["status"] not in {"done", "blocked"} for job in jobs):
            continue
        signature = digest([(t["id"], t.get("revision"), t["status"], t.get("blocker")) for t in topics])
        if batch.get("report_signature") == signature:
            continue
        sections = [("Scope and evidence policy", batch["instruction"] +
                     "\n\nThis report summarizes saved review results. Evidence-blocked directions remain unverified. "
                     "Only verified selectable topics may be approved; this batch cannot authorize planning or experiments.")]
        selectable = []
        for topic in topics:
            assessment = topic.get("assessment") or {}
            status = topic["status"]
            if status == "AWAITING_SELECTION":
                try:
                    if digest(service.evidence_bundle(topic)) != topic.get("evidence_bundle_hash"):
                        raise ResearchError("Frozen evidence differs")
                    selectable.append(topic["id"])
                except ResearchError:
                    status = "EVIDENCE_BLOCKED"
            body = (f"Topic: {topic['id']}; revision: {topic.get('revision', 'pending')}; "
                    f"assessment: {VALUES.get(status, status)}\n\nResearch question: {topic['question']}\n\n"
                    f"Related work and comparison: {assessment.get('synthesis', 'No verified synthesis is available.')}\n\n"
                    f"Bounded gap / lead: {assessment.get('proposed_gap', 'Unverified.')}\n\n"
                    f"Feasibility: {assessment.get('feasibility', 'Pending review.')}\n\n"
                    f"Limitations: {assessment.get('coverage_limits', '')}\n\n"
                    f"Review blocker: {topic.get('blocker', 'No additional blocker recorded.')}\n\n"
                    f"Local survey: topic/{topic['id']}-survey.md")
            sections.append(("Research direction: " + topic["id"], body))
            bibliography = []
            for identifier in topic.get("papers", []):
                paper = service.store.get("paper", identifier)
                publication = paper.get("publication") or {}
                tier = VALUES.get(paper.get("evidence_role"), "Publication evidence unverified")
                bibliography.append(f"{paper['title']}\nEvidence tier: {tier}; full text: {paper.get('full_text_status', 'unknown')}; "
                                    f"publication: {publication.get('venue', 'Unverified / supplementary source')}\n"
                                    f"Source: {publication.get('source_url', paper['source_url'])}\nNote: {paper['note_path']}")
            if bibliography:
                sections.append(("Literature: " + topic["id"], "\n\n".join(bibliography)))
        sections.append(("Topic selection", "Selectable topics: " + (", ".join(selectable) or "No verified selectable topic at present.") +
                         "\n\nOther items remain blocked or unverified leads. An incomplete survey cannot establish that no research gap exists."))
        from .presentation import english_sections
        sections = english_sections(service.agent, sections, service.config["agent_timeout_seconds"])
        stem = f"topic/{batch['id']}-{signature[:12]}"
        title = "Joint research survey: candidate topics and evidence limitations"
        service.write(stem + ".md", markdown({"batch": batch["id"], "created": now()}, title, sections))
        service.write(stem + ".pdf", pdf_report(title, sections))
        separate = (service.store.maybe("policy", "topic_delivery") or {}).get("separate_files", False)
        if separate:
            for topic in topics:
                if topic["id"] in selectable:
                    publish_selectable_topic(service, topic)
        else:
            service.store.event("literature.report", {
                "entity": batch["id"], "summary": "See the PDF for candidate topics, related work and evidence limitations.",
                "count": len(topics), "findings": "Selectable topics: " + (", ".join(selectable) or "No verified selectable topic at present."),
                "limitations": "Blocked items remain unverified. No topic approval or research experiments have been authorized.", "result": stem + ".pdf"},
                key="survey-batch:" + batch["id"] + ":" + signature)
        batch.update({"report_signature": signature, "report_path": stem + ".pdf", "selectable": selectable})
        service.store.put("survey_batch", batch["id"], batch)
        published += 1
    return published
