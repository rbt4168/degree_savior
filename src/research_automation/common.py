from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

_configured_secrets = frozenset()


class ResearchError(Exception):
    pass


class BudgetExceeded(ResearchError):
    pass


class Cancelled(ResearchError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    if not isinstance(value, bytes):
        value = canonical(value).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def safe_path(root, relative):
    root = Path(root).resolve()
    relative = str(relative)
    if Path(relative).is_absolute() or "\\" in relative or ":" in relative:
        raise ResearchError("Artifact path must be a workspace-relative POSIX path")
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or target == root:
        raise ResearchError("Artifact path escapes the workspace")
    for part in Path(relative).parts:
        if part in {"..", "."} or part.rstrip(" .") != part:
            raise ResearchError("Invalid artifact path component")
        if part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
            raise ResearchError("Reserved artifact filename")
    return target


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        content = content.encode("utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(20):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                # Windows scanners/readers can briefly prevent replacement.
                if attempt == 19:
                    raise
                time.sleep(0.05)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def markdown(metadata, title, sections):
    # JSON scalar/array values are valid YAML values; no YAML parser is needed.
    header = "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in metadata.items())
    body = "\n\n".join(f"## {heading}\n\n{text}" for heading, text in sections)
    return f"---\n{header}\n---\n\n# {title}\n\n{body}\n"


def register_secrets(values):
    global _configured_secrets
    # Keep loaded and rotated values in memory for log/event redaction only.
    _configured_secrets = _configured_secrets.union(value for value in values if isinstance(value, str) and value)


def redact(text):
    text = str(text)
    text = re.sub(r"https://(?:[^/]*discord[^/]*)/api/(?:v\d+/)?webhooks/[^\s\"']+", "[REDACTED_WEBHOOK]", text)
    values = _configured_secrets.union(os.environ.get(key, "") for key in ("DISCORD_WEBHOOK_URL", "OPENALEX_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY"))
    for secret in sorted(filter(None, values), key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    return text


def child_environment():
    # Keep normal OS/CLI auth discovery, but remove notification and API secrets.
    forbidden = {"DISCORD_WEBHOOK_URL", "OPENALEX_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY"}
    env = {k: v for k, v in os.environ.items() if k.upper() not in forbidden and not any(x in k.upper() for x in ("WEBHOOK", "SECRET", "TOKEN", "PASSWORD"))}
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2"})
    return env


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def tree_size(root):
    total = 0
    for path in Path(root).rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except FileNotFoundError:
            # Atomic rename/removal can race a filesystem walk.
            continue
    return total
