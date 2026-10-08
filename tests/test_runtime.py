import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import psutil

from research_automation.analysis import analyze
from research_automation.common import ResearchError, child_environment, safe_path
from research_automation.discord import Notifier
from research_automation.experiments import validate_metrics
from research_automation.hypothesis import generation_schema, validate_plan
from research_automation.literature import validate_note, validate_pdf
from research_automation.service import Service
from research_automation.store import Store

from fixtures import Agent, Sources, PAPER_TEXT, pdf_bytes, plan_fixture


class Response(io.BytesIO):
    headers = {}


class RuntimeTests(unittest.TestCase):
    def test_unresolvable_pdf_host_is_a_controlled_source_failure(self):
        import socket
        from research_automation.network import public_url
        with patch('research_automation.network.socket.getaddrinfo', side_effect=socket.gaierror(11001, 'host unavailable')):
            with self.assertRaisesRegex(ResearchError, 'hostname could not be resolved'):
                public_url('https://unavailable.example/paper.pdf')

    def test_pdf_tables_wrap_cells_fit_page_and_repeat_headers(self):
        from pypdf import PdfReader
        from reportlab.platypus import LongTable
        from research_automation.reports import pdf_report
        tables = []
        original = LongTable
        def capture(*args, **kwargs):
            table = original(*args, **kwargs)
            tables.append(table)
            return table
        rows = '\n'.join('| tree candidate '+str(i)+' | Long evidence and limitations '+('nested expressions '*8)+' | '+str(i/100)+' |' for i in range(50))
        with patch('research_automation.reports.LongTable', side_effect=capture):
            data = pdf_report('Grammar pilot report', [('Comparison', '| Method | Evidence | MSE |\n| --- | --- | --- |\n'+rows)])
        pages = PdfReader(io.BytesIO(data)).pages
        self.assertGreater(len(pages), 1)
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0].repeatRows, 1)
        self.assertLessEqual(sum(tables[0]._colWidths), 508)
        text = '\n'.join(page.extract_text() for page in pages)
        self.assertIn('tree candidate 49', text)
        self.assertGreater(text.count('Method'), 1)
        self.assertNotIn('| --- |', text)

    def test_generated_plan_schema_requires_budget_contract_without_changing_legacy_schema(self):
        from research_automation import schemas
        original = json.loads(json.dumps(schemas.PLANS))
        generated = generation_schema()
        item = generated['properties']['hypotheses']['items']
        self.assertEqual(set(item['required']), set(item['properties']))
        self.assertIn('budget_contract', item['required'])
        self.assertEqual(schemas.PLANS, original)
        self.assertNotIn('budget_contract', schemas.HYPOTHESIS['required'])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.store = Store(self.root)
        self.secrets = patch('research_automation.discord.secrets', return_value={'DISCORD_WEBHOOK_URL':'https://discord.com/api/webhooks/123/test-only','OPENALEX_API_KEY':''})
        self.secrets.start()

    def tearDown(self):
        self.secrets.stop()
        self.store.close()
        self.directory.cleanup()

    def test_action_state_and_outbox_are_atomic_and_event_key_is_idempotent(self):
        self.store.put('example','id',{'status':'done'},'literature.report','Saved','once')
        event = self.store.event('literature.report',{'summary':'duplicate'},'once')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],1)
        self.assertEqual(self.store.pending_count(),1)
        self.assertEqual(self.store.get('example','id')['status'],'done')

    def test_maintenance_events_stay_local_and_research_still_notifies(self):
        quiet = ('system.initialized', 'worker.started', 'worker.stopped', 'worker.stop_requested',
                 'interface.action_completed', 'implementation.file_completed', 'implementation.file_ready',
                 'agent.started', 'agent.completed', 'agent.reused', 'artifact.saved',
                 'artifact.publication_recovered', 'paper.download_started', 'paper.download_failed',
                 'paper.pdf_validated', 'paper.reused', 'job.cancelled', 'job.progress', 'paper.screened',
                 'literature.citation_trace_started', 'literature.citation_trace_completed')
        quiet += ('literature.query_started', 'literature.query_completed', 'job.started', 'job.queued',
                  'job.done', 'job.blocked', 'job.resumed', 'job.recovered', 'idea.accepted',
                  'paper.evidence_blocked', 'topic.assessed', 'topic.refinement_started',
                  'topic.review_closed', 'hypothesis.outcome_saved', 'selection.approved',
                  'experiment.run_started', 'experiment.run_completed', 'planning.completed',
                  'future.unknown_completed')
        for action in quiet:
            self.store.event(action, {'summary': 'Synthetic maintenance fixture'})
        self.assertEqual(self.store.pending_count(), 0)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0], len(quiet))
        self.store.event('topic.awaiting_selection', {'topic': 'synthetic-topic'})
        self.store.event('workflow.blocked', {'reason': 'Synthetic intervention fixture'})
        self.store.event('hypothesis.verified', {'hypothesis': 'synthetic-hypothesis'})
        self.store.event('campaign.result', {'topic': 'synthetic-topic'})
        self.store.event('paper.note_saved', {'paper': 'synthetic-paper'})
        self.assertEqual(self.store.pending_count(), 5)

    def test_legacy_unsent_maintenance_is_removed_without_losing_audit_or_receipts(self):
        payload = json.dumps({'embeds': [{'title': 'Synthetic old maintenance notification'}]})
        quiet = ('interface.action_completed', 'agent.started', 'agent.completed',
                 'paper.download_started', 'paper.download_failed', 'artifact.saved',
                 'job.cancelled', 'job.progress', 'paper.screened')
        for action in quiet:
            event = self.store.event(action, {'summary': 'Synthetic muted fixture'})
            seq = self.store.db.execute('SELECT seq FROM events WHERE id=?', (event,)).fetchone()[0]
            self.store.db.execute("INSERT INTO outbox(id,seq,part,payload,status) VALUES(?,?,?,?,?)", (event + ':1', seq, 1, payload, 'pending'))
            self.store.db.execute("INSERT INTO outbox(id,seq,part,payload,status,message_id) VALUES(?,?,?,?,?,?)", (event + ':2', seq, 2, payload, 'sent', 'synthetic-receipt'))
        calls = []
        Notifier(self.store, lambda *args, **kwargs: calls.append(args)).flush()
        self.assertEqual(calls, [])
        self.assertEqual(self.store.pending_count(), 0)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0], len(quiet))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0], len(quiet))
        self.assertEqual(self.store.db.execute('SELECT message_id FROM outbox').fetchone()[0], 'synthetic-receipt')

    def test_event_splits_unicode_with_mentions_disabled(self):
        self.store.event('literature.report',{'summary':'😀'*2500})
        rows = self.store.db.execute('SELECT payload FROM outbox').fetchall()
        self.assertGreater(len(rows),1)
        for row in rows:
            data = json.loads(row['payload'])
            self.assertIn('embeds',data)
            self.assertNotIn('content',data)
            self.assertLessEqual(len(data['embeds'][0]['description'].encode('utf-16-le'))//2,4096)
        self.assertEqual(data['allowed_mentions'],{'parse':[]})

    def test_live_preferences_apply_to_existing_connections_and_preserve_receipts(self):
        event = self.store.event('literature.report', {'summary': 'Synthetic report'})
        seq = self.store.db.execute('SELECT seq FROM events WHERE id=?', (event,)).fetchone()[0]
        self.store.db.execute("INSERT INTO outbox(id,seq,part,payload,status,message_id) VALUES(?,?,?,?,?,?)", (event + ':2', seq, 2, '{}', 'sent', 'synthetic-receipt'))
        other = Store(self.root)
        try:
            other.set_notification_actions(['paper.note_saved'])
            self.store.event('literature.report', {'summary': 'Synthetic report after preference change'})
            self.store.event('paper.note_saved', {'title': 'Synthetic paper'})
            self.assertEqual(self.store.pending_count(), 1)
            self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0], 3)
            self.assertEqual(self.store.db.execute("SELECT message_id FROM outbox WHERE status='sent'").fetchone()[0], 'synthetic-receipt')
        finally:
            other.close()

    def test_pending_embed_is_rewritten_without_resetting_retry_or_receipt(self):
        event = self.store.event('paper.note_saved', {'title': 'Synthetic paper', 'result': 'fixture.pdf'})
        self.store.db.execute("UPDATE outbox SET payload=?,attempts=3,next_at=12345,error=? WHERE id=?", ('{"embeds":[{"title":"Old completion title"}]}', 'Attachment exceeded upload limit; sending embed summary', event + ':1'))
        self.store.reformat_pending()
        row = self.store.db.execute('SELECT * FROM outbox WHERE id=?', (event + ':1',)).fetchone()
        payload = json.loads(row['payload'])
        self.assertNotIn('Old completion title', payload['embeds'][0]['title'])
        self.assertNotIn('_attachment', payload)
        self.assertEqual(row['attempts'], 3)
        self.assertEqual(row['next_at'], 12345)

    def test_paper_embed_orders_sources_hides_paths_and_keeps_attachment(self):
        from research_automation.messages import build_messages
        payload = build_messages('paper.note_saved', {
            'entity': 'fixture-id', 'paper': 'fixture-id', 'findings': '合成測試',
            'result': 'fixture.pdf', 'source': 'https://example.org/paper',
            'title': 'Synthetic paper'}, 'event', 1, '2026-10-08T00:00:00Z')[0]
        self.assertEqual(payload['embeds'][0]['title'], 'Paper study report (fixture-id)')
        fields = payload['embeds'][0]['fields']
        self.assertEqual([f['name'] for f in fields[:2]], ['Paper title', 'Source'])
        self.assertFalse({'Entity', 'Paper ID', 'Result path'} & {f['name'] for f in fields})
        self.assertEqual(payload['_attachment'], 'fixture.pdf')

    def test_confirmed_delivery_is_recorded_and_not_resent(self):
        self.store.event('literature.report',{'summary':'Synthetic notification fixture'})
        calls=[]
        def opener(request,timeout):
            calls.append(request)
            self.assertIn('wait=true',request.full_url)
            return Response(b'{"id":"fixture-message"}')
        notifier=Notifier(self.store,opener)
        self.assertEqual(notifier.flush(),1)
        self.assertEqual(notifier.flush(),0)
        self.assertEqual(len(calls),1)
        self.assertEqual(self.store.db.execute('SELECT message_id FROM outbox').fetchone()[0],'fixture-message')

    def test_paper_publication_date_survives_pending_reformat_and_is_not_event_time(self):
        self.store.put('paper', 'dated-fixture', {'year': 2021, 'publication_date': '2021-07-18', 'provider': 'crossref'})
        event = self.store.event('paper.note_saved', {'paper': 'dated-fixture', 'title': 'Synthetic dated paper', 'source': 'https://example.org/paper'})
        self.store.reformat_pending()
        row = self.store.db.execute('SELECT payload FROM outbox WHERE id=?', (event + ':1',)).fetchone()
        fields = json.loads(row['payload'])['embeds'][0]['fields']
        self.assertEqual([f['name'] for f in fields[:3]], ['Paper title', 'Source', 'Publication date'])
        self.assertEqual(fields[2]['value'], '2021-07-18')

    def test_topic_selection_is_one_embed_with_one_pdf_even_for_long_unicode_fields(self):
        from research_automation.messages import build_messages, units
        data = {key: '😀' * 4000 for key in ('question', 'closest_papers', 'gap', 'feasibility', 'limitations')}
        data.update(topic='synthetic-topic', revision='synthetic-revision', result='topic/fixture.pdf', artifact='private-path.md')
        payloads = build_messages('topic.awaiting_selection', data, 'event', 1, '2026-10-08T00:00:00Z')
        self.assertEqual(len(payloads), 1)
        self.assertEqual(len(payloads[0]['embeds']), 1)
        self.assertEqual(payloads[0]['_attachment'], 'topic/fixture.pdf')
        embed = payloads[0]['embeds'][0]
        self.assertIn('(synthetic-topic)', embed['title'])
        self.assertNotIn('Path', [f['name'] for f in embed['fields']])
        size = units(embed['title'] + embed['description'] + embed['footer']['text'])
        size += sum(units(f['name'] + f['value']) for f in embed['fields'])
        self.assertLess(size, 5500)
        self.assertTrue(all('attached PDF' in f['value'] for f in embed['fields'] if f['name'] != 'Topic revision'))

    def test_publication_year_does_not_borrow_preprint_date_or_notification_time(self):
        paper = {'year': 2020, 'publication_date': '2020-12-03', 'provider': 'arxiv', 'preprint_id': 'fixture',
                 'publication': {'year': 2021, 'status': 'published'}}
        self.store.put('paper', 'fixture', paper)
        self.assertEqual(self.store.notification_data('paper.note_saved', {'paper': 'fixture'})['published_date'], '2021 (year only)')
        self.store.put('publication_date', 'fixture', {'source_url': 'https://example.org/official', 'date': '2021-07-18'})
        paper['publication']['source_url'] = 'https://example.org/official'
        self.store.put('paper', 'fixture', paper)
        self.assertEqual(self.store.notification_data('paper.note_saved', {'paper': 'fixture'})['published_date'], '2021-07-18')
        paper['publication']['source_url'] = 'https://example.org/different'
        self.store.put('paper', 'fixture', paper)
        self.assertEqual(self.store.notification_data('paper.note_saved', {'paper': 'fixture'})['published_date'], '2021 (year only)')
        paper.pop('publication')
        self.store.put('paper', 'fixture', paper)
        self.assertEqual(self.store.notification_data('paper.note_saved', {'paper': 'fixture'})['published_date'], '2020-12-03 (preprint)')
        self.assertEqual(self.store.notification_data('paper.note_saved', {'paper': 'missing'})['published_date'], 'Not available')

    def test_scholarly_dates_use_publication_fields_with_actual_precision(self):
        from research_automation.literature import from_crossref, from_openalex
        work = {'id': 'synthetic', 'publication_year': 2021, 'publication_date': '2021-07-18'}
        self.assertEqual(from_openalex(work)['publication_date'], '2021-07-18')
        work = {'published-online': {'date-parts': [[2021, 7]]}, 'published-print': {'date-parts': [[2022, 1, 2]]},
                'created': {'date-parts': [[2020, 1, 1]]}, 'published': {'date-parts': [[2021]]}}
        self.assertEqual(from_crossref(work)['publication_date'], '2021-07')
        self.assertEqual(from_crossref({'published': {'date-parts': [[2021]]}})['publication_date'], '2021')
        self.assertIsNone(from_crossref({'created': {'date-parts': [[2020, 1, 1]]}})['publication_date'])

    def test_rate_limit_persists_server_retry_and_survives_restart(self):
        self.store.event('literature.report',{'summary':'Synthetic notification fixture'})
        def opener(request,timeout):
            raise urllib.error.HTTPError(request.full_url,429,'rate limit',{},io.BytesIO(b'{"retry_after":123}'))
        before=time.time()
        self.assertEqual(Notifier(self.store,opener).flush(),0)
        row=self.store.db.execute('SELECT * FROM outbox').fetchone()
        self.assertEqual(row['status'],'pending')
        self.assertEqual(row['attempts'],0)
        self.assertGreaterEqual(row['next_at'],before+123)
        self.store.close()
        self.store=Store(self.root)
        self.assertGreater(self.store.db.execute('SELECT next_at FROM outbox').fetchone()[0],before)

    def test_permanent_failure_and_ambiguous_timeout_stay_visible(self):
        self.store.event('literature.report',{'summary':'Synthetic notification fixture'})
        def permanent(request,timeout):
            raise urllib.error.HTTPError(request.full_url,404,'deleted',{},io.BytesIO())
        notifier=Notifier(self.store,permanent)
        notifier.flush()
        self.assertEqual(self.store.db.execute('SELECT status FROM outbox').fetchone()[0],'dead')
        notifier.replay()
        def ambiguous(request,timeout):
            raise TimeoutError('URL must not be printed')
        Notifier(self.store,ambiguous).flush()
        row=self.store.db.execute('SELECT * FROM outbox').fetchone()
        self.assertEqual(row['status'],'pending')
        self.assertEqual(row['error'],'TimeoutError')

    def test_unconfirmed_response_is_not_marked_sent(self):
        self.store.event('literature.report',{'summary':'Synthetic notification fixture'})
        Notifier(self.store,lambda request,timeout:Response(b'{}')).flush()
        self.assertNotEqual(self.store.db.execute('SELECT status FROM outbox').fetchone()[0],'sent')

    def test_webhook_is_redacted_and_not_in_child_environment(self):
        secret='https://discord.com/api/webhooks/123/fixture-secret'
        with patch.dict(os.environ,{'DISCORD_WEBHOOK_URL':secret,'OPENALEX_API_KEY':'fixture-key','OTHER_TOKEN':'fixture-token'}):
            self.store.event('error',{'summary':secret})
            env=child_environment()
            self.assertNotIn('DISCORD_WEBHOOK_URL',env)
            self.assertNotIn('OPENALEX_API_KEY',env)
            self.assertNotIn('OTHER_TOKEN',env)
        data=self.store.db.execute('SELECT data FROM events').fetchone()[0]
        self.assertNotIn('fixture-secret',data)

    def test_paths_cannot_escape_workspace_or_use_windows_reserved_names(self):
        for path in ('../elsewhere','/absolute','C:/absolute','data\\escape','data/CON.txt'):
            with self.assertRaises(ResearchError,msg=path):
                safe_path(self.root,path)

    def test_pdf_identity_and_exact_evidence_locations_are_verified(self):
        pages=validate_pdf(pdf_bytes(),Sources().record)
        self.assertIn('Synthetic',pages[0])
        with self.assertRaises(ResearchError):
            validate_pdf(b'<html>Not a PDF</html>',Sources().record)
        with self.assertRaises(ResearchError):
            validate_pdf(pdf_bytes(),{'title':'Completely unrelated quantum superconductivity paper','doi':''})
        note={'identity_verified':True,'claims':[{'id':'a','page':1,'quote':'Invented evidence not present'},{'id':'b','page':1,'quote':'Also invented evidence'}]}
        with self.assertRaises(ResearchError):
            validate_note(note,pages)

    def test_invalid_plan_and_unfair_metrics_are_rejected(self):
        plan=plan_fixture()
        config={'evaluation_budget':100}
        evidence={plan['evidence'][0]['paper_id']:{'c1'}}
        plan['files'][0]['content']='import subprocess\n'
        with self.assertRaises(ResearchError):
            validate_plan(plan,config,evidence)
        plan=plan_fixture()
        self.assertEqual(validate_plan(plan,config,evidence),20)
        plan['files'][0]['path']='../../outside.py'
        with self.assertRaises(ResearchError):
            validate_plan(plan,config,evidence)
        plan=plan_fixture()
        bad={'metric':'squared_error','unit':'squared-units','seed':1,'condition':'near','candidate':1.,'baseline':2.,'ablation':3.,'evaluations':{'candidate':100,'baseline':10,'ablation':100},'input_sha256':'a'*64}
        with self.assertRaises(ResearchError):
            validate_metrics(bad,plan,1,'near')

    def test_analysis_requires_all_units_and_reproduction(self):
        plan=plan_fixture()
        plan['seeds']=[1,2,3,4,5]
        def measurement(seed,condition):
            return {'condition':condition,'seed':seed,'candidate':1.,'baseline':2.,'ablation':3.,'input_sha256':'a'*64}
        rows=[measurement(seed,c) for c in plan['conditions'] for seed in plan['seeds']]
        repeated=[measurement(seed,c) for c in plan['conditions'] for seed in plan['seeds'][:3]]
        self.assertEqual(analyze(plan,rows,repeated,1)['outcome'],'SUPPORTED')
        self.assertEqual(analyze(plan,rows,[],1)['outcome'],'INCONCLUSIVE')
        with self.assertRaises(ResearchError):
            analyze(plan,rows[:-1],repeated,1)

    def test_neural_plan_imports_require_installed_scientific_packages(self):
        plan = plan_fixture()
        plan['files'][0]['content'] = 'import torch\nimport numpy\n'
        config = {'evaluation_budget': 100}
        evidence = {plan['evidence'][0]['paper_id']: {'c1'}}
        with patch('research_automation.hypothesis.scientific_packages', return_value={}):
            with self.assertRaises(ResearchError):
                validate_plan(plan, config, evidence)
        with patch('research_automation.hypothesis.scientific_packages', return_value={'torch': 'fixture', 'numpy': 'fixture'}):
            self.assertEqual(validate_plan(plan, config, evidence), 20)
            plan['files'][0]['content'] += 'import requests\n'
            with self.assertRaises(ResearchError):
                validate_plan(plan, config, evidence)

    def test_explicit_common_cap_preserves_actual_counts_and_rejects_overruns(self):
        plan = plan_fixture()
        counts = {'candidate': 80, 'baseline': 70, 'ablation': 75}
        metrics = {'metric':'squared_error', 'unit':'squared-units', 'seed':1, 'condition':'near',
                   'candidate':1., 'baseline':2., 'ablation':3., 'evaluations':counts, 'input_sha256':'a'*64}
        with self.assertRaises(ResearchError):
            validate_metrics(metrics, plan, 1, 'near')
        plan['budget_contract'] = 'common_cap'
        validate_metrics(metrics, plan, 1, 'near')
        counts['candidate'] = 101
        with self.assertRaises(ResearchError):
            validate_metrics(metrics, plan, 1, 'near')
        counts['candidate'] = 0
        with self.assertRaises(ResearchError):
            validate_metrics(metrics, plan, 1, 'near')

    def test_experiment_environment_keeps_windows_identity_but_excludes_credentials(self):
        import getpass
        from research_automation.experiments import experiment_environment
        with patch.dict(os.environ, {'USERNAME': 'fixture-user', 'DISCORD_WEBHOOK_URL': 'fixture-secret',
                                     'OPENALEX_API_KEY': 'fixture-key', 'UNEXPECTED_VARIABLE': 'fixture-value'}, clear=True):
            environment = experiment_environment(self.root)
        self.assertEqual(environment['USERNAME'], 'fixture-user')
        self.assertFalse({'DISCORD_WEBHOOK_URL', 'OPENALEX_API_KEY', 'UNEXPECTED_VARIABLE'} & environment.keys())
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(getpass.getuser(), 'fixture-user')

    def test_attempt_history_is_retained_after_retry(self):
        self.store.put('run','logical',{'id':'first','status':'INTERRUPTED'})
        self.store.put('run','logical',{'id':'second','status':'COMPLETED'})
        self.assertEqual(len(self.store.list('attempt')),2)
        self.assertEqual(self.store.get('run','logical')['id'],'second')

    def supervised_run(self,**overrides):
        from research_automation.process_runner import run
        directory=self.root/'process-fixture'
        directory.mkdir(exist_ok=True)
        request={'run_id':'synthetic-process','command':[sys.executable,'-c','import time; time.sleep(10)'],'cwd':str(directory),'environment':child_environment(),'worker_pid':os.getpid(),'worker_created':psutil.Process().create_time(),'timeout':0.2,'memory_mb':128,'max_output_mb':1}
        request.update(overrides)
        path=directory/'request.json'
        path.write_text(json.dumps(request),encoding='utf-8')
        run(path)
        return json.loads((directory/'process.json').read_text())

    def test_supervisor_enforces_timeout_and_stops_owned_process(self):
        result=self.supervised_run()
        self.assertEqual(result['status'],'INTERRUPTED')
        self.assertEqual(result['reason'],'timeout')
        self.assertFalse(psutil.pid_exists(result['child_pid']))

    def test_supervisor_detects_lost_worker_identity(self):
        result=self.supervised_run(worker_created=psutil.Process().create_time()+100)
        self.assertEqual(result['reason'],'owner_interrupted')
        self.assertFalse(psutil.pid_exists(result['child_pid']))

    def test_supervisor_honors_cancellation_marker(self):
        directory=self.root/'process-fixture'
        directory.mkdir()
        (directory/'cancel').write_text('synthetic cancellation')
        result=self.supervised_run()
        self.assertEqual(result['reason'],'cancelled')
        self.assertFalse(psutil.pid_exists(result['child_pid']))

    def test_result_notification_is_english_embed_with_report_attachment(self):
        (self.root/'results').mkdir()
        (self.root/'results/fixture.md').write_text('Synthetic attachment; not a research finding.',encoding='utf-8')
        self.store.event('campaign.result',{'result':'results/fixture.md','outcomes':{'SUPPORTED':0,'NOT_SUPPORTED':1},'question':'Synthetic research question'})
        captured=[]
        def opener(request,timeout):
            captured.append(request)
            return Response(b'{"id":"fixture-attachment"}')
        self.assertEqual(Notifier(self.store,opener).flush(),1)
        request=captured[0]
        self.assertIn('multipart/form-data',request.get_header('Content-type'))
        body=request.data.decode('utf-8')
        self.assertIn('Research results',body)
        self.assertIn('NOT_SUPPORTED',body)
        self.assertIn('Synthetic attachment',body)
        self.assertNotIn('_attachment',body)

    def test_pdf_report_preserves_readable_traditional_chinese(self):
        from pypdf import PdfReader
        from research_automation.reports import pdf_report
        data = pdf_report('繁體中文研究報告', [('證據限制', '尚未批准選題；沒有完成實驗。'),
                                              ('來源', 'https://example.org/fixture?x=1&y=2')])
        text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)
        self.assertIn('繁體中文研究報告', text)
        self.assertIn('沒有完成實驗', text)
        self.assertIn('x=1&y=2', text)

    def test_paper_completion_and_research_report_attach_pdf(self):
        from research_automation.reports import pdf_report
        pdf = pdf_report('Synthetic English report', [('Scope', 'Not a research finding.')])
        path = self.root/'fixture.pdf'
        path.write_bytes(pdf)
        self.store.event('paper.note_saved', {'title': 'Synthetic paper', 'findings': 'Synthetic conclusion', 'result': 'fixture.pdf'})
        self.store.event('literature.report', {'summary': 'Research report; evidence review is incomplete.', 'result': 'fixture.pdf'})
        requests = []
        def opener(request, timeout):
            requests.append(request)
            return Response(b'{"id":"synthetic-pdf-receipt"}')
        self.assertEqual(Notifier(self.store, opener).flush(), 2)
        for request in requests:
            self.assertIn(b'Content-Type: application/pdf', request.data)
            self.assertIn(pdf, request.data)
            self.assertNotIn(b'_attachment', request.data)
        self.assertIn(b'Paper study report', requests[0].data)
        self.assertIn(b'Synthetic conclusion', requests[0].data)
        self.assertEqual(Notifier(self.store, opener).flush(), 0)

    def test_atomic_publication_retries_a_temporary_windows_sharing_failure(self):
        from research_automation.common import atomic_write
        target=self.root/'atomic.txt'
        target.write_text('old',encoding='utf-8')
        original=os.replace
        attempts=[]
        def replace(source,destination):
            attempts.append(source)
            if len(attempts)==1:
                raise PermissionError('Synthetic Windows sharing violation')
            return original(source,destination)
        with patch('research_automation.common.os.replace',side_effect=replace):
            atomic_write(target,'complete new artifact')
        self.assertEqual(target.read_text(),'complete new artifact')

    def test_background_worker_start_duplicate_lock_and_clean_stop(self):
        import subprocess
        from research_automation.cli import start_worker
        service=Service(self.root)
        process=None
        try:
            with patch.dict(os.environ,{'DISCORD_WEBHOOK_URL':'','OPENALEX_API_KEY':''}):
                started=start_worker(service)
            self.assertEqual(started['status'],'started')
            process=psutil.Process(started['pid'])
            self.assertTrue(process.is_running())
            self.assertEqual(start_worker(service),{'status':'already_running','pid':started['pid']})
            duplicate=subprocess.run([sys.executable,'-m','research_automation','--root',str(self.root),'worker','--once'],capture_output=True,text=True,encoding='utf-8',timeout=15)
            self.assertNotEqual(duplicate.returncode,0)
            self.assertIn('already active',duplicate.stderr)
            service.stop_worker()
            process.wait(timeout=15)
            self.assertEqual(service.store.get('runtime','worker')['status'],'STOPPED')
        finally:
            if process and process.is_running():
                from research_automation.agent import terminate_tree
                terminate_tree(process)
            from research_automation.cli import _background_processes
            for child in _background_processes:
                child.wait(timeout=10)
            service.close()


if __name__=='__main__':
    unittest.main()
