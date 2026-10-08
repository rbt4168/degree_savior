"""English presentation copies; source evidence and scientific decisions stay intact."""
import re
from decimal import Decimal

from .common import ResearchError


def quantities(text):
    months = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
              'August', 'September', 'October', 'November', 'December']
    text = re.sub(r'\b(' + '|'.join(months) + r')\s+([0-9]{4})\b',
                  lambda m: str(months.index(m.group(1)) + 1) + ' ' + m.group(2), text)
    scales = {"萬": 10000, "万": 10000, "億": 100000000, "亿": 100000000,
              "thousand": 1000, "million": 1000000, "billion": 1000000000}
    pattern = r"(?<![A-Za-z0-9_.])([+\-−]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?(?:[eE][+\-]?[0-9]+)?)\s*(萬|万|億|亿|thousand\b|million\b|billion\b)?"
    return {Decimal(number.replace(',', '').replace('−', '-')) * scales.get(unit.lower(), 1)
            for number, unit in re.findall(pattern, text, re.IGNORECASE)}


def english_sections(agent, sections, timeout):
    result = []
    schema = {"type": "object", "properties": {"sections": {"type": "array", "items": {
        "type": "object", "properties": {"label": {"type": "string"}, "text": {"type": "string"}},
        "required": ["label", "text"], "additionalProperties": False}}},
        "required": ["sections"], "additionalProperties": False}
    # Bound individual translation requests; preserve the order of every section.
    batches, current, size = [], [], 0
    for label, text in sections:
        item = {"label": str(label), "text": str(text)}
        if current and size + len(item["text"]) > 14000:
            batches.append(current)
            current, size = [], 0
        current.append(item)
        size += len(item["text"])
    if current:
        batches.append(current)
    for batch in batches:
        if not any(re.search(r"[\u3400-\u9fff]", item["label"] + item["text"]) for item in batch):
            result.extend((item["label"], item["text"]) for item in batch)
            continue
        task = (
            "Translate these report sections into English, in exactly the supplied order. "
            "This is a presentation copy, not a new analysis. Preserve all claims, uncertainty, "
            "limitations and evidence tiers; do not summarize, infer, add findings or declare novelty. "
            "Keep every numerical quantity, URL, DOI, technical term, identifier and verbatim English "
            "evidence excerpt unchanged. Keep English section labels unchanged. "
            "Chinese magnitude units may be converted to equivalent English units, such as 500 wan to 5 million. "
            "Return every section with label and text; do not leave Chinese prose in the output.")
        legacy_task = task.replace('numerical quantity', 'numeric literal').replace(
            'Chinese magnitude units may be converted to equivalent English units, such as 500 wan to 5 million. ', '')
        cached = agent.cached(legacy_task, {"sections": batch}, schema) if hasattr(agent, 'cached') else None
        answer = cached if isinstance(cached, dict) else agent.ask(task, {"sections": batch}, schema, timeout=timeout)
        translated = answer["sections"]
        if len(translated) != len(batch):
            raise ResearchError("English report translation omitted sections")
        for original, output in zip(batch, translated):
            output["text"] = re.sub(r"(?<!\w)([0-9]+)\s+ten[- ]thousand\b", lambda m: format(int(m.group(1)) * 10000, ','), output["text"])
            if re.search(r"[\u3400-\u9fff]", output["label"] + output["text"]):
                raise ResearchError("English report translation still contains Chinese prose")
            if not re.search(r"[\u3400-\u9fff]", original["label"]) and output["label"] != original["label"]:
                raise ResearchError("English report translation changed section order or labels")
            protected = re.findall(r"https?://[^\s<>()]+|\b(?:p|t|job)-[a-f0-9]+\b", original["text"])
            protected += re.findall(r"Evidence excerpt: ([^\n]+)", original["text"])
            protected += re.findall(r"\b(?:DiT|VAE|HVAE|GA|GP|CMA-ES|SRBench|ELBO|AST)\b", original["text"])
            if any(token not in output["text"] for token in protected) or not quantities(original["text"]).issubset(quantities(output["text"])):
                raise ResearchError("English report translation changed a source, identifier or numeric literal")
            result.append((output["label"], output["text"]))
    return result
