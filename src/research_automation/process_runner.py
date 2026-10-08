"""Owned subprocess supervisor. It never receives notification credentials."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

from .agent import terminate_tree
from .common import atomic_write, now, tree_size, redact


def run(request_path):
    request_path = Path(request_path).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    directory = request_path.parent
    result_path = directory / "process.json"
    result = {"status": "RUNNING", "supervisor_pid": os.getpid(), "supervisor_created": psutil.Process().create_time(), "started_at": now(), "run_id": request["run_id"]}
    atomic_write(result_path, json.dumps(result))
    started = time.monotonic()
    process = None
    peak_memory = 0
    try:
        with (directory / "stdout.log").open("wb") as stdout, (directory / "stderr.log").open("wb") as stderr:
            process = subprocess.Popen(request["command"], cwd=request["cwd"], env=request["environment"], stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            result.update({"child_pid": process.pid, "child_created": psutil.Process(process.pid).create_time()})
            atomic_write(result_path, json.dumps(result))
            while process.poll() is None:
                try:
                    worker = psutil.Process(request["worker_pid"])
                    owner_alive = worker.is_running() and abs(worker.create_time() - request["worker_created"]) < 0.01
                except psutil.Error:
                    owner_alive = False
                reason = None
                if not owner_alive:
                    reason = "owner_interrupted"
                elif (directory / "cancel").exists():
                    reason = "cancelled"
                elif time.monotonic() - started > request["timeout"]:
                    reason = "timeout"
                try:
                    parent = psutil.Process(process.pid)
                    memory = sum(p.memory_info().rss for p in [parent, *parent.children(recursive=True)] if p.is_running())
                    peak_memory = max(peak_memory, memory)
                    if memory > request["memory_mb"] * 1024 * 1024:
                        reason = "memory_limit"
                except psutil.Error:
                    pass
                if tree_size(directory) > request["max_output_mb"] * 1024 * 1024:
                    reason = "output_limit"
                if reason:
                    terminate_tree(process)
                    result.update({"status": "INTERRUPTED", "reason": reason})
                    break
                time.sleep(0.1)
            if result["status"] == "RUNNING":
                result["status"] = "COMPLETED" if process.returncode == 0 else "FAILED"
            result["exit_code"] = process.wait(timeout=10)
    except Exception as error:
        if process:
            terminate_tree(process)
        result.update({"status": "FAILED", "reason": type(error).__name__, "error_detail": redact(str(error))})
    finally:
        result.update({"finished_at": now(), "elapsed_seconds": time.monotonic() - started, "peak_memory_bytes": peak_memory})
        atomic_write(result_path, json.dumps(result))


if __name__ == "__main__":
    run(sys.argv[1])
