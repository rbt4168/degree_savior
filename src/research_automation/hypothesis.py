from __future__ import annotations

import ast
import json
import re

from . import schemas
from .common import ResearchError, digest, finite_number, markdown, new_id, safe_path

ALLOWED_IMPORTS = {"argparse", "array", "bisect", "collections", "copy", "csv", "dataclasses", "decimal", "enum", "fractions", "functools", "hashlib", "heapq", "itertools", "json", "math", "numbers", "operator", "pathlib", "random", "re", "statistics", "sys", "time", "typing", "unittest"}


def validate_plan(plan, config, paper_claims):
    if not 5 <= plan["repetitions"] <= 30 or not 2 <= len(plan["conditions"]) <= 4:
        raise ResearchError("Plans require 5-30 independent repetitions and 2-4 conditions")
    if len(set(plan["conditions"])) != len(plan["conditions"]) or any(not re.fullmatch(r"[a-z0-9_-]{1,40}", c) for c in plan["conditions"]):
        raise ResearchError("Conditions must be distinct short filesystem-safe names")
    for field in ("practical_threshold", "ablation_threshold", "reproduction_tolerance"):
        if not finite_number(plan[field]) or plan[field] < 0:
            raise ResearchError(f"Invalid {field}")
    if not finite_number(plan["alpha"]) or not 0 < plan["alpha"] <= 0.05:
        raise ResearchError("Family-wise alpha must be positive and at most 0.05")
    if not 1 <= plan["evaluation_budget"] <= config["evaluation_budget"]:
        raise ResearchError("Evaluation budget exceeds approved envelope")
    for field in ("prediction", "null", "rationale", "sample_size_rationale", "experimental_unit", "input_description", "baseline_reproduction", "guardrails", "implementation_notes"):
        if len(plan[field].strip()) < 20:
            raise ResearchError(f"Plan field {field} is insufficiently specified")
    if not plan["evidence"]:
        raise ResearchError("Hypothesis lacks evidence provenance")
    for entry in plan["evidence"]:
        if entry["claim_id"] not in paper_claims.get(entry["paper_id"], set()):
            raise ResearchError("Hypothesis cites unknown paper evidence")
    paths = set()
    local_modules = {item["path"].rsplit("/", 1)[-1][:-3] for item in plan["files"] if item["path"].endswith(".py")}
    for item in plan["files"]:
        path = item["path"]
        safe_path(".", path)
        if path in paths or not path.startswith(("src/", "tests/", "configs/")) or not path.endswith((".py", ".json")):
            raise ResearchError("Generated implementation files must be unique Python/JSON files under src, tests, or configs")
        paths.add(path)
        if path.endswith(".py"):
            try:
                tree = ast.parse(item["content"])
            except SyntaxError:
                raise ResearchError(f"Generated Python syntax is invalid: {path}") from None
            for node in ast.walk(tree):
                imports = [a.name.split(".")[0] for a in node.names] if isinstance(node, ast.Import) else [node.module.split(".")[0]] if isinstance(node, ast.ImportFrom) and node.module else []
                if any(name not in ALLOWED_IMPORTS | local_modules for name in imports):
                    raise ResearchError("Generated code imports unsupported network/process/dependency modules")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"exec", "eval", "compile", "__import__"}:
                    raise ResearchError("Dynamic code execution is not supported in experiment proposals")
        elif path.endswith(".json"):
            try:
                json.loads(item["content"])
            except ValueError:
                raise ResearchError("Generated config is invalid JSON") from None
    if not {"src/experiment.py", "tests/check.py"}.issubset(paths):
        raise ResearchError("Plan requires src/experiment.py and executable scientific correctness tests/check.py")
    for item in plan["inputs"]:
        safe_path(".", item["path"])
        if not item["path"].startswith("data/") or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]):
            raise ResearchError("External data requires a data/ path and verified expected SHA-256")
    return 1 + 3 + len(plan["conditions"]) * (plan["repetitions"] + 3)


def plan_hypotheses(ctx):
    campaign = ctx.store.get("campaign", ctx.job["entity"])
    topic = ctx.service.require_approval(campaign["topic_id"], campaign["approval_id"])
    if campaign.get("hypothesis_ids"):
        ctx.service.ensure_execution(campaign)
        return
    papers = [ctx.store.get("paper", identifier) for identifier in topic["papers"] if ctx.store.get("paper", identifier).get("full_text_status") == "verified"]
    paper_claims = {p["id"]: {c["id"] for c in p["note"]["claims"]} for p in papers}
    task = """Create a small set of distinct, falsifiable hypotheses and complete local Python verification plans for this APPROVED topic. Stay within its scope and limits. No cloud or paid compute. Use Python's standard library for generated experiment code. Return runnable source files as strings, not shell commands. Do not claim they have run.
Each plan must have src/experiment.py accepting --seed INT --condition NAME --budget INT --output PATH. It must perform actual candidate, strongest suitable baseline, and mechanism ablation measurements on the SAME input and return exactly the supplied metrics schema. Evaluations must count actual work for all three approaches; input_sha256 hashes canonical experimental inputs, not output values. All metrics must be finite. Tests/check.py must exit nonzero on numerical/correctness/baseline reproduction failure, checking meaningful known cases or reference behavior, and exit zero only after real checks. No network access, process spawning, dynamic code execution or dependency installation inside scripts; use only verified external input URLs with known hashes when essential, otherwise generate seeded documented synthetic benchmark inputs. Never fabricate results or passing checks. Allowed imports are the computational standard library list supplied in context plus your own generated modules; use pathlib for file access.
Use distinct robustness conditions (2-4), 5-30 independent repetitions with a sample-size rationale, primary metric units/direction, absolute practical/ablation thresholds, and a reproduction tolerance. Confirmation uses paired bootstrap intervals with Bonferroni adjustment across hypotheses, conditions, and baseline/ablation comparisons. Clearly justify experimental units and whether this design is appropriate. If the question cannot be responsibly tested by this supported runner, return no hypotheses rather than an artificial test. Smoke seed is 0; confirmation uses independently generated nonzero seeds. No pilot/tuning measurements count as confirmation. Include scientific correctness, meaningful baseline reproduction, fair budgets, data separation, mechanism isolation and guardrails in the code/design."""
    context = {"topic": topic, "papers": papers, "limits": campaign["limits"], "metrics_schema": schemas.METRICS, "allowed_imports": sorted(ALLOWED_IMPORTS)}
    answer = ctx.ask(task, context, schemas.PLANS)
    if len(answer["hypotheses"]) > ctx.config["max_hypotheses"]:
        raise ResearchError("Too many hypotheses for approved campaign")
    if not answer["hypotheses"]:
        raise ResearchError("No feasible local verification plan was produced")
    for attempt in range(2):
        try:
            total_runs = sum(validate_plan(plan, campaign["limits"], paper_claims) for plan in answer["hypotheses"])
            if not answer["hypotheses"] or len(answer["hypotheses"]) > ctx.config["max_hypotheses"]:
                raise ResearchError("No feasible bounded hypothesis set")
            if total_runs > campaign["limits"]["max_runs"]:
                raise ResearchError("Combined hypotheses exceed the approved campaign run count")
            break
        except ResearchError as error:
            if attempt:
                raise
            ctx.emit("planning.validation_failed", reason=str(error))
            answer = ctx.ask(task + "\nRepair the proposals to resolve the validation failure. Keep the approved question and frozen decision design; do not fabricate evidence.", {**context, "invalid_proposals": answer, "validation_error": str(error)}, schemas.PLANS)
    if total_runs > campaign["limits"]["max_runs"]:
        raise ResearchError("Combined hypotheses exceed the approved campaign run count")
    hypothesis_ids = []
    for index, proposed in enumerate(answer["hypotheses"], 1):
        # Stable IDs make a crash/retry publish the same plans rather than duplicates.
        identifier = "h-" + digest([campaign["id"], index])[:10]
        body = dict(proposed)
        body.update({"id": identifier, "topic_id": topic["id"], "topic_revision": topic["revision"], "approval_id": campaign["approval_id"], "campaign_id": campaign["id"], "status": "PLAN_READY", "plan_revision": 1})
        body["work_directory"] = f"experiments/{topic['id']}-{identifier}/{campaign['id']}"
        body["seeds"] = [int(digest([campaign["id"], identifier, i])[:8], 16) or 1 for i in range(proposed["repetitions"])]
        body["plan_hash"] = digest({k: v for k, v in body.items() if k not in {"plan_hash", "status"}})
        plan_path = f"hypothesis/{topic['id']}-{identifier}.md"
        sections = [
            ("Evidence and rationale", proposed["rationale"] + "\n\n" + json.dumps(proposed["evidence"])),
            ("Hypothesis, null, and disproof", proposed["prediction"] + "\n\nNull: " + proposed["null"]),
            ("Implementation and baseline reproduction", proposed["implementation_notes"] + "\n\n" + proposed["baseline_reproduction"]),
            ("Data and experimental design", proposed["input_description"] + "\n\nExperimental unit: " + proposed["experimental_unit"] + "\n\n" + proposed["sample_size_rationale"]),
            ("Frozen metrics and verdict criteria", f"Primary: {proposed['primary_metric']} ({proposed['metric_unit']}, {proposed['direction']}).\n\nPractical improvement > {proposed['practical_threshold']}; ablation improvement > {proposed['ablation_threshold']}.\n\nPaired bootstrap, family-wise alpha={proposed['alpha']}, Bonferroni over hypotheses, conditions, and two comparisons. All conditions, scientific audit checks, and reproduction must pass.\n\nGuardrails: {proposed['guardrails']}"),
            ("Execution and resources", f"Local Python, budget {proposed['evaluation_budget']} per method. Conditions: {proposed['conditions']}. Confirmation seeds: {body['seeds']}.\n\nCorrectness -> 3 smoke runs -> confirmation -> 3 reproduction seeds per condition -> raw-data analysis -> scientific audit. Limits: {json.dumps(campaign['limits'])}"),
            ("Reproducibility", f"Absolute metric tolerance: {proposed['reproduction_tolerance']}. Source/inputs/environment and raw data hashed; frozen source included in adjacent JSON.\n\nExample: python src/experiment.py --seed {body['seeds'][0]} --condition {proposed['conditions'][0]} --budget {proposed['evaluation_budget']} --output metrics.json"),
            ("Deviations and revision history", "Initial frozen plan. No measurements have informed its criteria."),
        ]
        ctx.write(plan_path, markdown({k: body[k] for k in ("id", "topic_id", "topic_revision", "approval_id", "campaign_id", "plan_revision", "plan_hash")}, proposed["title"], sections))
        body["plan_path"] = plan_path
        from .common import file_hash
        body["document_hash"] = file_hash(safe_path(ctx.root, plan_path))
        ctx.write_json(f"hypothesis/{topic['id']}-{identifier}.json", body)
        body["json_path"] = f"hypothesis/{topic['id']}-{identifier}.json"
        body["json_hash"] = file_hash(safe_path(ctx.root, body["json_path"]))
        ctx.store.put("hypothesis", identifier, body, "hypothesis.plan_ready", f"{proposed['prediction']} | metric={proposed['primary_metric']} | path={plan_path}", event_key=f"plan-ready:{campaign['id']}:{identifier}")
        hypothesis_ids.append(identifier)
    latest = ctx.store.get("campaign", campaign["id"])
    campaign.update({"hypothesis_ids": hypothesis_ids, "status": "EXECUTING", "planned_runs": total_runs, "usage": latest.get("usage", {})})
    ctx.store.put("campaign", campaign["id"], campaign, "planning.completed", f"{len(hypothesis_ids)} plans; automatic experiment handoff")
    ctx.service.ensure_execution(campaign)
