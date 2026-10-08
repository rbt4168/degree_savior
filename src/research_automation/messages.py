"""English Discord reports; scientific terms and identifiers stay literal."""
import json

REVIEW_ACTIONS = frozenset({
    "paper.note_saved", "literature.report", "topic.awaiting_selection",
    "hypothesis.verified", "campaign.result", "workflow.blocked",
    "selection.stale_rejected",
})


def should_notify(action, allowed_actions=None):
    """Only send reading material, conclusions, decisions and intervention requests."""
    allowed = REVIEW_ACTIONS if allowed_actions is None else allowed_actions
    return action in REVIEW_ACTIONS and action in allowed


TITLES = {
    "paper.note_saved": "Paper study report", "literature.report": "Research synthesis",
    "topic.awaiting_selection": "Choose a research topic",
    "hypothesis.verified": "Experimental conclusions", "campaign.result": "Research results",
    "workflow.blocked": "Research issue requiring your input",
    "selection.stale_rejected": "Confirm the current topic revision",
}
VALUES = {
    "AWAITING_SELECTION": "Awaiting topic selection",
    "EVIDENCE_BLOCKED": "Insufficient evidence", "UNRESOLVED": "Unresolved",
    "CANDIDATE": "Candidate topic", "COVERED": "Covered by prior work",
    "hard": "Verified major-venue evidence", "supplement": "Supplementary evidence",
}
FIELDS = {
    "topic": "Topic", "topic_id": "Topic", "revision": "Topic revision",
    "provided_revision": "Selected revision", "current_revision": "Current revision",
    "campaign": "Research campaign", "hypothesis": "Hypothesis", "run": "Experiment",
    "phase": "Phase", "stage": "Stage", "provider": "Provider", "query": "Query",
    "direction": "Citation direction", "relevance": "Relevance to this research",
    "decision": "Assessment", "outcome": "Outcome", "status": "Status", "count": "Count",
    "pages": "PDF pages", "round": "Refinement round", "elapsed_seconds": "Elapsed seconds",
    "outcomes": "Outcome counts", "statistics": "Measurements and statistics",
    "findings": "Findings", "question": "Research question", "gap": "Bounded research gap",
    "feasibility": "Feasibility", "limitations": "Limitations", "reason": "Reason",
    "error": "Error", "artifact": "Research artifact", "path": "Path", "source": "Source",
    "closest_papers": "Closest related work", "approval": "Selection record",
    "audit_pass": "Evidence audit passed", "sha256": "SHA-256", "producer": "Producer",
    "title": "Paper title", "published_date": "Publication date",
    "contribution": "Contribution", "evidence_role": "Evidence tier",
}


def units(text):
    return len(text.encode("utf-16-le")) // 2


def chunks(text, limit):
    current = ""
    for character in text:
        if units(current + character) > limit:
            yield current
            current = ""
        current += character
    if current:
        yield current


def translated(value):
    if isinstance(value, dict):
        return {k: translated(v) for k, v in value.items()}
    if isinstance(value, list):
        return [translated(v) for v in value]
    if isinstance(value, str):
        return VALUES.get(value, value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return value


def build_messages(action, data, event_id, sequence, created):
    if action == "paper.note_saved":
        data = dict(data)
        data.setdefault("published_date", "Not available")
    title = TITLES.get(action, "Research report")
    identifier = next((data[k] for k in ("entity", "topic", "topic_id", "paper", "job", "campaign") if data.get(k)), None)
    if identifier:
        title += f" ({identifier})"
    summary = data.get("summary", "")
    description = summary if isinstance(summary, str) and summary.strip() else title + "."
    if action == "topic.awaiting_selection":
        description = "Review the research question, related work, bounded gap and limitations, then approve, revise, reject or defer this topic in the chat interface. Planning and experiments wait for your selection."
    elif action == "campaign.result":
        description = "Review the experimental conclusions, statistical evidence and limitations for all hypotheses, including supported, unsupported, inconclusive and unevaluated hypotheses."
    field_parts = []
    ordered_keys = [key for key in ("title", "source", "published_date") if key in data]
    ordered_keys.extend(key for key in data if key not in {"title", "source", "published_date"})
    if action == "topic.awaiting_selection":
        ordered_keys = [key for key in ordered_keys if key in {
            "revision", "question", "closest_papers", "gap", "feasibility", "limitations"}]
    for key in ordered_keys:
        value = data[key]
        if key in {"entity", "job", "paper", "result"} or key not in FIELDS or value is None or value == "":
            continue
        text = json.dumps(translated(value), ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else str(translated(value))
        if action == "topic.awaiting_selection":
            if units(text) > 650:
                text = next(chunks(text, 610)) + "… See the attached PDF for details."
        for i, part in enumerate(chunks(text, 900), 1):
            field_parts.append({"name": FIELDS[key] + (f" (part {i})" if units(text) > 900 else ""), "value": part, "inline": key not in {"question", "gap", "feasibility", "limitations", "statistics", "findings", "reason", "error"}})
    pages = []
    descriptions = list(chunks(description, 3500)) or [title + "."]
    for paragraph in descriptions:
        embed = {"title": title, "description": paragraph, "color": 0xE67E22 if any(x in action for x in ("failed", "blocked", "invalid", "interrupted")) else 0x2ECC71 if action in {"campaign.result", "hypothesis.verified"} else 0x3498DB, "timestamp": created, "footer": {"text": f"Event {event_id} | Sequence {sequence}"}, "fields": []}
        pages.append(embed)
    for field in field_parts:
        embed = pages[-1]
        size = units(embed["title"] + embed["description"] + embed["footer"]["text"]) + sum(units(f["name"] + f["value"]) for f in embed["fields"])
        if len(embed["fields"]) >= 25 or size + units(field["name"] + field["value"]) > 5500:
            embed = {"title": title, "description": "Report details continued.", "color": pages[0]["color"], "timestamp": created, "footer": dict(pages[0]["footer"]), "fields": []}
            pages.append(embed)
        embed["fields"].append(field)
    for index, embed in enumerate(pages, 1):
        if len(pages) > 1:
            embed["footer"]["text"] += f" | Part {index}/{len(pages)}"
    payloads = [{"embeds": [embed], "allowed_mentions": {"parse": []}} for embed in pages]
    if action in {"campaign.result", "paper.note_saved", "literature.report", "topic.awaiting_selection"} and data.get("result"):
        payloads[0]["_attachment"] = data["result"]
    return payloads
