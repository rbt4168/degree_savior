from __future__ import annotations

import time

from .common import BudgetExceeded, Cancelled, ResearchError, atomic_write, canonical, file_hash, safe_path, tree_size


class Context:
    def __init__(self, service, job):
        self.service, self.store, self.agent = service, service.store, service.agent
        self.root, self.config = service.root, dict(service.config)
        if job["kind"] != "review":
            self.config.update(self.store.get("campaign", job["entity"])["limits"])
        self.job = job
        self.data = job["data"]
        self.data.setdefault("usage", {})
        self.started = time.monotonic()
        self.last_heartbeat = self.started
        self.previous_seconds = self.data["usage"].get("seconds", 0)

    def checkpoint(self):
        self.data["usage"]["seconds"] = self.previous_seconds + time.monotonic() - self.started
        self.store.checkpoint(self.job["id"], self.data)

    def cancelled(self):
        row = self.store.db.execute("SELECT status FROM jobs WHERE id=?", (self.job["id"],)).fetchone()
        return not row or row["status"] == "cancelled"

    def guard(self):
        if self.cancelled():
            raise Cancelled("Job cancelled by user")
        if self.job["kind"] != "review":
            # Explicit CLI budget amendments apply at the next guard check.
            self.config.update(self.store.get("campaign", self.job["entity"])["limits"])
        limit = self.config["max_search_seconds"] if self.job["kind"] == "review" else self.config["max_campaign_seconds"]
        if self.previous_seconds + time.monotonic() - self.started > limit:
            raise BudgetExceeded("Phase elapsed-time budget exhausted")
        if self.store.pending_count() >= self.config["max_notification_backlog"]:
            raise BudgetExceeded("Notification backlog limit reached; deliver/replay before resuming")
        size = sum(tree_size(self.root / folder) for folder in ("papers", "experiments", "results", "state"))
        if size > self.config["disk_mb"] * 1024 * 1024:
            raise BudgetExceeded("Workspace research disk budget exhausted")
        if self.job["kind"] != "review":
            campaign = self.store.get("campaign", self.job["entity"])
            self.service.require_approval(campaign["topic_id"], campaign["approval_id"])
            used = campaign.get("elapsed_seconds", 0) + time.monotonic() - self.started
            if used > campaign["limits"]["max_campaign_seconds"]:
                raise BudgetExceeded("Campaign elapsed-time budget exhausted")

    def reserve(self, counter, limit_key, key=None):
        self.guard()
        usage = self.data["usage"]
        reservations = self.data.setdefault("reservations", {}).setdefault(counter, [])
        if key is not None and key in reservations:
            return
        if self.job["kind"] != "review":
            campaign = self.store.get("campaign", self.job["entity"])
            campaign_usage = campaign.setdefault("usage", {})
            if campaign_usage.get(counter, 0) >= self.config[limit_key]:
                raise BudgetExceeded(f"Campaign {counter} budget exhausted")
            campaign_usage[counter] = campaign_usage.get(counter, 0) + 1
            self.store.put("campaign", campaign["id"], campaign)
        if usage.get(counter, 0) >= self.config[limit_key]:
            raise BudgetExceeded(f"{counter} budget exhausted")
        usage[counter] = usage.get(counter, 0) + 1
        if key is not None:
            reservations.append(key)
        self.checkpoint()

    def emit(self, action, **data):
        return self.store.event(action, {"job": self.job["id"], "entity": self.job["entity"], **data})

    def heartbeat(self):
        self.guard()
        if time.monotonic() - self.last_heartbeat >= self.config["heartbeat_seconds"]:
            self.emit("job.progress", elapsed_seconds=round(time.monotonic() - self.started), usage=self.data["usage"])
            self.last_heartbeat = time.monotonic()
            self.checkpoint()

    def ask(self, task, context, schema):
        self.guard()
        cached = self.agent.cached(task, context, schema)
        if cached is not None:
            self.emit("agent.reused", task=task[:120])
            return cached
        self.reserve("agent_calls", "max_agent_calls")
        self.emit("agent.started", task=task[:120])
        answer = self.agent.ask(task, context, schema, timeout=self.config["agent_timeout_seconds"], cancelled=self.cancelled, heartbeat=self.heartbeat)
        self.emit("agent.completed", task=task[:120])
        self.checkpoint()
        return answer

    def write(self, relative, content):
        path = safe_path(self.root, relative)
        expected = content.encode("utf-8") if isinstance(content, str) else content
        # A retry reconciles an already-finalized file and ensures its event exists.
        from .common import digest
        if not path.exists() or file_hash(path) != digest(expected):
            atomic_write(path, expected)
        self.store.artifact(relative, file_hash(path), self.job["id"])
        return relative

    def write_json(self, relative, value):
        return self.write(relative, canonical(value) + "\n")
