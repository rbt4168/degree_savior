"""Synthetic application fixtures, never scientific research findings."""
import io
import json
from textwrap import dedent

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from research_automation import schemas
from research_automation.literature import paper_id


PAPER_TEXT = (
    "Synthetic optimization baseline validation fixture. "
    "Gradient descent reduces squared error on convex quadratic functions. "
    "Random search supplies a reference baseline with a fixed evaluation budget. "
    "The synthetic fixture exists only to test application workflow plumbing. "
    "These statements are fabricated test metadata and are not research evidence."
)


def pdf_bytes():
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    content = DecodedStreamObject()
    content.set_data(('BT /F1 10 Tf 20 700 Td (' + PAPER_TEXT + ') Tj ET').encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(content)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


class Sources:
    def __init__(self):
        self.record = {"title": "Synthetic optimization baseline validation fixture", "authors": ["Synthetic fixture"], "year": 2026, "doi": "10.0000/synthetic-test-only", "preprint_id": "", "source_url": "https://example.org/test-only", "pdf_urls": ["https://example.org/test-only.pdf"], "references": [], "abstract": "Synthetic workflow fixture", "provider": "test"}

    def search(self, provider, query):
        return [dict(self.record)]

    def trace(self, record, direction):
        return []


def plan_fixture(negative=False):
    source = dedent('''
        import argparse, hashlib, json, math, random
        def gradient(initial, count):
            x = initial
            for _ in range(count):
                x -= 0.2 * x
            return x*x
        def random_search(seed, count):
            rng = random.Random(seed)
            return min(rng.uniform(-10,10)**2 for _ in range(count))
        def measurements(seed, condition, count):
            initial = random.Random(seed).uniform(3,7) * (2 if condition=='far' else 1)
            inputs = {'seed':seed,'initial':initial,'condition':condition}
            value = gradient(initial,count)
            reference = random_search(seed,count)
            if NEGATIVE:
                value, reference = reference, value
            return {'metric':'squared_error','unit':'squared-units','seed':seed,'condition':condition,
                    'candidate':value,'baseline':reference,'ablation':initial*initial,
                    'evaluations':{'candidate':count,'baseline':count,'ablation':count},
                    'input_sha256':hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()}
        if __name__=='__main__':
            p=argparse.ArgumentParser()
            p.add_argument('--seed',type=int,required=True)
            p.add_argument('--condition',required=True)
            p.add_argument('--budget',type=int,required=True)
            p.add_argument('--output',required=True)
            a=p.parse_args()
            with open(a.output,'w',encoding='utf-8') as f:
                json.dump(measurements(a.seed,a.condition,a.budget),f)
    ''').replace('NEGATIVE', repr(negative))
    check = dedent('''
        import math
        from experiment import gradient, random_search, measurements
        assert gradient(0,20)==0
        assert math.isclose(gradient(2,1),2.56,abs_tol=1e-12)
        assert gradient(2,20)<4
        assert random_search(42,20)==random_search(42,20)
        assert measurements(42,'near',20)['input_sha256']==measurements(42,'near',20)['input_sha256']
        print('Synthetic application fixture: known numerical cases and seeded inputs checked.')
    ''')
    return {
        "title": "Synthetic application fixture: quadratic comparison",
        "prediction": "Synthetic test prediction: planned candidate improves squared error on generated instances.",
        "null": "Synthetic test null: candidate does not produce the required error improvement.",
        "rationale": "Synthetic fixture evidence exercises provenance and pipeline accounting only.",
        "evidence": [{"paper_id": paper_id(Sources().record), "claim_id": "c1"}],
        "primary_metric": "squared_error", "metric_unit": "squared-units", "direction": "min",
        "practical_threshold": 0.0, "ablation_threshold": 0.0, "alpha": 0.05,
        "repetitions": 5, "conditions": ["near", "far"], "evaluation_budget": 100,
        "reproduction_tolerance": 0.0, "sample_size_rationale": "Five seeded independent units are used only for a synthetic integration fixture.",
        "experimental_unit": "One independently seeded synthetic quadratic instance per run.",
        "input_description": "Seeded synthetic initialization shared by candidate, reference and ablation.",
        "baseline_reproduction": "Known quadratic updates and seeded reference calculations checked numerically.",
        "guardrails": "Synthetic fixture requires finite measurements and matching evaluation counts.",
        "implementation_notes": "Pure Python synthetic algorithms; this is application validation, not research.",
        "files": [{"path": "src/experiment.py", "content": source}, {"path": "tests/check.py", "content": check}], "inputs": [],
    }


class Agent:
    def __init__(self, covered=False, negative=False, audit_pass=True):
        self.covered, self.negative, self.audit_pass = covered, negative, audit_pass
        self.calls = 0

    def cached(self, task, context, schema):
        return None

    def ask(self, task, context, schema, **kwargs):
        self.calls += 1
        if schema == schemas.SEARCH:
            return {"question": context['idea'], "motivation": "Synthetic fixture", "queries": ["synthetic baseline", "quadratic reference"]}
        if schema == schemas.SCREEN:
            return {"papers": [{"paper_id": p['id'], "relevance": "closest", "reason": "Synthetic nearest-work fixture"} for p in context['papers']]}
        if schema == schemas.STUDY:
            return {"identity_verified": True, "research_question": "Synthetic numerical fixture", "contribution": "Synthetic verification", "method": "Known quadratic updates", "assumptions": "Synthetic inputs", "evaluation": "Known test cases", "findings": "Synthetic fixture only", "author_limitations": "No actual research evidence", "interpretation": "Application validation only", "relevance": "Tests provenance", "claims": [{"id":"c1","claim":"Synthetic descent claim","page":1,"quote":"Gradient descent reduces squared error on convex quadratic functions","kind":"author_claim"},{"id":"c2","claim":"Synthetic baseline claim","page":1,"quote":"Random search supplies a reference baseline with a fixed evaluation budget","kind":"author_claim"}], "reference_dois": [], "code_url": ""}
        if schema == schemas.ASSESS:
            return {"decision":"COVERED" if self.covered else "CANDIDATE","question":context['question'],"motivation":"Synthetic fixture","proposed_gap":"Synthetic gap for pipeline validation only","closest_papers":[paper_id(Sources().record)],"evidence":[{"paper_id":paper_id(Sources().record),"claim_id":"c1","interpretation":"Synthetic provenance fixture"}],"synthesis":"A synthetic test survey, not a scientific literature review.","feasibility":"Local bounded synthetic execution","coverage_limits":"Fabricated integration fixtures only; no real research claim.","critical_missing_ids":[],"improvement_question":"Synthetic deeper question" if self.covered else ""}
        from research_automation.hypothesis import generation_schema
        if schema == schemas.PLANS or schema == generation_schema():
            return {"hypotheses":[plan_fixture(self.negative)]}
        if schema == schemas.AUDIT:
            check = {"passed":self.audit_pass,"artifact":context['allowed_artifacts'][0],"explanation":"Synthetic application audit fixture; scientific validity is not asserted."}
            return {key: dict(check) for key in ("correctness","baseline_reproduced","fair_budget","no_leakage","mechanism_isolated","reproducible")} | {"limitations":"Synthetic fixture audit; not a research finding."}
        raise AssertionError('Unexpected synthetic agent task')
