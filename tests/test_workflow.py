import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_automation.common import ResearchError
from research_automation.service import Service

from fixtures import Agent, Sources, pdf_bytes


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.agent = Agent()
        self.service = Service(self.root, agent=self.agent, sources=Sources())
        self.fetch = patch('research_automation.literature.fetch', return_value=pdf_bytes())
        self.fetch.start()

    def tearDown(self):
        self.fetch.stop()
        self.service.close()
        self.directory.cleanup()

    def review(self):
        topic = self.service.submit('Synthetic integration test question; never a research finding.')
        self.assertTrue(self.service.run_next())
        return self.service.store.get('topic', topic['id'])

    def approve(self, topic):
        return self.service.approve(topic['id'], topic['revision'], 'Explicit synthetic-test selection only.')

    def test_review_archives_evidence_and_persistently_stops(self):
        topic = self.review()
        self.assertEqual(topic['status'], 'AWAITING_SELECTION')
        self.assertEqual(len(list((self.root/'papers').glob('*.pdf'))), 1)
        self.assertEqual(len(list((self.root/'papers').glob('*.md'))), 1)
        self.assertFalse(self.service.run_next())
        self.assertEqual(list((self.root/'hypothesis').glob('*.md')), [])
        self.service.close()
        self.service = Service(self.root, agent=self.agent, sources=Sources())
        self.service.recover()
        self.assertEqual(self.service.store.get('topic', topic['id'])['status'], 'AWAITING_SELECTION')
        self.assertFalse(self.service.run_next())

    def test_unreviewed_stale_and_changed_evidence_cannot_be_approved(self):
        raw = self.service.submit('Unreviewed synthetic fixture')
        with self.assertRaises(ResearchError):
            self.approve(raw)
        self.service.run_next()
        topic = self.service.store.get('topic', raw['id'])
        with self.assertRaises(ResearchError):
            self.service.approve(topic['id'], 'wrong', 'Synthetic selection')
        paper = self.service.store.get('paper', topic['papers'][0])
        (self.root/paper['note_path']).write_text('changed evidence', encoding='utf-8')
        with self.assertRaises(ResearchError):
            self.approve(topic)

    def test_approval_requires_user_actor(self):
        topic = self.review()
        with self.assertRaises(ResearchError):
            self.service.approve(topic['id'], topic['revision'], 'Agent fabricated selection', actor='agent')

    def test_refinement_is_bounded_to_two_rounds(self):
        self.agent.covered = True
        topic = self.review()
        self.assertEqual(topic['status'], 'COVERED')
        self.assertEqual(len(topic['review_history']), 3)
        self.assertFalse(self.service.run_next())

    def test_missing_pdf_blocks_candidate(self):
        self.fetch.stop()
        self.fetch = patch('research_automation.literature.fetch', side_effect=ResearchError('PDF unavailable'))
        self.fetch.start()
        topic = self.review()
        self.assertEqual(topic['status'], 'EVIDENCE_BLOCKED')
        with self.assertRaises(ResearchError):
            self.approve(topic)

    def test_selected_topic_automatically_plans_executes_and_reports(self):
        topic = self.review()
        campaign = self.approve(topic)
        self.assertTrue(self.service.run_next())
        planned = self.service.store.get('campaign', campaign['id'])
        self.assertTrue(planned['hypothesis_ids'])
        self.assertTrue(self.service.run_next())
        complete = self.service.store.get('campaign', campaign['id'])
        self.assertEqual(complete['status'], 'COMPLETED', complete.get('error'))
        result = next(iter(complete['outcomes'].values()))
        self.assertEqual(result['outcome'], 'SUPPORTED', result)
        self.assertTrue((self.root/complete['report_path']).is_file())
        self.assertEqual(len(self.service.store.list('attempt')), complete['planned_runs'])
        self.assertFalse(self.service.run_next())
        from research_automation.analysis import analyze
        data = json.loads((self.root/result['work_directory']/'analysis/input.json').read_text())
        statistics = json.loads((self.root/result['work_directory']/'analysis/statistics.json').read_text())
        self.assertEqual(analyze(data['plan'],data['confirmation'],data['reproduction'],data['hypothesis_count']), statistics)
        self.assertTrue(self.service.store.db.execute("SELECT 1 FROM events WHERE action='campaign.result'").fetchone())
        # Simulate losing the final database update after a subprocess completed.
        original=self.service.store.list('run')[0]
        original['status']='RUNNING'
        original.pop('manifest_hash',None)
        self.service.store.put('run',original['logical_key'],original)
        plan=self.service.store.get('hypothesis',complete['hypothesis_ids'][0])
        from research_automation.context import Context
        from research_automation.experiments import execute_run
        context=Context(self.service,{'id':'recovery-fixture','kind':'execute','entity':complete['id'],'data':{'usage':{}}})
        context.cancelled=lambda:False
        run_count=len(self.service.store.list('attempt'))
        recovered,_=execute_run(context,plan,self.root/result['work_directory'],'correctness')
        self.assertEqual(recovered['id'],original['id'])
        self.assertEqual(len(self.service.store.list('attempt')),run_count)

    def test_all_negative_hypotheses_still_produce_complete_result(self):
        self.agent.negative = True
        topic = self.review()
        campaign = self.approve(topic)
        self.service.run_next()
        self.service.run_next()
        complete = self.service.store.get('campaign', campaign['id'])
        self.assertEqual(complete['status'], 'COMPLETED')
        result = next(iter(complete['outcomes'].values()))
        self.assertEqual(result['outcome'], 'NOT_SUPPORTED', result)
        self.assertIn('NOT_SUPPORTED', (self.root/complete['report_path']).read_text())

    def test_failed_scientific_audit_cannot_mark_supported(self):
        self.agent.audit_pass = False
        campaign = self.approve(self.review())
        self.service.run_next()
        self.service.run_next()
        result = next(iter(self.service.store.get('campaign', campaign['id'])['outcomes'].values()))
        self.assertEqual(result['outcome'], 'INVALID')

    def test_revoked_selection_cancels_queued_execution_and_writes_report(self):
        topic = self.review()
        campaign = self.approve(topic)
        self.service.run_next()
        self.service.decide(topic['id'], 'cancel', 'Stop synthetic fixture campaign')
        self.assertFalse(self.service.run_next())
        updated = self.service.store.get('campaign', campaign['id'])
        self.assertEqual(updated['status'], 'CANCELLED')
        self.assertTrue((self.root/updated['report_path']).exists())
        with self.assertRaises(ResearchError):
            self.service.require_approval(topic['id'], campaign['approval_id'])

    def test_modified_frozen_plan_blocks_execution(self):
        campaign = self.approve(self.review())
        self.service.run_next()
        updated = self.service.store.get('campaign', campaign['id'])
        plan = self.service.store.get('hypothesis', updated['hypothesis_ids'][0])
        (self.root/plan['plan_path']).write_text('changed criteria',encoding='utf-8')
        self.service.run_next()
        result = next(iter(self.service.store.get('campaign', campaign['id'])['outcomes'].values()))
        self.assertNotEqual(result['outcome'], 'SUPPORTED')
        self.assertEqual(len(self.service.store.list('attempt')), 0)

    def test_campaign_budget_exhaustion_preserves_partial_report(self):
        campaign = self.approve(self.review())
        self.service.run_next()
        updated = self.service.store.get('campaign', campaign['id'])
        updated['usage']['runs'] = updated['limits']['max_runs']
        self.service.store.put('campaign', campaign['id'], updated)
        self.service.run_next()
        result = self.service.store.get('campaign', campaign['id'])
        self.assertEqual(result['status'], 'PARTIAL')
        self.assertEqual(next(iter(result['outcomes'].values()))['outcome'], 'BLOCKED')
        self.assertTrue((self.root/result['report_path']).exists())

    def test_changed_approved_paper_blocks_work_and_still_saves_report(self):
        topic=self.review()
        campaign=self.approve(topic)
        self.service.run_next()
        paper=self.service.store.get('paper',topic['papers'][0])
        (self.root/paper['pdf_path']).write_bytes(b'changed approved PDF')
        self.service.run_next()
        result=self.service.store.get('campaign',campaign['id'])
        self.assertEqual(result['status'],'BLOCKED')
        self.assertTrue((self.root/result['report_path']).exists())
        self.assertEqual(len(self.service.store.list('attempt')),0)

    def test_topic_publication_is_reconciled_without_inventing_approval(self):
        topic=self.review()
        original=self.service.store._put
        def interrupted(kind,identifier,value,*args,**kwargs):
            if kind=='topic':
                raise OSError('Synthetic crash between rename and state commit')
            return original(kind,identifier,value,*args,**kwargs)
        topic['status']='DEFERRED'
        with patch.object(self.service.store,'_put',side_effect=interrupted):
            with self.assertRaises(OSError):
                self.service.save_topic(topic)
        self.assertEqual(self.service.store.get('publication',topic['id'])['status'],'pending')
        self.service.recover()
        recovered=self.service.store.get('topic',topic['id'])
        self.assertEqual(recovered['status'],'DEFERRED')
        self.assertNotIn('latest_decision',recovered)
        self.assertEqual(self.service.store.get('publication',topic['id'])['status'],'done')


if __name__=='__main__':
    unittest.main()
