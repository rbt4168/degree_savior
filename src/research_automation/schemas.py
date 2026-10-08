"""Strict model output contracts, also validated locally before use."""


def obj(**properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def arr(items):
    return {"type": "array", "items": items}


STRING = {"type": "string"}
INTEGER = {"type": "integer"}
NUMBER = {"type": "number"}
BOOL = {"type": "boolean"}


def enum(*values):
    return {"type": "string", "enum": list(values)}


SEARCH = obj(question=STRING, motivation=STRING, queries=arr(STRING))
SCREEN = obj(papers=arr(obj(paper_id=STRING, relevance=enum("closest", "relevant", "excluded"), reason=STRING)))
STUDY = obj(
    identity_verified=BOOL, research_question=STRING, contribution=STRING,
    method=STRING, assumptions=STRING, evaluation=STRING, findings=STRING,
    author_limitations=STRING, interpretation=STRING, relevance=STRING,
    claims=arr(obj(id=STRING, claim=STRING, page=INTEGER, quote=STRING, kind=enum("author_claim", "result", "interpretation"))),
    reference_dois=arr(STRING), code_url=STRING,
)
ASSESS = obj(
    decision=enum("CANDIDATE", "COVERED", "UNRESOLVED", "EVIDENCE_BLOCKED"),
    question=STRING, motivation=STRING, proposed_gap=STRING, closest_papers=arr(STRING),
    evidence=arr(obj(paper_id=STRING, claim_id=STRING, interpretation=STRING)),
    synthesis=STRING, feasibility=STRING, coverage_limits=STRING,
    critical_missing_ids=arr(STRING), improvement_question=STRING,
)
FILE = obj(path=STRING, content=STRING)
INPUT = obj(path=STRING, url=STRING, sha256=STRING)
HYPOTHESIS = obj(
    title=STRING, prediction=STRING, null=STRING, rationale=STRING,
    evidence=arr(obj(paper_id=STRING, claim_id=STRING)),
    primary_metric=STRING, metric_unit=STRING, direction=enum("min", "max"),
    practical_threshold=NUMBER, ablation_threshold=NUMBER,
    alpha=NUMBER, repetitions=INTEGER, conditions=arr(STRING),
    evaluation_budget=INTEGER, reproduction_tolerance=NUMBER,
    sample_size_rationale=STRING, experimental_unit=STRING,
    input_description=STRING, baseline_reproduction=STRING,
    guardrails=STRING, implementation_notes=STRING,
    files=arr(FILE), inputs=arr(INPUT),
)
HYPOTHESIS["properties"]["budget_contract"] = enum("equal_actual", "common_cap")
PLANS = obj(hypotheses=arr(HYPOTHESIS))
AUDIT_CHECK = obj(passed=BOOL, artifact=STRING, explanation=STRING)
AUDIT = obj(
    correctness=AUDIT_CHECK, baseline_reproduced=AUDIT_CHECK,
    fair_budget=AUDIT_CHECK, no_leakage=AUDIT_CHECK,
    mechanism_isolated=AUDIT_CHECK, reproducible=AUDIT_CHECK,
    limitations=STRING,
)
METRICS = obj(
    metric=STRING, unit=STRING, seed=INTEGER, condition=STRING,
    candidate=NUMBER, baseline=NUMBER, ablation=NUMBER,
    evaluations=obj(candidate=INTEGER, baseline=INTEGER, ablation=INTEGER),
    input_sha256=STRING,
)
HANDSHAKE = obj(ok=BOOL)
