from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .common import ResearchError, canonical, digest, new_id, now, redact
from .messages import build_messages, should_notify


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "state/research.sqlite3", timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS records(kind TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(kind,id));
          CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT, entity TEXT, status TEXT, data TEXT, error TEXT, created TEXT);
          CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, key TEXT UNIQUE, action TEXT, data TEXT, created TEXT);
          CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, seq INTEGER, part INTEGER, payload TEXT, status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, next_at REAL DEFAULT 0, message_id TEXT, error TEXT);
          CREATE TABLE IF NOT EXISTS artifacts(path TEXT PRIMARY KEY, hash TEXT, producer TEXT);
        """)

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def get(self, kind, entity):
        row = self.db.execute("SELECT data FROM records WHERE kind=? AND id=?", (kind, entity)).fetchone()
        if not row:
            raise ResearchError(f"Unknown {kind}: {entity}")
        return json.loads(row["data"])

    def maybe(self, kind, entity):
        try:
            return self.get(kind, entity)
        except ResearchError:
            return None

    def list(self, kind):
        return [json.loads(r["data"]) for r in self.db.execute("SELECT data FROM records WHERE kind=? ORDER BY rowid", (kind,))]

    def _put(self, kind, entity, value):
        self.db.execute("INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data", (kind, entity, canonical(value)))

    def put(self, kind, entity, value, action=None, summary="", event_key=None, *, event_data=None):
        with self.transaction():
            self._put(kind, entity, value)
            if kind == "run":
                self._put("attempt", value["id"], value)
            if action:
                self._event(action, {"entity": entity, "summary": summary, **(event_data or {})}, event_key)

    def _event(self, action, data, key=None):
        data = json.loads(redact(canonical(data)))
        if key:
            row = self.db.execute("SELECT id FROM events WHERE key=?", (key,)).fetchone()
            if row:
                return row["id"]
        event_id = new_id("evt")
        created = now()
        cursor = self.db.execute("INSERT INTO events(id,key,action,data,created) VALUES(?,?,?,?,?)", (event_id, key, action, canonical(data), created))
        sequence = cursor.lastrowid
        if not should_notify(action):
            return event_id
        for index, payload in enumerate(build_messages(action, data, event_id, sequence, created), 1):
            self.db.execute("INSERT INTO outbox(id,seq,part,payload) VALUES(?,?,?,?)", (f"{event_id}:{index}", sequence, index, canonical(payload)))
        return event_id

    def reformat_pending(self):
        # Preserve the audit event and delivered receipts, but remove unsent
        # muted notifications queued before the user's preference changed.
        for row in list(self.db.execute("SELECT DISTINCT events.seq,events.action FROM events JOIN outbox ON events.seq=outbox.seq WHERE outbox.status!='sent'")):
            if not should_notify(row["action"]):
                self.db.execute("DELETE FROM outbox WHERE seq=? AND status!='sent'", (row["seq"],))
        legacy = list(self.db.execute("SELECT DISTINCT events.* FROM events JOIN outbox ON events.seq=outbox.seq WHERE outbox.status!='sent' AND outbox.payload NOT LIKE '%\"embeds\"%'"))
        for event in legacy:
            with self.transaction():
                self.db.execute("DELETE FROM outbox WHERE seq=? AND status!='sent'", (event["seq"],))
                for part, payload in enumerate(build_messages(event["action"], json.loads(event["data"]), event["id"], event["seq"], event["created"]), 1):
                    self.db.execute("INSERT OR IGNORE INTO outbox(id,seq,part,payload) VALUES(?,?,?,?)", (f"{event['id']}:{part}", event["seq"], part, canonical(payload)))

    def event(self, action, data, key=None):
        with self.transaction():
            return self._event(action, data, key)

    def artifact(self, relative, content_hash, producer):
        with self.transaction():
            self.db.execute("INSERT INTO artifacts VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET hash=excluded.hash,producer=excluded.producer", (relative, content_hash, producer))
            self._event("artifact.saved", {"path": relative, "producer": producer, "sha256": content_hash}, f"artifact:{relative}:{content_hash}")

    def enqueue(self, kind, entity, data=None):
        with self.transaction():
            existing = self.db.execute("SELECT id FROM jobs WHERE kind=? AND entity=? AND status IN ('queued','running')", (kind, entity)).fetchone()
            if existing:
                return existing["id"]
            job = new_id("job")
            self.db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?)", (job, kind, entity, "queued", canonical(data or {"usage": {}}), None, now()))
            self._event("job.queued", {"job": job, "phase": kind, "entity": entity})
            return job

    def claim(self):
        with self.transaction():
            row = self.db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
            if not row:
                return None
            self.db.execute("UPDATE jobs SET status='running' WHERE id=?", (row["id"],))
            self._event("job.started", {"job": row["id"], "phase": row["kind"], "entity": row["entity"]})
        return dict(row) | {"data": json.loads(row["data"])}

    def checkpoint(self, job, data):
        self.db.execute("UPDATE jobs SET data=? WHERE id=?", (canonical(data), job))

    def finish(self, job, status="done", error=None):
        with self.transaction():
            self.db.execute("UPDATE jobs SET status=?,error=? WHERE id=?", (status, redact(error) if error else None, job))
            self._event(f"job.{status}", {"job": job, "error": redact(error) if error else ""})

    def pending_count(self):
        return self.db.execute("SELECT count(*) FROM outbox WHERE status!='sent'").fetchone()[0]

    def status(self):
        return {
            "topics": self.list("topic"), "campaigns": self.list("campaign"),
            "jobs": [dict(r) for r in self.db.execute("SELECT id,kind,entity,status,error FROM jobs ORDER BY rowid")],
            "notifications": [dict(r) for r in self.db.execute("SELECT status,count(*) AS count FROM outbox GROUP BY status")],
            "worker": self.maybe("runtime", "worker"),
        }
