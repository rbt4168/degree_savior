import tempfile
import unittest
from pathlib import Path

from research_automation.common import ResearchError
from research_automation.literature import evidence_valid
from research_automation.publications import classify
from research_automation.store import Store


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.directory.name))
        self.store.put('policy', 'literature', {
            'major_only': True, 'major_venues': ['ICML'],
            'official_hosts': ['proceedings.mlr.press']})
        self.record = {'id': 'fixture', 'title': 'Synthetic paper', 'pdf_urls': []}
        self.proof = {'official_verified': True, 'status': 'published', 'venue': 'ICML',
                      'source_url': 'https://proceedings.mlr.press/v1/fixture.html',
                      'pdf_urls': ['https://proceedings.mlr.press/v1/fixture.pdf']}

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_preprint_and_unverified_or_nonmajor_publications_are_supplements(self):
        self.assertEqual(classify(self.store, self.record)['evidence_role'], 'supplement')
        for key, invalid in [('venue', 'Other venue'), ('status', 'submitted'),
                             ('official_verified', False), ('source_url', 'https://example.org/paper')]:
            with self.subTest(key=key):
                self.store.put('venue_evidence', 'fixture', dict(self.proof, **{key: invalid}))
                classified = classify(self.store, dict(self.record, publication=self.proof))
                self.assertEqual(classified['evidence_role'], 'supplement')
                self.assertNotIn('publication', classified)

    def test_verified_major_publication_prioritizes_official_pdf(self):
        self.store.put('venue_evidence', 'fixture', self.proof)
        record = classify(self.store, dict(self.record, pdf_urls=['https://example.org/preprint.pdf']))
        self.assertEqual(record['evidence_role'], 'hard')
        self.assertEqual(record['publication'], self.proof)
        self.assertEqual(record['pdf_urls'][0], self.proof['pdf_urls'][0])

    def test_supplements_cannot_establish_gap_or_prior_coverage(self):
        paper = dict(self.record, full_text_status='verified', evidence_role='supplement',
                     note={'claims': [{'id': 'C1'}]})
        for decision in ['CANDIDATE', 'COVERED']:
            assessment = {'decision': decision, 'evidence': [{'paper_id': 'fixture', 'claim_id': 'C1'}],
                          'closest_papers': ['fixture']}
            with self.assertRaises(ResearchError):
                evidence_valid(assessment, [paper], strict=True)
            evidence_valid(assessment, [dict(paper, evidence_role='hard')], strict=True)
            assessment['evidence'] = []
            with self.assertRaises(ResearchError):
                evidence_valid(assessment, [dict(paper, evidence_role='hard')], strict=True)


if __name__ == '__main__':
    unittest.main()
