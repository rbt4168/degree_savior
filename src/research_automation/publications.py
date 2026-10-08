"""Publication evidence supplied after inspecting an official proceedings/journal page."""
from urllib.parse import urlsplit
import re

from .common import digest


def title_key(title):
    return digest(" ".join(re.findall(r"\w+", title.lower())))


def major_only(store):
    return bool((store.maybe("policy", "literature") or {}).get("major_only"))


def classify(store, record):
    record = dict(record)
    if not major_only(store):
        record["evidence_role"] = "hard"
        return record
    policy = store.get("policy", "literature")
    proof = store.maybe("venue_evidence", record["id"]) or store.maybe("venue_title", title_key(record["title"]))
    valid = (proof and proof.get("official_verified") is True
             and proof.get("status") == "published"
             and proof.get("venue") in policy.get("major_venues", [])
             and urlsplit(proof.get("source_url", "")).hostname in policy.get("official_hosts", []))
    record["evidence_role"] = "hard" if valid else "supplement"
    if valid:
        record["publication"] = proof
        record["pdf_urls"] = list(dict.fromkeys(proof.get("pdf_urls", []) + record["pdf_urls"]))
    else:
        record.pop("publication", None)
    return record
