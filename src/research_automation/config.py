from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import dotenv_values

from .common import ResearchError, atomic_write, digest, register_secrets


DEFAULTS = {
    "agent_timeout_seconds": 600, "max_agent_calls": 45,
    "max_queries": 18, "max_candidates": 60, "max_full_texts": 12,
    "max_search_seconds": 1800, "max_hypotheses": 3, "max_runs": 150,
    "max_campaign_seconds": 7200, "max_run_seconds": 300,
    "memory_mb": 4096, "disk_mb": 2048, "max_output_mb": 16,
    "evaluation_budget": 1000, "max_notification_backlog": 1000,
    "heartbeat_seconds": 300, "poll_seconds": 2, "paid_compute": False,
}


def load_config(root):
    values = dict(DEFAULTS)
    path = Path(root) / "research.json"
    if path.exists():
        supplied = json.loads(path.read_text(encoding="utf-8"))
        unknown = supplied.keys() - DEFAULTS.keys()
        if unknown:
            raise ResearchError(f"Unknown configuration keys: {sorted(unknown)}")
        values.update(supplied)
    for key, value in values.items():
        if key == "paid_compute":
            if value is not False:
                raise ResearchError("This local runner does not provision paid compute")
        elif not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ResearchError(f"{key} must be a positive finite integer")
    return values


def secret_path(root):
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return base / "ResearchAutomation" / digest(str(Path(root).resolve()))[:16] / "secrets.json"


def secrets(root):
    path = secret_path(root)
    stored = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    # Explicit workspace path: never discover another project's .env or export
    # its contents into the coordinator/experiment subprocess environment.
    env_path = Path(root).resolve() / ".env"
    dotenv = dotenv_values(env_path, encoding="utf-8-sig", interpolate=False) if env_path.is_file() else {}
    keys = ("DISCORD_WEBHOOK_URL", "OPENALEX_API_KEY")
    values = {key: os.environ.get(key) or dotenv.get(key) or stored.get(key, "") for key in keys}
    register_secrets(value for source in (os.environ, dotenv, stored) for key in keys if (value := source.get(key)))
    return values


def configure_secret(root, key, value):
    if key not in {"DISCORD_WEBHOOK_URL", "OPENALEX_API_KEY"}:
        raise ResearchError("Unsupported secret")
    path = secret_path(root)
    stored = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    stored[key] = value.strip()
    atomic_write(path, json.dumps(stored))
    if os.name != "nt":
        path.chmod(0o600)
    return path
