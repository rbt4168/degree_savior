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
from research_automation.hypothesis import validate_plan
from research_automation.literature import validate_note, validate_pdf
from research_automation.service import Service
from research_automation.store import Store

from fixtures import Agent, Sources, PAPER_TEXT, pdf_bytes, plan_fixture


class Response(io.BytesIO):
    headers = {}


class RuntimeTests(unittest.TestCase):
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
        self.store.put('example','id',{'status':'done'},'example.completed','Saved','once')
        event = self.store.event('example.completed',{'summary':'duplicate'},'once')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],1)
        self.assertEqual(self.store.pending_count(),1)
        self.assertEqual(self.store.get('example','id')['status'],'done')

    def test_event_splits_unicode_with_mentions_disabled(self):
        self.store.event('long.completed',{'summary':'😀'*2500})
        rows = self.store.db.execute('SELECT payload FROM outbox').fetchall()
        self.assertGreater(len(rows),1)
        for row in rows:
            data = json.loads(row['payload'])
            self.assertIn('embeds',data)
            self.assertNotIn('content',data)
            self.assertLessEqual(len(data['embeds'][0]['description'].encode('utf-16-le'))//2,4096)
        self.assertEqual(data['allowed_mentions'],{'parse':[]})

    def test_confirmed_delivery_is_recorded_and_not_resent(self):
        self.store.event('test.saved',{'summary':'Synthetic notification fixture'})
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

    def test_rate_limit_persists_server_retry_and_survives_restart(self):
        self.store.event('test.saved',{'summary':'Synthetic notification fixture'})
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
        self.store.event('test.saved',{'summary':'Synthetic notification fixture'})
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
        self.store.event('test.saved',{'summary':'Synthetic notification fixture'})
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

    def test_result_notification_is_chinese_embed_with_report_attachment(self):
        (self.root/'results').mkdir()
        (self.root/'results/fixture.md').write_text('繁體中文附件測試；這不是研究成果。',encoding='utf-8')
        self.store.event('campaign.result',{'result':'results/fixture.md','outcomes':{'SUPPORTED':0,'NOT_SUPPORTED':1},'question':'合成測試問題'})
        captured=[]
        def opener(request,timeout):
            captured.append(request)
            return Response(b'{"id":"fixture-attachment"}')
        self.assertEqual(Notifier(self.store,opener).flush(),1)
        request=captured[0]
        self.assertIn('multipart/form-data',request.get_header('Content-type'))
        body=request.data.decode('utf-8')
        self.assertIn('完整研究結果已儲存',body)
        self.assertIn('假設未獲支持',body)
        self.assertIn('繁體中文附件測試',body)
        self.assertNotIn('_attachment',body)

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
