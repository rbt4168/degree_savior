from __future__ import annotations

import math
import random
import statistics

from .common import ResearchError, finite_number


def bootstrap_interval(values, alpha, *, draws=5000, seed=911):
    if len(values) < 5 or not all(finite_number(v) for v in values):
        raise ResearchError("Insufficient valid independent values for confirmatory analysis")
    rng = random.Random(seed)
    means = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(draws))
    lower = max(0, min(draws - 1, int(draws * alpha / 2)))
    upper = max(0, min(draws - 1, math.ceil(draws * (1 - alpha / 2)) - 1))
    return {"mean": statistics.mean(values), "lower": means[lower], "upper": means[upper], "n": len(values)}


def analyze(plan, confirmation, reproductions, hypothesis_count):
    direction = 1 if plan["direction"] == "max" else -1
    family_alpha = plan["alpha"] / (hypothesis_count * len(plan["conditions"]) * 2)
    by_condition = {}
    all_support, all_negative, reproduction_pass = True, True, True
    metrics = {(x["condition"], x["seed"]): x for x in confirmation}
    for repeated in reproductions:
        original = metrics.get((repeated["condition"], repeated["seed"]))
        if not original or original["input_sha256"] != repeated["input_sha256"] or any(abs(original[k] - repeated[k]) > plan["reproduction_tolerance"] for k in ("candidate", "baseline", "ablation")):
            reproduction_pass = False
    for condition in plan["conditions"]:
        rows = [x for x in confirmation if x["condition"] == condition]
        if {x["seed"] for x in rows} != set(plan["seeds"]) or len(rows) != len(plan["seeds"]):
            raise ResearchError("Confirmation has missing, duplicate, or unplanned independent units")
        improvement = [direction * (x["candidate"] - x["baseline"]) for x in rows]
        ablation = [direction * (x["candidate"] - x["ablation"]) for x in rows]
        primary_ci = bootstrap_interval(improvement, family_alpha)
        ablation_ci = bootstrap_interval(ablation, family_alpha, seed=912)
        supported = primary_ci["lower"] > plan["practical_threshold"] and ablation_ci["lower"] > plan["ablation_threshold"]
        # Clear failure of a mandatory support condition is a negative result.
        negative = primary_ci["upper"] <= plan["practical_threshold"] or ablation_ci["upper"] <= plan["ablation_threshold"]
        all_support &= supported
        all_negative &= negative
        by_condition[condition] = {"baseline_improvement": primary_ci, "ablation_improvement": ablation_ci, "supported": supported, "clearly_below_required_effect": negative}
    expected_repeats = {(c, s) for c in plan["conditions"] for s in plan["seeds"][:3]}
    if {(x["condition"], x["seed"]) for x in reproductions} != expected_repeats or len(reproductions) != len(expected_repeats):
        reproduction_pass = False
    verdict = "SUPPORTED" if all_support and reproduction_pass else "NOT_SUPPORTED" if all_negative and reproduction_pass else "INCONCLUSIVE"
    return {"outcome": verdict, "conditions": by_condition, "reproduction_pass": reproduction_pass, "adjusted_alpha": family_alpha, "method": "paired percentile bootstrap; Bonferroni over campaign hypotheses, conditions, and two comparisons", "limitations": "Intervals describe the planned independent units. Dependence, limited sample size, or an unsuitable sampling design can invalidate a scientific claim; the evidence audit must check these."}
