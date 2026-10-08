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
        self.assertEqual(len(list((self.root/'papers').glob('*.pdf'))), 2)
        self.assertEqual(len(list((self.root/'papers').glob('*.md'))), 1)
        paper = self.service.store.get('paper', topic['papers'][0])
        self.assertTrue((self.root/paper['report_path']).read_bytes().startswith(b'%PDF-'))
        event = self.service.store.db.execute("SELECT data FROM events WHERE action='paper.note_saved'").fetchone()
        self.assertEqual(json.loads(event['data'])['result'], paper['report_path'])
        self.assertEqual(json.loads(event['data'])['findings'], paper['note']['findings'])
        self.assertFalse(self.service.run_next())
        self.assertEqual(list((self.root/'hypothesis').glob('*.md')), [])
        self.service.close()
        self.service = Service(self.root, agent=self.agent, sources=Sources())
        self.service.recover()
        self.assertEqual(self.service.store.get('topic', topic['id'])['status'], 'AWAITING_SELECTION')
        self.assertFalse(self.service.run_next())

    def test_official_seed_is_screened_and_logged_without_fabricating_search_results(self):
        record = dict(self.service.sources.record, doi='10.0000/official-seed-fixture')
        topic = self.service.submit('Synthetic seed-routing fixture')
        topic['review_seeds'] = [record]
        self.service.store.put('topic', topic['id'], topic)
        self.assertTrue(self.service.run_next())
        reviewed = self.service.store.get('topic', topic['id'])
        self.assertEqual(len(reviewed['papers']), 1)  # same-title duplicate is merged
        row = self.service.store.db.execute('SELECT data FROM jobs WHERE entity=?', (topic['id'],)).fetchone()
        seeds = json.loads(row['data'])['review']['queries']['official_seeds']
        self.assertEqual(seeds['provider'], 'official_seed')
        self.assertEqual(seeds['papers'], [record])

    def test_detailed_request_reaches_full_text_reading_and_final_synthesis(self):
        from research_automation import schemas
        request = 'Synthetic test: compare teacher bias, assumptions and untested claims.'
        topic = self.service.submit(request)
        with patch.object(self.agent, 'ask', wraps=self.agent.ask) as ask:
            self.assertTrue(self.service.run_next())
        studies = [call for call in ask.call_args_list if call.args[2] == schemas.STUDY]
        assessments = [call for call in ask.call_args_list if call.args[2] == schemas.ASSESS]
        self.assertTrue(studies)
        self.assertTrue(assessments)
        for call in studies + assessments:
            self.assertEqual(call.args[1]['review_request'], request)
        reviewed = self.service.store.get('topic', topic['id'])
        self.assertEqual(reviewed['status'], 'AWAITING_SELECTION')
        self.assertEqual(self.service.store.list('decision'), [])
        self.assertEqual(self.service.store.list('campaign'), [])

    def test_resume_updates_stage_and_preserves_approval_usage_and_valid_outcomes(self):
        topic = self.review()
        campaign = self.approve(topic)
        row = self.service.store.db.execute('SELECT id FROM jobs WHERE entity=?', (campaign['id'],)).fetchone()
        self.service.store.finish(row['id'], 'blocked', 'Synthetic infrastructure blocker')
        campaign.update(status='BLOCKED', error='Synthetic infrastructure blocker', usage={'agent_calls': 2},
                        outcomes={'saved': {'outcome': 'NOT_SUPPORTED'}, 'pending': {'outcome': 'BLOCKED'}})
        self.service.store.put('campaign', campaign['id'], campaign)
        self.service.resume(row['id'])
        resumed = self.service.store.get('campaign', campaign['id'])
        self.assertEqual(resumed['status'], 'PLANNING')
        self.assertNotIn('error', resumed)
        self.assertEqual(resumed['usage'], campaign['usage'])
        self.assertEqual(resumed['limits'], campaign['limits'])
        self.assertEqual(resumed['approval_id'], campaign['approval_id'])
        self.assertEqual(resumed['outcomes'], {'saved': {'outcome': 'NOT_SUPPORTED'}})
        self.service.decide(topic['id'], 'defer', 'Synthetic user deferral')
        with self.assertRaises(ResearchError):
            self.service.resume(row['id'])

    def test_explicit_time_extension_preserves_frozen_campaign_and_refreshes_context(self):
        from research_automation.context import Context
        from research_automation.common import BudgetExceeded
        topic = self.review()
        campaign = self.approve(topic)
        old_decision = self.service.store.get('decision', campaign['approval_id'])
        old_limits = dict(campaign['limits'])
        context = Context(self.service, {'id': self.service.store.enqueue('execute',campaign['id']),
                          'kind':'execute','entity':campaign['id'],'data':{'usage':{}}})
        context.previous_seconds = old_limits['max_campaign_seconds'] + 1
        with self.assertRaises(BudgetExceeded):
            context.guard()
        updated = self.service.approve(topic['id'],topic['revision'],'Allow three hours for this frozen test.',
                                       {'max_campaign_seconds':old_limits['max_campaign_seconds']+3600},
                                       campaign_id=campaign['id'])
        context.guard()
        self.assertEqual(updated['id'],campaign['id'])
        self.assertEqual(updated['approval_id'],campaign['approval_id'])
        self.assertEqual(updated['hypothesis_ids'],campaign['hypothesis_ids'])
        self.assertEqual(updated['usage'],campaign['usage'])
        self.assertEqual(self.service.store.get('decision',campaign['approval_id']),old_decision)
        self.assertEqual({k:v for k,v in updated['limits'].items() if k!='max_campaign_seconds'},
                         {k:v for k,v in old_limits.items() if k!='max_campaign_seconds'})
        budget = self.service.store.get('decision',updated['budget_decisions'][0])
        self.assertEqual(budget['actor'],'user')
        self.assertEqual(budget['instruction'],'Allow three hours for this frozen test.')
        for limits in ({'max_runs':999},{'max_campaign_seconds':True},{'max_campaign_seconds':1}):
            with self.assertRaises(ResearchError):
                self.service.approve(topic['id'],topic['revision'],'Invalid fixture extension.',limits,campaign_id=campaign['id'])
        with self.assertRaises(ResearchError):
            self.service.approve(topic['id'],'stale','Invalid fixture extension.',{'max_campaign_seconds':20000},campaign_id=campaign['id'])
        self.service.decide(topic['id'],'defer','Synthetic revocation.')
        with self.assertRaises(ResearchError):
            self.service.approve(topic['id'],topic['revision'],'Invalid fixture extension.',{'max_campaign_seconds':20000},campaign_id=campaign['id'])

    def test_interface_reviewed_recovery_plan_is_hashed_and_requires_existing_approval(self):
        from fixtures import plan_fixture
        from research_automation.common import file_hash
        topic = self.review()
        campaign = self.approve(topic)
        path = 'hypothesis/reviewed-fixture.json'
        self.service.write(path, json.dumps({'hypotheses': [plan_fixture()]}))
        provenance = {'path': path, 'sha256': file_hash(self.root/path), 'reviewer': 'synthetic-test'}
        campaign['reviewed_plan_input'] = provenance
        self.service.store.put('campaign', campaign['id'], campaign)
        with patch.object(self.agent, 'ask', side_effect=AssertionError('Recovery input should not be regenerated')):
            self.assertTrue(self.service.run_next())
        planned = self.service.store.get('campaign', campaign['id'])
        self.assertEqual(planned['status'], 'EXECUTING')
        frozen = self.service.store.get('hypothesis', planned['hypothesis_ids'][0])
        self.assertEqual(frozen['proposal_provenance'], provenance)
        self.assertEqual(frozen['approval_id'], campaign['approval_id'])
        self.assertEqual(len(self.service.store.list('decision')), 1)
        self.assertEqual(self.service.store.list('attempt'), [])

    def test_repair_batch_preserves_invalid_parent_files_usage_and_uses_fresh_seeds(self):
        from fixtures import plan_fixture
        from research_automation.common import file_hash
        topic = self.review()
        campaign = self.approve(topic)
        self.agent.audit_pass = False
        self.service.run_next()
        self.service.run_next()
        previous = self.service.store.get('campaign', campaign['id'])
        old_id = previous['hypothesis_ids'][0]
        old = self.service.store.get('hypothesis', old_id)
        old_file_hash = file_hash(self.root/old['json_path'])
        path = 'hypothesis/revision-fixture.json'
        self.service.write(path, json.dumps({'hypotheses': [plan_fixture()]}))
        previous.update(planning_revision=2, revision_reason='Synthetic repair of an invalid application fixture.',
                        reviewed_plan_input={'path': path, 'sha256': file_hash(self.root/path)})
        self.service.store.put('campaign', campaign['id'], previous)
        self.service.store.enqueue('plan', campaign['id'])
        self.service.run_next()
        revised = self.service.store.get('campaign', campaign['id'])
        self.assertEqual(len(revised['hypothesis_ids']), 2)
        self.assertEqual(revised['outcomes'], previous['outcomes'])
        self.assertEqual(revised['usage'], previous['usage'])
        new = self.service.store.get('hypothesis', revised['hypothesis_ids'][1])
        self.assertEqual(new['plan_revision'], 2)
        self.assertFalse(set(old['seeds']) & set(new['seeds']))
        self.assertEqual(file_hash(self.root/old['json_path']), old_file_hash)
        self.assertEqual(revised['planned_runs'], 2 * previous['planned_runs'])

    def test_changed_recovery_plan_is_blocked_before_freezing_or_execution(self):
        from fixtures import plan_fixture
        from research_automation.common import file_hash
        topic = self.review()
        campaign = self.approve(topic)
        path = 'hypothesis/changed-fixture.json'
        self.service.write(path, json.dumps({'hypotheses': [plan_fixture()]}))
        campaign['reviewed_plan_input'] = {'path': path, 'sha256': file_hash(self.root/path)}
        self.service.store.put('campaign', campaign['id'], campaign)
        self.service.write(path, json.dumps({'hypotheses': []}))
        self.service.run_next()
        blocked = self.service.store.get('campaign', campaign['id'])
        self.assertEqual(blocked['status'], 'BLOCKED')
        self.assertIn('changed', blocked['error'])
        self.assertEqual(self.service.store.list('hypothesis'), [])
        self.assertEqual(self.service.store.list('attempt'), [])

    def test_candidates_get_separate_pdf_embeds_and_repeat_publication_is_idempotent(self):
        from research_automation.surveys import publish_ready_batches, publish_selectable_topic
        topics = [self.review(), self.review()]
        reports = []
        for topic in topics:
            path = publish_selectable_topic(self.service, topic)
            reports.append(path)
            self.assertTrue((self.root/path).read_bytes().startswith(b'%PDF-'))
        self.assertNotEqual(*reports)
        self.service.store.put('policy', 'topic_delivery', {'separate_files': True})
        self.service.store.put('survey_batch', 'separate-fixture', {
            'id': 'separate-fixture', 'topic_ids': [t['id'] for t in topics],
            'instruction': 'Synthetic delivery test; not a research finding.'})
        self.assertEqual(publish_ready_batches(self.service), 1)
        self.assertEqual(publish_ready_batches(self.service), 0)
        self.assertEqual(self.service.store.db.execute("SELECT COUNT(*) FROM events WHERE action='literature.report'").fetchone()[0], 0)
        rows = self.service.store.db.execute("SELECT outbox.payload FROM outbox JOIN events USING(seq) WHERE events.action='topic.awaiting_selection'").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual({json.loads(row['payload'])['_attachment'] for row in rows}, set(reports))
        self.assertTrue(all(len(json.loads(row['payload'])['embeds']) == 1 for row in rows))
        self.assertEqual(self.service.store.list('decision'), [])
        self.assertEqual(self.service.store.list('campaign'), [])
        stale = dict(topics[0], revision='stale-fixture-revision')
        with self.assertRaises(ResearchError):
            publish_selectable_topic(self.service, stale)

    def test_pinned_search_queries_survive_restart_and_model_rewriting(self):
        queries = ['known paper title', 'gene editing symbolic regression']
        topic = self.service.submit('Synthetic query-routing fixture', search_queries=queries)
        self.service.close()
        sources = Sources()
        self.service = Service(self.root, agent=self.agent, sources=sources)
        with patch.object(sources, 'search', wraps=sources.search) as search:
            self.service.run_next()
        self.assertEqual([call.args for call in search.call_args_list], [
            ('openalex', queries[0]), ('crossref', queries[0]),
            ('openalex', queries[1]), ('crossref', queries[1]),
        ])
        saved = self.service.store.get('topic', topic['id'])
        self.assertEqual(saved['search_queries'], queries)
        self.assertEqual(saved['status'], 'AWAITING_SELECTION')
        self.assertFalse(self.service.run_next())
        self.assertEqual(self.service.store.list('decision'), [])

    def test_survey_batch_waits_for_all_reviews_and_publishes_once_without_approval(self):
        from research_automation.surveys import publish_ready_batches
        first = self.review()
        second = self.service.submit('Synthetic second batch topic')
        self.service.store.put('survey_batch', 'synthetic-batch', {
            'id': 'synthetic-batch', 'topic_ids': [first['id'], second['id']],
            'instruction': 'Synthetic application test; not a research finding.'})
        self.assertEqual(publish_ready_batches(self.service), 0)
        self.service.run_next()
        batch = self.service.store.get('survey_batch', 'synthetic-batch')
        self.assertTrue((self.root/batch['report_path']).read_bytes().startswith(b'%PDF-'))
        self.assertEqual(len(batch['selectable']), 2)
        self.assertEqual(publish_ready_batches(self.service), 0)
        self.assertEqual(self.service.store.db.execute("SELECT COUNT(*) FROM events WHERE action='literature.report'").fetchone()[0], 1)
        self.assertEqual(self.service.store.list('decision'), [])
        self.assertEqual(self.service.store.list('campaign'), [])

    def major_policy_fixture(self):
        from research_automation.literature import paper_id
        self.service.store.put('policy', 'literature', {
            'major_only': True, 'major_venues': ['ICML'], 'official_hosts': ['proceedings.mlr.press']})
        proof = {'official_verified': True, 'status': 'published', 'venue': 'ICML',
                 'source_url': 'https://proceedings.mlr.press/v1/synthetic.html', 'pdf_urls': []}
        return paper_id(self.service.sources.record), proof

    def test_small_reading_budget_prioritizes_verified_major_work_over_supplements(self):
        identifier, proof = self.major_policy_fixture()
        self.service.store.put('venue_evidence', identifier, proof)
        self.service.config['max_full_texts'] = 1
        seed = dict(self.service.sources.record)
        supplement = dict(seed, doi='10.0000/supplement-fixture', title=seed['title'] + ' variation')
        topic = self.service.submit('Synthetic major-priority fixture')
        topic['review_seeds'] = [seed]
        self.service.store.put('topic', topic['id'], topic)
        with patch.object(self.service.sources, 'search', return_value=[supplement]):
            self.service.run_next()
        reviewed = self.service.store.get('topic', topic['id'])
        self.assertEqual(reviewed['status'], 'AWAITING_SELECTION')
        self.assertEqual(reviewed['papers'], [identifier])
        self.assertEqual(self.service.store.get('paper', identifier)['evidence_role'], 'hard')

    def test_publication_verified_during_review_is_refreshed_before_freezing_evidence(self):
        from research_automation import schemas
        identifier, proof = self.major_policy_fixture()
        original = self.agent.ask
        calls = []
        def verify_during_read(task, context, schema, **kwargs):
            if schema == schemas.STUDY:
                calls.append(context['metadata'].get('evidence_role'))
                self.service.store.put('venue_evidence', identifier, proof)
            return original(task, context, schema, **kwargs)
        with patch.object(self.agent, 'ask', side_effect=verify_during_read):
            reviewed = self.review()
        self.assertEqual(calls, ['supplement', 'hard'])
        self.assertEqual(reviewed['status'], 'AWAITING_SELECTION')
        self.assertIn('publication:' + identifier, reviewed['evidence_bundle'])

    def test_invalid_pinned_queries_do_not_create_jobs(self):
        for queries in ([], ['only one'], ['same', ' same '], ['one', 'two', 'three'], ['one', 2], 'two queries'):
            with self.subTest(queries=queries), self.assertRaises(ResearchError):
                self.service.submit('Synthetic invalid search fixture', search_queries=queries)
        self.assertEqual(self.service.store.list('topic'), [])
        self.assertEqual(self.service.store.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 0)

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
        self.assertIsNone(self.service.store.db.execute("SELECT 1 FROM events WHERE action='paper.note_saved'").fetchone())
        with self.assertRaises(ResearchError):
            self.approve(topic)

    def test_invalid_study_quote_is_repaired_before_publication(self):
        from research_automation import schemas
        original = self.agent.ask
        attempts = []
        def reply(task, context, schema, **kwargs):
            answer = original(task, context, schema, **kwargs)
            if schema == schemas.STUDY:
                attempts.append(context)
                if len(attempts) == 1:
                    answer['claims'][0]['quote'] = '0.99221.12'
            return answer
        with patch.object(self.agent, 'ask', side_effect=reply):
            topic = self.review()
        self.assertEqual(topic['status'], 'AWAITING_SELECTION')
        self.assertEqual(len(attempts), 2)
        self.assertIn('rejected_note', attempts[1])
        self.assertEqual(attempts[1]['rejected_note']['claims'][0]['quote'], '0.99221.12')
        self.assertEqual(self.service.store.db.execute("SELECT COUNT(*) FROM events WHERE action='paper.note_saved'").fetchone()[0], 1)

    def test_repeated_invalid_study_is_bounded_and_never_published(self):
        from research_automation import schemas
        original = self.agent.ask
        attempts = []
        def reply(task, context, schema, **kwargs):
            answer = original(task, context, schema, **kwargs)
            if schema == schemas.STUDY:
                attempts.append(context)
                answer['claims'][0]['page'] = 999
            return answer
        with patch.object(self.agent, 'ask', side_effect=reply):
            topic = self.review()
        self.assertEqual(len(attempts), 3)
        self.assertEqual(topic['status'], 'EVIDENCE_BLOCKED')
        self.assertEqual(self.service.store.list('paper'), [])
        self.assertIsNone(self.service.store.db.execute("SELECT 1 FROM events WHERE action='paper.note_saved'").fetchone())
        self.assertEqual(list((self.root/'papers').glob('*-report.pdf')), [])

    def test_selected_topic_automatically_plans_executes_and_reports(self):
        topic = self.review()
        campaign = self.approve(topic)
        self.assertTrue(self.service.run_next())
        planned = self.service.store.get('campaign', campaign['id'])
        self.assertTrue(planned['hypothesis_ids'])
        with patch.object(self.agent, 'ask', wraps=self.agent.ask) as asks:
            self.assertTrue(self.service.run_next())
        from research_automation import schemas
        from research_automation.common import file_hash
        audit_call = next(call for call in asks.call_args_list if call.args[2] == schemas.AUDIT)
        audit_context = audit_call.args[1]
        implementation = audit_context['analysis_implementation']
        self.assertTrue(implementation['reanalysis_exactly_matches'])
        self.assertEqual(implementation['hypothesis_count'], 1)
        self.assertEqual(file_hash(self.root/implementation['artifact']), implementation['sha256'])
        self.assertIn(implementation['artifact'], audit_context['allowed_artifacts'])
        self.assertIn('correctness_stderr', audit_context)
        complete = self.service.store.get('campaign', campaign['id'])
        self.assertEqual(complete['status'], 'COMPLETED', complete.get('error'))
        result = next(iter(complete['outcomes'].values()))
        self.assertEqual(result['outcome'], 'SUPPORTED', result)
        self.assertTrue((self.root/complete['report_path']).is_file())
        self.assertTrue((self.root/complete['report_pdf_path']).read_bytes().startswith(b'%PDF-'))
        self.assertEqual(len(self.service.store.list('attempt')), complete['planned_runs'])
        self.assertFalse(self.service.run_next())
        from research_automation.analysis import analyze
        data = json.loads((self.root/result['work_directory']/'analysis/input.json').read_text())
        statistics = json.loads((self.root/result['work_directory']/'analysis/statistics.json').read_text())
        self.assertEqual(analyze(data['plan'],data['confirmation'],data['reproduction'],data['hypothesis_count']), statistics)
        self.assertTrue(self.service.store.db.execute("SELECT 1 FROM events WHERE action='campaign.result'").fetchone())
        event = self.service.store.db.execute("SELECT data FROM events WHERE action='campaign.result'").fetchone()
        self.assertEqual(json.loads(event['data'])['result'], complete['report_pdf_path'])
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
