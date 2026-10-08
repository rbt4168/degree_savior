import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from research_automation.agent import CodexAgent
from research_automation.common import ResearchError, digest
from research_automation.messages import build_messages
from research_automation.presentation import english_sections


class PresentationTests(unittest.TestCase):
    def test_english_embed_keeps_summary_terms_and_metric_keys(self):
        payload = build_messages('literature.report', {
            'summary': 'DiT / VAE / GP: review of the bounded gap.',
            'question': 'Can CMA-ES improve SRBench recovery?',
            'statistics': {'baseline_improvement': 0.1, 'mean': 2.3},
            'result': 'report.pdf'}, 'evt', 1, '2026-10-08')[0]
        self.assertEqual(payload['embeds'][0]['description'], 'DiT / VAE / GP: review of the bounded gap.')
        self.assertIn('baseline_improvement', json.dumps(payload))
        self.assertIn('CMA-ES', json.dumps(payload))
        self.assertTrue(json.dumps(payload, ensure_ascii=False).isascii())
        self.assertEqual(payload['_attachment'], 'report.pdf')

    def test_old_language_cache_is_ignored_and_english_cache_is_reusable(self):
        with tempfile.TemporaryDirectory() as root:
            agent = CodexAgent(root)
            task, context, schema = 'Fixture', {}, {'type': 'object'}
            old = digest({'version': 2, 'task': task, 'context': context, 'schema': schema})
            path = Path(root)/'state/agent'/old/'answer.json'
            path.parent.mkdir(parents=True)
            path.write_text('{"summary":"Legacy fixture"}', encoding='utf-8')
            self.assertIsNone(agent.cached(task, context, schema))
            new = digest({'version': 3, 'language': 'en', 'task': task, 'context': context, 'schema': schema})
            path = Path(root)/'state/agent'/new/'answer.json'
            path.parent.mkdir(parents=True)
            path.write_text('{"summary":"English fixture"}', encoding='utf-8')
            self.assertEqual(agent.cached(task, context, schema)['summary'], 'English fixture')

    def test_translation_preserves_numbers_identifiers_terms_and_quotes(self):
        agent = Mock()
        sections = [('Finding', '\u9650\u5236 DiT 512 p-abcdef; https://example.org/paper\nEvidence excerpt: exact source words')]
        agent.ask.return_value = {'sections': [{'label': 'Finding', 'text': 'Limitations DiT 512 p-abcdef; https://example.org/paper\nEvidence excerpt: exact source words'}]}
        self.assertIn('512', english_sections(agent, sections, 10)[0][1])
        agent.ask.return_value['sections'][0]['text'] = 'Limitations DiT 1024 p-abcdef; https://example.org/paper\nEvidence excerpt: exact source words'
        with self.assertRaises(ResearchError):
            english_sections(agent, sections, 10)

    def test_english_sections_need_no_translation_and_incomplete_translation_is_rejected(self):
        agent = Mock()
        sections = [('Finding', 'DiT / VAE: unverified gap.')]
        self.assertEqual(english_sections(agent, sections, 10), sections)
        agent.ask.assert_not_called()
        agent.ask.return_value = {'sections': []}
        with self.assertRaises(ResearchError):
            english_sections(agent, [('Finding', '\u5f85\u67e5\u6838')], 10)

    def test_equivalent_magnitude_units_are_allowed_but_changed_quantities_are_rejected(self):
        agent = Mock()
        sections = [('Method', '500\u842c synthetic samples; DiT dimension 512.')]
        agent.ask.return_value = {'sections': [{'label': 'Method', 'text': '5 million synthetic samples; DiT dimension 512.'}]}
        self.assertIn('5 million', english_sections(agent, sections, 10)[0][1])
        agent.ask.return_value['sections'][0]['text'] = '50 million synthetic samples; DiT dimension 512.'
        with self.assertRaises(ResearchError):
            english_sections(agent, sections, 10)

    def test_decimal_after_chinese_prose_is_checked_as_one_quantity(self):
        agent = Mock()
        sections = [('Findings', '\u70ba0.6278; \u70ba13.73%; 1000\u842c samples.')]
        agent.ask.return_value = {'sections': [{'label': 'Findings', 'text': 'Value 0.6278; rate 13.73%; 1000 ten-thousand samples.'}]}
        self.assertIn('10,000,000 samples', english_sections(agent, sections, 10)[0][1])
        agent.ask.return_value['sections'][0]['text'] = 'Value 0.06278; rate 13.73%; 10 million samples.'
        with self.assertRaises(ResearchError):
            english_sections(agent, sections, 10)

    def test_date_translation_accepts_month_names_but_rejects_a_different_month(self):
        agent = Mock()
        sections = [('Publication', '2023\u5e745\u6708; DOI 10.1007/example.')]
        agent.ask.return_value = {'sections': [{'label': 'Publication', 'text': 'May 2023; DOI 10.1007/example.'}]}
        self.assertIn('May 2023', english_sections(agent, sections, 10)[0][1])
        agent.ask.return_value['sections'][0]['text'] = 'June 2023; DOI 10.1007/example.'
        with self.assertRaises(ResearchError):
            english_sections(agent, sections, 10)
