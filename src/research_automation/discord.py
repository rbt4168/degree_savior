from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .common import ResearchError, safe_path
from .config import secrets


class Notifier:
    def __init__(self, store, opener=None):
        self.store = store
        self.opener = opener or urllib.request.urlopen

    def flush(self, limit=50):
        self.store.reformat_pending()
        destination = secrets(self.store.root)["DISCORD_WEBHOOK_URL"]
        if not destination:
            return 0
        parsed = urllib.parse.urlsplit(destination)
        if parsed.scheme != "https" or parsed.hostname != "discord.com" or not parsed.path.startswith("/api/webhooks/"):
            raise ResearchError("Discord webhook destination is invalid")
        query = urllib.parse.parse_qs(parsed.query)
        query["wait"] = ["true"]
        destination = urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query, doseq=True)))
        delivered = 0
        for _ in range(limit):
            # An earlier pending message waits before later messages; dead messages remain visible.
            row = self.store.db.execute("SELECT * FROM outbox WHERE status IN ('pending','sending') ORDER BY seq,part LIMIT 1").fetchone()
            if not row or row["next_at"] > time.time():
                break
            self.store.db.execute("UPDATE outbox SET status='sending' WHERE id=?", (row["id"],))
            payload = json.loads(row["payload"])
            attachment = payload.pop("_attachment", None)
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            content_type = "application/json"
            if attachment:
                path = safe_path(self.store.root, attachment)
                if path.is_file() and path.stat().st_size <= 1024 * 1024:
                    boundary = "research-" + uuid.uuid4().hex
                    attachment_type = "application/pdf" if path.suffix.lower() == ".pdf" else "text/markdown; charset=utf-8"
                    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\nContent-Type: application/json\r\n\r\n'.encode() + body + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="files[0]"; filename="{path.name}"\r\nContent-Type: {attachment_type}\r\n\r\n'.encode() + path.read_bytes() + f'\r\n--{boundary}--\r\n'.encode())
                    content_type = "multipart/form-data; boundary=" + boundary
            request = urllib.request.Request(destination, data=body, headers={"Content-Type": content_type, "User-Agent": "ResearchAutomation/0.1"}, method="POST")
            try:
                with self.opener(request, timeout=20) as response:
                    message = json.load(response)
                    message_id = message.get("id")
                    if not message_id:
                        raise ValueError("Missing delivery confirmation")
                    remaining = response.headers.get("X-RateLimit-Remaining")
                    delay = float(response.headers.get("X-RateLimit-Reset-After", "0")) if remaining == "0" else 0
                self.store.db.execute("UPDATE outbox SET status='sent',message_id=?,error=NULL WHERE id=?", (str(message_id), row["id"]))
                delivered += 1
                if delay:
                    self.store.db.execute("UPDATE outbox SET next_at=max(next_at,?) WHERE status='pending'", (time.time() + delay,))
                    break
            except urllib.error.HTTPError as error:
                if error.code == 413 and attachment:
                    payload["embeds"][0]["description"] += "\n完整報告附件超過目前傳送限制；報告已完整保存在本機。"
                    self.store.db.execute("UPDATE outbox SET status='pending',payload=?,next_at=0,error=? WHERE id=?", (json.dumps(payload, ensure_ascii=False), "Attachment exceeded upload limit; sending embed summary", row["id"]))
                elif error.code == 429:
                    try:
                        retry = float(json.loads(error.read()).get("retry_after", 2))
                    except (ValueError, TypeError):
                        retry = 2
                    self._retry(row, f"HTTP {error.code}", max(0.1, retry), count_attempt=False)
                elif error.code >= 500:
                    self._retry(row, f"HTTP {error.code}")
                else:
                    self.store.db.execute("UPDATE outbox SET status='dead',error=? WHERE id=?", (f"Permanent HTTP {error.code}", row["id"]))
                break
            except Exception as error:
                # Never log request URLs, HTTP bodies, or secret-bearing exception text.
                self._retry(row, type(error).__name__)
                break
        return delivered

    def _retry(self, row, reason, delay=None, count_attempt=True):
        attempts = row["attempts"] + int(count_attempt)
        status = "dead" if attempts >= 5 else "pending"
        if delay is None:
            delay = min(60, 2 ** attempts) + random.random()
        self.store.db.execute("UPDATE outbox SET status=?,attempts=?,next_at=?,error=? WHERE id=?", (status, attempts, time.time() + delay, reason, row["id"]))

    def replay(self):
        # Ambiguous deliveries may repeat; original event IDs are retained.
        self.store.db.execute("UPDATE outbox SET status='pending',attempts=0,next_at=0,error=NULL WHERE status!='sent'")
