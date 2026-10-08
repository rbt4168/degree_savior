from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import psutil

from .agent import CodexAgent, terminate_tree
from .common import BudgetExceeded, Cancelled, ResearchError, atomic_write, digest, file_hash, markdown, new_id, now, safe_path
from .config import load_config
from .context import Context
from .discord import Notifier
from .literature import ScholarlySources
from .store import Store


class Service:
    def __init__(self, root, *, agent=None, sources=None):
        self.root = Path(root).resolve()
        self.config = load_config(self.root)
        self.store = Store(self.root)
        self.agent = agent or CodexAgent(self.root)
        self.sources = sources or ScholarlySources(self.root)
        self._hash_cache = {}

    def close(self):
        self.store.close()

    def initialize(self):
        for name in ("ideas", "papers", "topic", "hypothesis", "experiments", "results", "state"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.store.event("system.initialized", {"root": str(self.root), "summary": "Three-phase local research automation; topic selection is mandatory."}, "system:initialized")

    def write(self, relative, content, producer="interface"):
        path = safe_path(self.root, relative)
        atomic_write(path, content)
        self.store.artifact(relative, file_hash(path), producer)

    def cached_hash(self, relative):
        path = safe_path(self.root, relative)
        if not path.is_file():
            raise ResearchError(f"Required artifact is missing: {relative}")
        stat = path.stat()
        fingerprint = (stat.st_size, stat.st_mtime_ns)
        previous = self._hash_cache.get(relative)
        if previous and previous[0] == fingerprint:
            return previous[1]
        value = file_hash(path)
        self._hash_cache[relative] = (fingerprint, value)
        return value

    def evidence_bundle(self, topic):
        bundle = {}
        for identifier in topic.get("papers", []):
            paper = self.store.get("paper", identifier)
            if paper.get("full_text_status") != "verified":
                continue
            for path_key, hash_key in (("pdf_path", "pdf_sha256"), ("note_path", "note_sha256")):
                actual = self.cached_hash(paper[path_key])
                if actual != paper[hash_key]:
                    raise ResearchError(f"Paper evidence has changed: {paper[path_key]}")
                bundle[paper[path_key]] = actual
        if topic.get("assessment"):
            relative = f"topic/{topic['id']}-survey.md"
            bundle[relative] = self.cached_hash(relative)
        return bundle

    def save_topic(self, topic, ctx=None, allow_decision_change=False):
        if ctx:
            ctx.guard()
            current = self.store.get("topic", topic["id"])
            if current.get("latest_decision") != topic.get("latest_decision") or current["original_idea"] != topic["original_idea"]:
                raise Cancelled("Topic changed while its review was running")
        bundle = self.evidence_bundle(topic)
        topic["evidence_bundle"] = bundle
        topic["evidence_bundle_hash"] = digest(bundle)
        scientific = {"question": topic["question"], "original_idea": topic["original_idea"], "assessment": topic.get("assessment"), "evidence": bundle}
        topic["revision"] = digest(scientific)[:16]
        assessment = topic.get("assessment", {})
        sections = [
            ("Original idea and research question", topic["original_idea"] + "\n\nQuestion: " + topic["question"]),
            ("Motivation and closest related work", assessment.get("motivation", "Review pending") + "\n\nClosest paper IDs: " + str(assessment.get("closest_papers", []))),
            ("Proposed gap and bounded novelty", assessment.get("proposed_gap", "No assessment yet") + f"\n\nAssessment is limited to recorded searches as of {topic.get('search_as_of', 'pending')}; no global absence of prior work is established."),
            ("Feasibility and evidence limitations", assessment.get("feasibility", "Pending") + "\n\n" + assessment.get("coverage_limits", "Pending")),
            ("Selection", f"Status: {topic['status']}; revision: {topic['revision']}; latest decision: {topic.get('latest_decision', 'none')}.\n\nHypothesis planning requires explicit user approval of this revision. Editing this section cannot authorize execution."),
            ("Current blocker", topic.get("blocker", "None recorded")),
            ("Artifacts and history", f"[Survey]({topic['id']}-survey.md)" if topic.get("assessment") else "Survey not produced yet"),
        ]
        body = markdown({"topic_id": topic["id"], "idea_id": topic["idea_id"], "revision": topic["revision"], "workflow_status": topic["status"], "evidence_bundle_hash": topic["evidence_bundle_hash"]}, topic["question"], sections)
        relative = f"topic/{topic['id']}.md"
        path = safe_path(self.root, relative)
        previous_hash = file_hash(path) if path.exists() else None
        topic["document_hash"] = digest(body.encode("utf-8"))
        publication = {"id": topic["id"], "status": "pending", "topic": dict(topic), "path": relative, "body": body, "expected_hash": topic["document_hash"], "previous_hash": previous_hash, "allow_decision_change": allow_decision_change}
        self.store.put("publication", topic["id"], publication)
        if ctx:
            ctx.write(relative, body)
        else:
            self.write(relative, body)
        topic["document_hash"] = file_hash(safe_path(self.root, relative))
        snapshot = f"topic/history/{topic['id']}/{topic['revision']}.json"
        if not safe_path(self.root, snapshot).exists():
            self.write(snapshot, json.dumps(scientific, ensure_ascii=False, indent=2))
        with self.store.transaction():
            current = self.store.maybe("topic", topic["id"])
            if current and not allow_decision_change and current.get("latest_decision") != topic.get("latest_decision"):
                raise Cancelled("A newer user decision superseded this topic update")
            self.store._put("topic", topic["id"], topic)
        publication["status"] = "done"
        self.store.put("publication", topic["id"], publication)
        return topic

    def submit(self, text, discovery=False, search_queries=None):
        if not text.strip():
            raise ResearchError("An idea or research area is required")
        if search_queries is not None:
            if not isinstance(search_queries, list) or any(not isinstance(q, str) for q in search_queries):
                raise ResearchError("Search queries must be a list of two distinct nonempty strings")
            search_queries = list(dict.fromkeys(q.strip() for q in search_queries if q.strip()))
            if len(search_queries) != 2:
                raise ResearchError("Exactly two distinct nonempty search queries are required")
        self.initialize()
        idea_id, identifier = new_id("idea"), new_id("t")
        source = "agent_discovery" if discovery else "user"
        topic = {"id": identifier, "idea_id": idea_id, "source": source, "original_idea": text, "question": text, "status": "REVIEWING", "papers": [], "created_at": now()}
        if search_queries is not None:
            topic["search_queries"] = search_queries
        self.write(f"ideas/{idea_id}.md", markdown({"idea_id": idea_id, "source": source, "created_at": now(), "topic_id": identifier}, "Research input", [("Original input", text), ("Initial search queries", json.dumps(search_queries, ensure_ascii=False) if search_queries else "Generated during review"), ("Resources", json.dumps(self.config)), ("Related topic", f"[{identifier}](../topic/{identifier}.md)")]))
        self.store.put("idea", idea_id, {"id": idea_id, "text": text, "source": source, "topic_id": identifier})
        self.save_topic(topic)
        self.store.event("idea.accepted", {"idea": idea_id, "topic": identifier, "source": source, "summary": text})
        self.store.enqueue("review", identifier)
        return topic

    def approve(self, identifier, revision, instruction, limits=None, actor="user"):
        topic = self.store.get("topic", identifier)
        if revision != topic["revision"]:
            self.store.event("selection.stale_rejected", {"topic": identifier, "provided_revision": revision, "current_revision": topic["revision"]})
            raise ResearchError("Topic revision changed; inspect and select the current revision")
        if topic["status"] not in {"AWAITING_SELECTION", "DEFERRED", "COMPLETED", "PARTIAL", "BLOCKED"} or topic.get("assessment", {}).get("decision") != "CANDIDATE":
            raise ResearchError("Only an evidence-backed selectable candidate can be approved")
        if self.cached_hash(f"topic/{identifier}.md") != topic["document_hash"] or digest(self.evidence_bundle(topic)) != topic["evidence_bundle_hash"]:
            raise ResearchError("Topic/evidence files changed; review and regenerate before approval")
        chosen_limits = dict(self.config)
        if limits:
            if limits.keys() - chosen_limits.keys():
                raise ResearchError("Unknown budget override")
            chosen_limits.update(limits)
        for key, value in chosen_limits.items():
            if key == "paid_compute":
                if value is not False:
                    raise ResearchError("Paid compute provisioning is not enabled")
            elif not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ResearchError("Approval limits must be positive finite integers")
        if not instruction.strip() or actor != "user":
            raise ResearchError("Approval requires the original explicit user instruction")
        decision_id, campaign_id = new_id("approval"), new_id("c")
        decision = {"id": decision_id, "topic_id": identifier, "topic_revision": revision, "evidence_hash": topic["evidence_bundle_hash"], "action": "approve", "actor": actor, "instruction": instruction, "scope": topic["question"], "limits": chosen_limits, "created_at": now()}
        campaign = {"id": campaign_id, "topic_id": identifier, "topic_revision": revision, "approval_id": decision_id, "limits": chosen_limits, "status": "PLANNING", "hypothesis_ids": [], "outcomes": {}, "usage": {}, "elapsed_seconds": 0, "created_at": now()}
        campaign["topic_snapshot"] = dict(topic)
        for suffix in ("topic", "survey"):
            snapshot_path = f"topic/history/{identifier}/{revision}-{suffix}.md"
            original_path = f"topic/{identifier}.md" if suffix == "topic" else f"topic/{identifier}-survey.md"
            if not safe_path(self.root, snapshot_path).exists():
                self.write(snapshot_path, safe_path(self.root, original_path).read_bytes())
            campaign[f"{suffix}_snapshot_path"] = snapshot_path
        with self.store.transaction():
            self.store._put("decision", decision_id, decision)
            self.store._put("campaign", campaign_id, campaign)
            topic.update({"latest_decision": decision_id, "campaign_id": campaign_id, "status": "APPROVED"})
            self.store._put("topic", identifier, topic)
            self.store._event("selection.approved", {"topic": identifier, "revision": revision, "approval": decision_id, "campaign": campaign_id, "scope": topic["question"], "limits": chosen_limits})
        self.save_topic(topic)
        self.store.enqueue("plan", campaign_id)
        return campaign

    def require_approval(self, identifier, approval_id):
        topic = self.store.get("topic", identifier)
        decision = self.store.get("decision", approval_id)
        if topic.get("latest_decision") != approval_id or decision["action"] != "approve" or decision["actor"] != "user" or decision["topic_id"] != identifier or decision["topic_revision"] != topic["revision"] or decision["evidence_hash"] != topic["evidence_bundle_hash"] or topic["status"] in {"REJECTED", "DEFERRED", "CANCELLED", "REVIEWING", "AWAITING_SELECTION"}:
            raise ResearchError("Missing, stale, revoked, or unrelated topic approval")
        if self.cached_hash(f"topic/{identifier}.md") != topic["document_hash"] or digest(self.evidence_bundle(topic)) != decision["evidence_hash"]:
            raise ResearchError("Approved topic/evidence content changed")
        return topic

    def validate_frozen_plan(self, plan):
        self.require_approval(plan["topic_id"], plan["approval_id"])
        if self.cached_hash(plan["plan_path"]) != plan["document_hash"] or self.cached_hash(plan["json_path"]) != plan["json_hash"]:
            raise ResearchError("Frozen hypothesis plan changed after validation")

    def ensure_execution(self, campaign):
        self.require_approval(campaign["topic_id"], campaign["approval_id"])
        self.store.enqueue("execute", campaign["id"])

    def decide(self, identifier, action, instruction):
        if action not in {"reject", "defer", "revise", "cancel"}:
            raise ResearchError("Unknown selection action")
        topic = self.store.get("topic", identifier)
        decision_id = new_id("decision")
        decision = {"id": decision_id, "topic_id": identifier, "topic_revision": topic["revision"], "action": action, "actor": "user", "instruction": instruction, "created_at": now()}
        self.store.put("decision", decision_id, decision, "selection." + action, instruction)
        self.cancel_jobs(identifier)
        topic.update({"latest_decision": decision_id, "status": {"reject": "REJECTED", "defer": "DEFERRED", "revise": "REVIEWING", "cancel": "CANCELLED"}[action]})
        if action == "revise":
            topic.update({"original_idea": topic["original_idea"] + "\n\nUser revision: " + instruction, "question": instruction, "papers": []})
            topic.pop("assessment", None)
        self.save_topic(topic, allow_decision_change=True)
        if action == "revise":
            self.store.enqueue("review", identifier)
        return topic

    def cancel_jobs(self, identifier):
        campaigns = {c["id"] for c in self.store.list("campaign") if c["topic_id"] == identifier}
        rows = list(self.store.db.execute("SELECT id,entity FROM jobs WHERE status IN ('running','queued')"))
        for row in rows:
            if row["entity"] == identifier or row["entity"] in campaigns:
                self.store.finish(row["id"], "cancelled", "User revoked or cancelled work")
        for run in self.store.list("run"):
            if run["campaign_id"] in campaigns and run["status"] == "RUNNING":
                atomic_write(safe_path(self.root, run["request_path"]).parent / "cancel", "user cancellation")
        from .experiments import write_report
        for campaign_id in campaigns:
            campaign = self.store.get("campaign", campaign_id)
            if campaign["status"] not in {"COMPLETED", "CANCELLED"}:
                campaign["status"] = "CANCELLED"
                for hypothesis in campaign.get("hypothesis_ids", []):
                    campaign.setdefault("outcomes", {}).setdefault(hypothesis, {"hypothesis_id": hypothesis, "outcome": "CANCELLED", "reason": "User revoked or cancelled the campaign"})
                self.store.put("campaign", campaign_id, campaign)
                report_context = Context(self, {"id": "interface-cancellation", "kind": "execute", "entity": campaign_id, "data": {"usage": {}}})
                write_report(report_context, campaign)

    def resume(self, job_id):
        row = self.store.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row or row["status"] not in {"blocked", "cancelled"}:
            raise ResearchError("Only blocked/interrupted jobs can be resumed")
        if row["kind"] == "review":
            topic = self.store.get("topic", row["entity"])
            if topic["status"] in {"REJECTED", "DEFERRED", "CANCELLED"}:
                raise ResearchError("Topic decision must be revised before resuming")
        else:
            campaign = self.store.get("campaign", row["entity"])
            self.require_approval(campaign["topic_id"], campaign["approval_id"])
            campaign["outcomes"] = {k: v for k, v in campaign.get("outcomes", {}).items() if v["outcome"] not in {"BLOCKED", "CANCELLED"}}
            self.store.put("campaign", campaign["id"], campaign)
        self.store.db.execute("UPDATE jobs SET status='queued',error=NULL WHERE id=?", (job_id,))
        self.store.event("job.resumed", {"job": job_id})

    def run_next(self):
        job = self.store.claim()
        if not job:
            return False
        ctx = Context(self, job)
        try:
            if job["kind"] == "review":
                from .literature import review
                review(ctx)
            elif job["kind"] == "plan":
                campaign = self.store.get("campaign", job["entity"])
                topic = self.require_approval(campaign["topic_id"], campaign["approval_id"])
                topic["status"] = "PLANNING"
                self.save_topic(topic)
                from .hypothesis import plan_hypotheses
                plan_hypotheses(ctx)
            elif job["kind"] == "execute":
                campaign = self.store.get("campaign", job["entity"])
                topic = self.require_approval(campaign["topic_id"], campaign["approval_id"])
                topic["status"] = "EXECUTING"
                self.save_topic(topic)
                from .experiments import execute_campaign
                execute_campaign(ctx)
            else:
                raise ResearchError("Unknown workflow job type")
            self.store.finish(job["id"], "cancelled" if ctx.cancelled() else "done")
        except Exception as error:
            if not isinstance(error, ResearchError):
                import sys
                import traceback
                from .common import redact
                print(redact(traceback.format_exc()), file=sys.stderr)
            reason = str(error) if isinstance(error, ResearchError) else f"{type(error).__name__}: inspect worker log"
            if job["kind"] == "review":
                topic = self.store.get("topic", job["entity"])
                if topic["status"] not in {"REJECTED", "DEFERRED", "CANCELLED", "AWAITING_SELECTION"}:
                    topic["status"] = "EVIDENCE_BLOCKED" if "PDF" in reason or "evidence" in reason.lower() else "UNRESOLVED"
                    topic["blocker"] = reason
                    self.save_topic(topic)
            else:
                campaign = self.store.get("campaign", job["entity"])
                campaign.update({"status": "CANCELLED" if isinstance(error, Cancelled) else "BLOCKED", "error": reason})
                self.store.put("campaign", campaign["id"], campaign)
                from .experiments import write_report
                for identifier in campaign.get("hypothesis_ids", []):
                    campaign.setdefault("outcomes", {}).setdefault(identifier, {"hypothesis_id": identifier, "outcome": "CANCELLED" if isinstance(error, Cancelled) else "BLOCKED", "reason": reason})
                write_report(ctx, campaign)
            self.store.finish(job["id"], "cancelled" if isinstance(error, Cancelled) else "blocked", reason)
            self.store.event("workflow.blocked", {"job": job["id"], "phase": job["kind"], "reason": reason})
        finally:
            ctx.checkpoint()
            if job["kind"] != "review":
                campaign = self.store.get("campaign", job["entity"])
                campaign["elapsed_seconds"] = campaign.get("elapsed_seconds", 0) + time.monotonic() - ctx.started
                self.store.put("campaign", campaign["id"], campaign)
        return True

    def recover(self):
        for publication in self.store.list("publication"):
            if publication["status"] != "pending":
                continue
            candidate = publication["topic"]
            current = self.store.maybe("topic", candidate["id"])
            explicit_decision = self.store.maybe("decision", candidate.get("latest_decision", ""))
            allowed_change = publication.get("allow_decision_change") and explicit_decision and explicit_decision.get("actor") == "user"
            if current and current.get("latest_decision") != candidate.get("latest_decision") and not allowed_change:
                publication["status"] = "obsolete"
                self.store.put("publication", candidate["id"], publication)
                continue
            path = safe_path(self.root, publication["path"])
            actual = file_hash(path) if path.exists() else None
            if actual not in {publication["expected_hash"], publication["previous_hash"], None}:
                self.store.event("workflow.blocked", {"reason": "待恢復的主題檔案已被另外修改，保留檔案並停止自動覆寫。", "path": publication["path"]})
                continue
            if actual != publication["expected_hash"]:
                self.write(publication["path"], publication["body"], "publication-recovery")
            self.store.put("topic", candidate["id"], candidate)
            publication["status"] = "done"
            self.store.put("publication", candidate["id"], publication)
            self.store.event("artifact.publication_recovered", {"path": publication["path"], "summary": "已完成檔案與資料庫之間中斷的主題寫入；未建立新的使用者批准。"})
        for row in list(self.store.db.execute("SELECT id FROM jobs WHERE status='running'")):
            self.store.db.execute("UPDATE jobs SET status='queued' WHERE id=?", (row["id"],))
            self.store.event("job.recovered", {"job": row["id"], "summary": "Validated artifacts and owned process records will be reconciled before redispatch."})
        for path in (self.root / "state/agent").glob("*/owner.json"):
            owner = json.loads(path.read_text(encoding="utf-8"))
            try:
                process = psutil.Process(owner["pid"])
                if abs(process.create_time() - owner["created"]) < 0.01:
                    terminate_tree(process)
            except psutil.Error:
                pass
        # Recover approval -> enqueue and planning -> enqueue crash windows.
        for campaign in self.store.list("campaign"):
            if campaign["status"] in {"PLANNING", "EXECUTING"}:
                try:
                    self.require_approval(campaign["topic_id"], campaign["approval_id"])
                    self.store.enqueue("execute" if campaign.get("hypothesis_ids") else "plan", campaign["id"])
                except ResearchError:
                    continue

    def worker(self, once=False, drain=False):
        self.initialize()
        lock_path = self.root / "state/worker.lock"
        with lock_path.open("a+b") as lock:
            lock.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ResearchError("A worker is already active for this workspace") from None
            owner = {"pid": os.getpid(), "created": psutil.Process().create_time(), "started": now(), "status": "RUNNING", "stop_requested": False}
            self.store.put("runtime", "worker", owner, "worker.started", str(os.getpid()))
            stop = threading.Event()
            def sender():
                connection = Store(self.root)
                notifier = Notifier(connection)
                try:
                    while not stop.is_set():
                        notifier.flush()
                        stop.wait(1)
                finally:
                    connection.close()
            thread = threading.Thread(target=sender, name="discord-outbox", daemon=True)
            thread.start()
            try:
                self.recover()
                while not self.store.get("runtime", "worker").get("stop_requested"):
                    worked = self.run_next()
                    if once or (drain and not worked):
                        break
                    if not worked:
                        time.sleep(self.config["poll_seconds"])
            finally:
                owner["status"] = "STOPPED"
                self.store.put("runtime", "worker", owner, "worker.stopped", str(os.getpid()))
                stop.set()
                thread.join(timeout=25)
                Notifier(self.store).flush()

    def stop_worker(self):
        owner = self.store.maybe("runtime", "worker")
        if not owner:
            return
        owner["stop_requested"] = True
        self.store.put("runtime", "worker", owner, "worker.stop_requested", "Worker will stop after the active action; use cancel to stop a campaign immediately.")
