from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

from .agent import codex_command
from .common import ResearchError, child_environment
from .config import configure_secret, secrets
from .discord import Notifier
from .service import Service

# Retain intentionally detached Popen handles when used as an embedded Python API.
# CLI invocations exit after confirming startup; the worker survives independently.
_background_processes = []


def parser():
    p = argparse.ArgumentParser(prog="research", description="Literature -> human topic selection -> hypotheses -> verified experiments")
    p.add_argument("--root", default=".", help="Research workspace (default: current directory)")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("doctor")
    commands.add_parser("status")
    commands.add_parser("start", help="Start a hidden background worker")
    commands.add_parser("stop", help="Stop worker after active job; use cancel to interrupt research")
    submit = commands.add_parser("submit")
    submit.add_argument("idea", help="Idea or research area")
    submit.add_argument("--discover", action="store_true")
    submit.add_argument("--query", action="append", help="Pin an initial search query; supply exactly twice")
    approve = commands.add_parser("approve")
    approve.add_argument("topic")
    approve.add_argument("--revision", required=True)
    approve.add_argument("--instruction", required=True, help="Original explicit user selection")
    approve.add_argument("--limits", help="JSON object of finite campaign budget overrides")
    approve.add_argument("--campaign", help="Extend only the elapsed-time limit of this existing approved campaign")
    for command in ("reject", "defer", "revise", "cancel"):
        decision = commands.add_parser(command)
        decision.add_argument("topic")
        decision.add_argument("instruction")
    resume = commands.add_parser("resume")
    resume.add_argument("job")
    worker = commands.add_parser("worker")
    group = worker.add_mutually_exclusive_group()
    group.add_argument("--once", action="store_true")
    group.add_argument("--drain", action="store_true")
    events = commands.add_parser("events")
    events.add_argument("--limit", type=int, default=30)
    notifications = commands.add_parser("notifications")
    notifications.add_argument("--flush", action="store_true")
    notifications.add_argument("--replay", action="store_true")
    notifications.add_argument("--allow-actions", nargs="+", help="Replace live notification preferences with report/decision event names")
    secret = commands.add_parser("configure-secret")
    secret.add_argument("key", choices=["DISCORD_WEBHOOK_URL", "OPENALEX_API_KEY"])
    secret.add_argument("--stdin", action="store_true", help="Read secret from stdin, never command arguments")
    notify = commands.add_parser("notify")
    notify.add_argument("summary", help="Record a completed action and notify Discord")
    return p


def start_worker(service):
    _background_processes[:] = [p for p in _background_processes if p.poll() is None]
    owner = service.store.maybe("runtime", "worker")
    if owner and owner.get("status") == "RUNNING":
        try:
            process = psutil.Process(owner["pid"])
            if abs(process.create_time() - owner["created"]) < 0.01:
                return {"status": "already_running", "pid": owner["pid"]}
        except psutil.Error:
            pass
    service.initialize()
    with (service.root / "state/worker.stdout.log").open("ab") as stdout, (service.root / "state/worker.stderr.log").open("ab") as stderr:
        # The coordinator needs its configured environment; only inference and
        # experiment children remove notification/API secrets.
        coordinator_env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        process = subprocess.Popen([sys.executable, "-m", "research_automation", "--root", str(service.root), "worker"], cwd=service.root, env=coordinator_env, stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, start_new_session=os.name != "nt")
    _background_processes.append(process)
    for _ in range(50):
        owner = service.store.maybe("runtime", "worker")
        if owner and owner.get("status") == "RUNNING":
            try:
                actual = psutil.Process(owner["pid"])
                belongs = actual.pid == process.pid or any(parent.pid == process.pid for parent in actual.parents())
                if belongs and abs(actual.create_time() - owner["created"]) < 0.01:
                    # Windows venv redirectors launch a second Python process.
                    return {"status": "started", "pid": actual.pid}
            except psutil.Error:
                pass
        if process.poll() is not None:
            raise ResearchError("Worker failed to start; inspect state/worker.stderr.log")
        time.sleep(0.1)
    raise ResearchError("Worker did not confirm startup; inspect status before trying again")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = parser().parse_args(argv)
    service = None
    try:
        service = Service(args.root)
        result = None
        if args.command == "init":
            service.initialize()
            result = {"status": "initialized", "root": str(service.root), "limits": service.config}
        elif args.command == "doctor":
            configured = secrets(service.root)
            command = codex_command()
            auth = subprocess.run(command + ["login", "status"], capture_output=True, text=True, timeout=20, env=child_environment())
            result = {"python": sys.version.split()[0], "codex_installed": True, "codex_logged_in": auth.returncode == 0, "discord_configured": bool(configured["DISCORD_WEBHOOK_URL"]), "openalex_key_configured": bool(configured["OPENALEX_API_KEY"]), "root": str(service.root), "limits": service.config}
        elif args.command == "submit":
            topic = service.submit(args.idea, args.discover, search_queries=args.query)
            result = {"topic": topic["id"], "status": topic["status"], "next": "Worker performs review and pauses for topic selection."}
        elif args.command == "approve":
            campaign = service.approve(args.topic, args.revision, args.instruction, json.loads(args.limits) if args.limits else None, campaign_id=args.campaign)
            result = {"campaign": campaign["id"], "status": campaign["status"], "next": "Elapsed-time extension recorded; frozen work is preserved." if args.campaign else "Planning and experiments proceed automatically."}
        elif args.command in {"reject", "defer", "revise", "cancel"}:
            topic = service.decide(args.topic, args.command, args.instruction)
            result = {"topic": topic["id"], "status": topic["status"]}
        elif args.command == "resume":
            service.resume(args.job)
            result = {"job": args.job, "status": "queued"}
        elif args.command == "worker":
            service.worker(once=args.once, drain=args.drain)
        elif args.command == "start":
            result = start_worker(service)
        elif args.command == "stop":
            service.stop_worker()
            result = {"status": "stop_requested"}
        elif args.command == "status":
            result = service.store.status()
        elif args.command == "events":
            result = [dict(r) | {"data": json.loads(r["data"])} for r in service.store.db.execute("SELECT * FROM events ORDER BY seq DESC LIMIT ?", (max(1, min(args.limit, 1000)),))]
        elif args.command == "notifications":
            if args.allow_actions is not None:
                service.store.set_notification_actions(args.allow_actions)
            notifier = Notifier(service.store)
            if args.replay:
                notifier.replay()
            delivered = notifier.flush() if args.flush or args.replay else 0
            result = {"newly_delivered": delivered, "messages": [dict(r) for r in service.store.db.execute("SELECT id,status,attempts,message_id,error FROM outbox ORDER BY seq,part")]}
        elif args.command == "configure-secret":
            value = sys.stdin.read().strip() if args.stdin else getpass.getpass(f"{args.key}: ")
            configure_secret(service.root, args.key, value)
            result = {"secret": args.key, "configured": bool(value), "stored_outside_repository": True}
        elif args.command == "notify":
            event = service.store.event("interface.action_completed", {"summary": args.summary})
            result = {"event": event, "delivered": Notifier(service.store).flush()}
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ResearchError, ValueError, OSError) as error:
        from .common import redact
        print(redact(str(error)), file=sys.stderr)
        return 1
    finally:
        if service:
            service.close()


if __name__ == "__main__":
    raise SystemExit(main())
