from __future__ import annotations

import csv
import io
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import jsonschema
import psutil

from . import schemas
from .analysis import analyze
from .common import BudgetExceeded, Cancelled, ResearchError, atomic_write, child_environment, digest, file_hash, markdown, new_id, now, safe_path
from .network import fetch


def source_manifest(directory, plan):
    hashes = {}
    for item in plan["files"]:
        path = safe_path(directory, item["path"])
        if not path.exists() or file_hash(path) != digest(item["content"].encode("utf-8")):
            raise ResearchError("Experiment source differs from its frozen plan")
        hashes[item["path"]] = file_hash(path)
    for item in plan["inputs"]:
        path = safe_path(directory, item["path"])
        if not path.exists() or file_hash(path) != item["sha256"]:
            raise ResearchError("Experiment input differs from its frozen plan")
        hashes[item["path"]] = file_hash(path)
    return hashes


def active_supervisor(request_path):
    target = str(Path(request_path).resolve()).casefold()
    for process in psutil.process_iter(["pid", "cmdline", "create_time"]):
        try:
            args = process.info["cmdline"] or []
            if "research_automation.process_runner" in args and any(a.casefold() == target for a in args):
                return process
        except (psutil.Error, OSError):
            continue
    return None


def validate_metrics(metrics, plan, seed, condition):
    jsonschema.validate(metrics, schemas.METRICS)
    if metrics["seed"] != seed or metrics["condition"] != condition or metrics["metric"] != plan["primary_metric"] or metrics["unit"] != plan["metric_unit"]:
        raise ResearchError("Run output does not match its planned unit or metric")
    from .common import finite_number
    if not all(finite_number(metrics[x]) for x in ("candidate", "baseline", "ablation")):
        raise ResearchError("Run produced nonfinite measurements")
    if set(metrics["evaluations"].values()) != {plan["evaluation_budget"]}:
        raise ResearchError("Actual declared evaluation counts must equal the frozen fair budget")
    import re
    if not re.fullmatch(r"[a-f0-9]{64}", metrics["input_sha256"]):
        raise ResearchError("Run lacks a valid input fingerprint")


def execute_run(ctx, plan, directory, stage, seed=0, condition="", repeat=0):
    ctx.guard()
    ctx.service.validate_frozen_plan(plan)
    sources = source_manifest(directory, plan)
    logical_key = digest([plan["campaign_id"], plan["id"], plan["plan_hash"], stage, seed, condition, repeat])
    previous = ctx.store.maybe("run", logical_key)
    if previous and previous["status"] == "COMPLETED":
        path = safe_path(ctx.root, previous["manifest_path"])
        if not path.exists() or file_hash(path) != previous["manifest_hash"]:
            raise ResearchError("Stored run manifest was changed or lost")
        if stage != "correctness":
            metrics_path = safe_path(ctx.root, previous["metrics_path"])
            if not metrics_path.exists() or file_hash(metrics_path) != previous["metrics_hash"]:
                raise ResearchError("Stored raw measurements were changed or lost")
            measurements = json.loads(metrics_path.read_text(encoding="utf-8"))
            validate_metrics(measurements, plan, seed, condition)
        else:
            measurements = None
        ctx.emit("experiment.run_reused", run=previous["id"], stage=stage)
        return previous, measurements
    if previous and previous["status"] == "RUNNING":
        request_path = safe_path(ctx.root, previous["request_path"])
        process_path = request_path.parent / "process.json"
        finished = json.loads(process_path.read_text(encoding="utf-8")) if process_path.exists() else None
        if finished and finished["status"] == "COMPLETED":
            measurements = None
            if stage != "correctness":
                metrics_path = safe_path(ctx.root, previous["metrics_path"])
                try:
                    measurements = json.loads(metrics_path.read_text(encoding="utf-8"))
                    validate_metrics(measurements, plan, seed, condition)
                except (OSError, ValueError, jsonschema.ValidationError, ResearchError):
                    previous["status"] = "INVALID"
                    ctx.store.put("run", logical_key, previous, "experiment.run_invalid", "Recovery found invalid completed measurements")
                    raise ResearchError("Recovered completed run has invalid raw measurements") from None
                previous["metrics_hash"] = file_hash(metrics_path)
            request = json.loads(request_path.read_text(encoding="utf-8"))
            manifest_path = safe_path(ctx.root, previous["manifest_path"])
            previous.update({"status": "COMPLETED", "process": finished})
            if manifest_path.exists():
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
                if existing.get("plan_hash") != plan["plan_hash"] or existing.get("source_hashes") != sources:
                    raise ResearchError("Recovered manifest has mismatched plan or source provenance")
            else:
                manifest = {**previous, "topic_id": plan["topic_id"], "topic_revision": plan["topic_revision"], "approval_id": plan["approval_id"], "plan_hash": plan["plan_hash"], "source_hashes": sources, "command": request["command"], "working_directory": directory.relative_to(ctx.root).as_posix(), "machine": {"platform": platform.platform(), "python": sys.version, "cpu_count": os.cpu_count()}, "environment_lock_hash": file_hash(directory / "environment.json"), "environment": request["environment"]}
                ctx.write_json(previous["manifest_path"], manifest)
            previous["manifest_hash"] = file_hash(manifest_path)
            ctx.store.put("run", logical_key, previous, "experiment.run_recovered_completed", "Adopted persisted completion; no new experiment dispatched")
            return previous, measurements
        supervisor = active_supervisor(request_path)
        if supervisor:
            atomic_write(request_path.parent / "cancel", "worker recovery")
            try:
                supervisor.wait(timeout=15)
            except psutil.TimeoutExpired:
                raise ResearchError("Prior run is still owned by a live supervisor; duplicate dispatch blocked") from None
        previous["status"] = "INTERRUPTED"
        ctx.store.put("run", logical_key, previous, "experiment.run_interrupted", "Preserved prior attempt after worker recovery")
    if previous and previous["status"] not in {"INTERRUPTED"}:
        raise ResearchError("A failed scientific execution is not silently retried; revise or inspect the hypothesis")
    attempt = previous.get("attempt", 0) + 1 if previous else 1
    if attempt > 2:
        raise ResearchError("Infrastructure recovery retry cap reached")
    ctx.reserve("runs", "max_runs")
    run_id = new_id("run")
    run_directory = directory / "runs" / run_id
    run_directory.mkdir(parents=True, exist_ok=True)
    metrics_path = run_directory / "metrics.json"
    command = [sys.executable, str(directory / "tests/check.py")] if stage == "correctness" else [sys.executable, str(directory / "src/experiment.py"), "--seed", str(seed), "--condition", condition, "--budget", str(plan["evaluation_budget"]), "--output", str(metrics_path)]
    environment = child_environment()
    environment["PYTHONPATH"] = str(directory / "src") + os.pathsep + str(Path(__file__).resolve().parents[1])
    # Persist only a normal OS allowlist, not arbitrary inherited environment values.
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOME", "LOCALAPPDATA", "APPDATA", "PYTHONPATH", "PYTHONIOENCODING", "PYTHONUTF8", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"}
    environment = {k: v for k, v in environment.items() if k.upper() in allowed}
    request_path = run_directory / "request.json"
    request = {"run_id": run_id, "command": command, "cwd": str(directory), "environment": environment, "worker_pid": os.getpid(), "worker_created": psutil.Process().create_time(), "timeout": ctx.config["max_run_seconds"], "memory_mb": ctx.config["memory_mb"], "max_output_mb": ctx.config["max_output_mb"]}
    atomic_write(request_path, json.dumps(request))
    relative = lambda p: p.relative_to(ctx.root).as_posix()
    record = {"id": run_id, "logical_key": logical_key, "hypothesis_id": plan["id"], "campaign_id": plan["campaign_id"], "stage": stage, "seed": seed, "condition": condition, "attempt": attempt, "status": "RUNNING", "request_path": relative(request_path), "manifest_path": relative(run_directory / "manifest.json"), "metrics_path": relative(metrics_path)}
    ctx.store.put("run", logical_key, record, "experiment.run_started", f"{run_id}: {stage}, condition={condition}, seed={seed}, attempt={attempt}")
    supervisor = subprocess.Popen([sys.executable, "-m", "research_automation.process_runner", str(request_path)], env=child_environment(), cwd=ctx.root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        while supervisor.poll() is None:
            ctx.heartbeat()
            time.sleep(0.1)
    except BaseException:
        atomic_write(run_directory / "cancel", "coordinator cancellation or budget stop")
        try:
            supervisor.wait(timeout=15)
        except subprocess.TimeoutExpired:
            from .agent import terminate_tree
            terminate_tree(supervisor)
        record["status"] = "INTERRUPTED"
        ctx.store.put("run", logical_key, record, "experiment.run_interrupted", "Cancellation, interruption, or resource stop")
        raise
    process_path = run_directory / "process.json"
    if not process_path.exists():
        record["status"] = "FAILED"
        ctx.store.put("run", logical_key, record, "experiment.run_failed", "Supervisor did not produce a completion record")
        raise ResearchError("Subprocess supervisor failed to record its outcome")
    process = json.loads(process_path.read_text(encoding="utf-8"))
    record.update({"status": process["status"], "process": process})
    manifest = {**record, "topic_id": plan["topic_id"], "topic_revision": plan["topic_revision"], "approval_id": plan["approval_id"], "plan_hash": plan["plan_hash"], "source_hashes": sources, "command": command, "working_directory": relative(directory), "machine": {"platform": platform.platform(), "python": sys.version, "cpu_count": os.cpu_count()}, "environment_lock_hash": file_hash(directory / "environment.json"), "environment": environment}
    ctx.write_json(record["manifest_path"], manifest)
    record["manifest_hash"] = file_hash(run_directory / "manifest.json")
    if process["status"] != "COMPLETED":
        ctx.store.put("run", logical_key, record, "experiment.run_failed", f"{run_id}: {process.get('reason', process.get('exit_code'))}")
        raise ResearchError(f"Run {run_id} failed: {process.get('reason', process.get('exit_code'))}")
    source_manifest(directory, plan)
    if stage != "correctness":
        try:
            measurements = json.loads(metrics_path.read_text(encoding="utf-8"))
            validate_metrics(measurements, plan, seed, condition)
        except (OSError, ValueError, jsonschema.ValidationError, ResearchError):
            record["status"] = "INVALID"
            ctx.store.put("run", logical_key, record, "experiment.run_invalid", "Raw metric schema, identity, or fair-budget validation failed")
            raise ResearchError(f"Run {run_id} produced invalid scientific measurements") from None
        record["metrics_hash"] = file_hash(metrics_path)
        ctx.store.artifact(record["metrics_path"], record["metrics_hash"], ctx.job["id"])
    else:
        measurements = None
    ctx.store.put("run", logical_key, record, "experiment.run_completed", f"{run_id}: {stage}; elapsed={process['elapsed_seconds']:.3f}s; peak_memory={process['peak_memory_bytes']}")
    ctx.checkpoint()
    return record, measurements


def prepare(ctx, plan):
    ctx.service.validate_frozen_plan(plan)
    relative = f"experiments/{plan['topic_id']}-{plan['id']}/{plan['campaign_id']}"
    directory = safe_path(ctx.root, relative)
    directory.mkdir(parents=True, exist_ok=True)
    ctx.write_json(relative + "/frozen-plan.json", plan)
    for item in plan["files"]:
        path = safe_path(directory, item["path"])
        expected = digest(item["content"].encode("utf-8"))
        if path.exists() and file_hash(path) != expected:
            raise ResearchError("Existing implementation was modified; refusing to overwrite frozen source")
        ctx.write(relative + "/" + item["path"], item["content"])
        ctx.emit("implementation.file_ready", hypothesis=plan["id"], path=relative + "/" + item["path"], sha256=expected)
    for item in plan["inputs"]:
        path = safe_path(directory, item["path"])
        if not path.exists():
            data = fetch(item["url"])
            if digest(data) != item["sha256"]:
                raise ResearchError("External input checksum failed")
            ctx.write(relative + "/" + item["path"], data)
    import importlib.metadata
    environment = {"python": sys.version, "executable": sys.executable, "platform": platform.platform(), "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions() if d.metadata["Name"]}}
    if not (directory / "environment.json").exists():
        ctx.write_json(relative + "/environment.json", environment)
    elif json.loads((directory / "environment.json").read_text(encoding="utf-8")) != environment:
        raise ResearchError("Experiment environment changed since its frozen preparation")
    ctx.write(relative + "/README.md", f"# {plan['title']}\n\nCampaign {plan['campaign_id']}; frozen plan {plan['plan_hash']}.\n\nRun correctness: `{sys.executable} tests/check.py`\n\nExample confirmation: `{sys.executable} src/experiment.py --seed {plan['seeds'][0]} --condition {plan['conditions'][0]} --budget {plan['evaluation_budget']} --output metrics.json`\n\nRun from this directory. Environment and source fingerprints are preserved; all attempts are in runs/.\n")
    return directory


def experiment_hypothesis(ctx, plan, hypothesis_count):
    directory = prepare(ctx, plan)
    run_records = []
    correctness, _ = execute_run(ctx, plan, directory, "correctness")
    run_records.append(correctness)
    for i in range(3):
        record, _ = execute_run(ctx, plan, directory, "smoke", i, plan["conditions"][0])
        run_records.append(record)
    confirmations, reproductions = [], []
    for stage in ("confirmation", "reproduction"):
        for condition in plan["conditions"]:
            for seed in plan["seeds"] if stage == "confirmation" else plan["seeds"][:3]:
                record, measurements = execute_run(ctx, plan, directory, stage, seed, condition)
                run_records.append(record)
                target = confirmations if stage == "confirmation" else reproductions
                target.append(measurements)
    result = analyze(plan, confirmations, reproductions, hypothesis_count)
    relative = directory.relative_to(ctx.root).as_posix()
    analysis_input = {"plan": plan, "confirmation": confirmations, "reproduction": reproductions, "hypothesis_count": hypothesis_count}
    ctx.write_json(relative + "/analysis/input.json", analysis_input)
    ctx.write_json(relative + "/analysis/statistics.json", result)
    ctx.write(relative + "/analysis/recompute.py", "import json\nfrom pathlib import Path\nfrom research_automation.analysis import analyze\np = Path(__file__).with_name('input.json')\nd = json.loads(p.read_text(encoding='utf-8'))\nprint(json.dumps(analyze(d['plan'],d['confirmation'],d['reproduction'],d['hypothesis_count']), sort_keys=True, indent=2))\n")
    allowed_artifacts = [r["manifest_path"] for r in run_records] + [r["metrics_path"] for r in run_records if r["stage"] != "correctness"] + [relative + "/" + x["path"] for x in plan["files"]] + [relative + "/analysis/statistics.json"]
    audit = ctx.ask("Audit scientific validity conservatively using the frozen plan, actual source, correctness logs, raw measurements and analysis. Each check must cite one exact artifact from allowed_artifacts and explain concrete evidence. Check actual independent units, fairness, no hard-coded advantage/fabricated measurement, code/test correctness, meaningful baseline reproduction, leakage, isolated mechanism/ablation, guardrails, and reproducibility. A successful subprocess or generated assertion alone is not proof. Any unsupported check must be passed=false. Do not use tools or alter the experiment.", {"plan": plan, "runs": run_records, "correctness_stdout": safe_path(ctx.root, correctness["request_path"]).parent.joinpath("stdout.log").read_text(encoding="utf-8", errors="replace")[-20000:], "raw_confirmation": confirmations, "raw_reproduction": reproductions, "statistics": result, "allowed_artifacts": allowed_artifacts}, schemas.AUDIT)
    for key, check in audit.items():
        if key == "limitations":
            continue
        if check["artifact"] not in allowed_artifacts or len(check["explanation"].strip()) < 20:
            raise ResearchError("Scientific audit lacks traceable evidence")
    audit_pass = all(v["passed"] for k, v in audit.items() if k != "limitations")
    if not audit_pass:
        result["outcome"] = "INVALID" if not audit["correctness"]["passed"] or not audit["fair_budget"]["passed"] or not audit["no_leakage"]["passed"] else "INCONCLUSIVE"
    # Independent deterministic reanalysis must exactly recreate the persisted statistics.
    recomputed = analyze(plan, confirmations, reproductions, hypothesis_count)
    if {k: v for k, v in recomputed.items() if k != "outcome"} != {k: v for k, v in result.items() if k != "outcome"}:
        raise ResearchError("Raw-data reanalysis did not reproduce the statistics")
    result.update({"audit": audit, "audit_pass": audit_pass, "hypothesis_id": plan["id"], "plan_hash": plan["plan_hash"], "run_ids": [r["id"] for r in run_records], "work_directory": relative, "confirmation_count": len(confirmations), "reproduction_count": len(reproductions)})
    ctx.write_json(relative + "/analysis/audit.json", audit)
    ctx.write_json(relative + "/analysis/result.json", result)
    ctx.emit("hypothesis.verified", hypothesis=plan["id"], outcome=result["outcome"], statistics=result["conditions"], audit_pass=audit_pass, limitations=audit["limitations"], artifact=relative + "/analysis/result.json")
    return result


def execute_campaign(ctx):
    campaign = ctx.store.get("campaign", ctx.job["entity"])
    outcomes = campaign.setdefault("outcomes", {})
    stopped = False
    for identifier in campaign["hypothesis_ids"]:
        if identifier in outcomes:
            continue
        plan = ctx.store.get("hypothesis", identifier)
        try:
            ctx.guard()
            result = experiment_hypothesis(ctx, plan, len(campaign["hypothesis_ids"]))
        except (Cancelled, BudgetExceeded) as error:
            result = {"hypothesis_id": identifier, "outcome": "CANCELLED" if isinstance(error, Cancelled) else "BLOCKED", "reason": str(error)}
            stopped = True
        except ResearchError as error:
            result = {"hypothesis_id": identifier, "outcome": "INVALID", "reason": str(error)}
        outcomes[identifier] = result
        # Reload durable counters updated by individual action reservations.
        latest = ctx.store.get("campaign", campaign["id"])
        campaign.update({"usage": latest.get("usage", {}), "elapsed_seconds": latest.get("elapsed_seconds", 0)})
        campaign["outcomes"] = outcomes
        ctx.store.put("campaign", campaign["id"], campaign, "hypothesis.outcome_saved", f"{identifier}: {result['outcome']}")
        plan["status"] = "VERIFIED" if "audit" in result else "STOPPED"
        plan["outcome"] = result["outcome"]
        ctx.store.put("hypothesis", identifier, plan)
        if stopped:
            break
    for identifier in campaign["hypothesis_ids"]:
        outcomes.setdefault(identifier, {"hypothesis_id": identifier, "outcome": "CANCELLED" if ctx.cancelled() else "BLOCKED", "reason": "Campaign stopped before this hypothesis could be evaluated"})
    campaign["status"] = "CANCELLED" if ctx.cancelled() else "PARTIAL" if stopped else "COMPLETED"
    campaign["outcomes"] = outcomes
    ctx.store.put("campaign", campaign["id"], campaign)
    write_report(ctx, campaign)


def write_report(ctx, campaign):
    topic = campaign.get("topic_snapshot") or ctx.store.get("topic", campaign["topic_id"])
    outcomes = campaign.get("outcomes", {})
    counts = {name: sum(r["outcome"] == name for r in outcomes.values()) for name in ("SUPPORTED", "NOT_SUPPORTED", "INCONCLUSIVE", "INVALID", "BLOCKED", "CANCELLED")}
    base = f"results/{topic['id']}-{campaign['id']}"
    runs = [r for r in ctx.store.list("attempt") if r["campaign_id"] == campaign["id"]]
    evidence_links = "\n".join(f"- {r['id']} / {r['stage']} / {r['status']}: [manifest](../{r['manifest_path']})" if safe_path(ctx.root, r["manifest_path"]).exists() else f"- {r['id']} / {r['stage']} / {r['status']}: [request](../{r['request_path']}); manifest incomplete" for r in runs)
    per_hypothesis = []
    table = io.StringIO()
    writer = csv.writer(table)
    writer.writerow(["hypothesis", "outcome", "condition", "mean_improvement", "lower", "upper", "n"])
    for identifier in campaign.get("hypothesis_ids", []):
        plan = ctx.store.get("hypothesis", identifier)
        result = outcomes.get(identifier, {"outcome": "BLOCKED", "reason": "Not evaluated"})
        text = f"### {identifier}: {result['outcome']}\n\n[Plan](../{plan['plan_path']})\n\n{json.dumps(result, ensure_ascii=False, indent=2)}"
        per_hypothesis.append(text)
        for condition, values in result.get("conditions", {}).items():
            estimate = values["baseline_improvement"]
            writer.writerow([identifier, result["outcome"], condition, estimate["mean"], estimate["lower"], estimate["upper"], estimate["n"]])
    elapsed = sum(r.get("process", {}).get("elapsed_seconds", 0) for r in runs)
    summary = {"campaign_id": campaign["id"], "topic_id": topic["id"], "topic_revision": campaign["topic_revision"], "approval_id": campaign["approval_id"], "status": campaign["status"], "counts": counts, "outcomes": outcomes, "run_count": len(runs), "subprocess_seconds": elapsed, "limits": campaign["limits"], "usage": campaign.get("usage", {}), "report_path": base + ".md"}
    ctx.write_json(base + "/summary.json", summary)
    ctx.write(base + "/tables/effects.csv", table.getvalue())
    sections = [
        ("Executive result", f"Campaign: {campaign['status']}. Outcomes: {json.dumps(counts)}.\n\nSupported findings apply only to the frozen question, methods, and tested conditions. Unevaluated or invalid runs are not scientific disproof."),
        ("Question and literature context", topic["question"] + f"\n\n[Selected topic](../{campaign.get('topic_snapshot_path', 'topic/' + topic['id'] + '.md')}); [selected literature survey](../{campaign.get('survey_snapshot_path', 'topic/' + topic['id'] + '-survey.md')}). Selected revision: {campaign['topic_revision']}; approval: {campaign['approval_id']}."),
        ("Methods and frozen plans", "Paired independent runs; fair frozen evaluation budgets; distinct confirmation seeds and smoke runs; baseline and ablation comparisons with Bonferroni-adjusted bootstrap intervals; fresh-process repetition of three seeds per condition; code/raw-data scientific audit.\n\nEvery run records source, data, environment, and resource fingerprints. No post-hoc threshold changes are permitted."),
        ("Per-hypothesis results and detailed verification", "\n\n".join(per_hypothesis) or campaign.get("error", "No workable hypotheses were generated.")),
        ("Negative and incomplete results", f"Every planned hypothesis is listed. Counts: {json.dumps(counts)}.\n\nNOT_SUPPORTED means planned valid evidence did not meet the required effect. INCONCLUSIVE, INVALID, BLOCKED and CANCELLED remain distinct. Failed/invalid attempts are retained."),
        ("Raw evidence and reproduction", evidence_links + "\n\nEach work directory includes environment.json, frozen-plan.json, README.md, source, correctness tests, raw run logs/metrics, and analysis/recompute.py. Run that script with the same environment to reproduce statistics. [Machine-readable summary](" + base.rsplit("/", 1)[-1] + "/summary.json); [effect table](" + base.rsplit("/", 1)[-1] + "/tables/effects.csv)."),
        ("Resources and limitations", f"Subprocess attempts: {len(runs)}; recorded subprocess elapsed seconds: {elapsed:.3f}. Usage: {json.dumps(campaign.get('usage', {}))}. Approved limits: {json.dumps(campaign['limits'])}.\n\nLiterature coverage: {topic.get('assessment', {}).get('coverage_limits', 'Review incomplete')}. Research findings still require interpretation within these limits."),
        ("Discord delivery", "Final event IDs and delivery confirmation are recorded in the durable event/outbox tables. Use research notifications to inspect pending, failed, and confirmed messages; delivery is separate from scientific completion."),
    ]
    ctx.write(base + ".md", markdown({"topic_id": topic["id"], "campaign_id": campaign["id"], "approval_id": campaign["approval_id"], "status": campaign["status"]}, "Research result: " + topic["question"], sections))
    campaign["report_path"] = base + ".md"
    ctx.store.put("campaign", campaign["id"], campaign)
    current_topic = ctx.store.get("topic", campaign["topic_id"])
    if current_topic.get("campaign_id") == campaign["id"] and current_topic.get("latest_decision") == campaign["approval_id"]:
        current_topic["status"] = campaign["status"]
        try:
            ctx.service.save_topic(current_topic)
        except ResearchError:
            # A changed evidence file must not prevent a truthful blocked report,
            # and must never be adopted as newly verified evidence.
            ctx.store.put("topic", current_topic["id"], current_topic)
    ctx.emit("campaign.result", campaign=campaign["id"], question=topic["question"], status=campaign["status"], outcomes=counts, result=base + ".md", findings={k: v.get("conditions", v.get("reason", "")) for k, v in outcomes.items()}, limitations=topic.get("assessment", {}).get("coverage_limits", "Review incomplete"))
