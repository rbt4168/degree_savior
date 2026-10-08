import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_automation.common import child_environment, redact
from research_automation.config import secrets
from research_automation.literature import ScholarlySources


class SecretConfigTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name) / 'workspace'
        self.root.mkdir()
        self.local = Path(self.directory.name) / 'secrets.json'
        self.local.write_text(json.dumps({
            'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/123/stored-fixture',
            'OPENALEX_API_KEY': 'stored-fixture-key',
        }), encoding='utf-8')
        self.path_patch = patch('research_automation.config.secret_path', return_value=self.local)
        self.path_patch.start()
        self.env_patch = patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': '', 'OPENALEX_API_KEY': ''})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.path_patch.stop()
        self.directory.cleanup()

    def test_environment_then_workspace_dotenv_then_local_store(self):
        self.root.joinpath('.env').write_text(
            '\ufeffexport DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/456/dotenv-fixture" # comment\n'
            "OPENALEX_API_KEY='dotenv-fixture-key'\nUNRELATED_SETTING=should-not-be-imported\n",
            encoding='utf-8',
        )
        before = dict(os.environ)
        values = secrets(self.root)
        self.assertEqual(values['OPENALEX_API_KEY'], 'dotenv-fixture-key')
        self.assertEqual(values['DISCORD_WEBHOOK_URL'], 'https://discord.com/api/webhooks/456/dotenv-fixture')
        self.assertEqual(os.environ, before)
        with patch.dict(os.environ, {'OPENALEX_API_KEY': 'environment-fixture-key'}):
            self.assertEqual(secrets(self.root)['OPENALEX_API_KEY'], 'environment-fixture-key')
        self.assertNotIn('UNRELATED_SETTING', values)
        self.assertEqual(json.loads(self.local.read_text())['OPENALEX_API_KEY'], 'stored-fixture-key')

    def test_missing_and_blank_dotenv_preserve_local_fallback(self):
        self.assertEqual(secrets(self.root)['OPENALEX_API_KEY'], 'stored-fixture-key')
        self.root.joinpath('.env').write_text('OPENALEX_API_KEY= # empty\nDISCORD_WEBHOOK_URL\n')
        self.assertEqual(secrets(self.root)['OPENALEX_API_KEY'], 'stored-fixture-key')
        self.assertEqual(secrets(self.root)['DISCORD_WEBHOOK_URL'], 'https://discord.com/api/webhooks/123/stored-fixture')

    def test_only_requested_workspace_dotenv_is_loaded(self):
        self.root.parent.joinpath('.env').write_text('OPENALEX_API_KEY=parent-fixture-key\n')
        self.assertEqual(secrets(self.root)['OPENALEX_API_KEY'], 'stored-fixture-key')
        self.root.joinpath('.env').write_text('OPENALEX_API_KEY=workspace-fixture-key\n')
        original = Path.cwd()
        try:
            os.chdir(self.root.parent)
            self.assertEqual(secrets(self.root)['OPENALEX_API_KEY'], 'workspace-fixture-key')
        finally:
            os.chdir(original)

    def test_reloaded_dotenv_keys_are_redacted_and_not_exported_to_children(self):
        path = self.root / '.env'
        path.write_text('OPENALEX_API_KEY=initial-dotenv-fixture-key\n')
        secrets(self.root)
        path.write_text('OPENALEX_API_KEY=replaced-dotenv-fixture-key\n')
        self.assertEqual(secrets(self.root)['OPENALEX_API_KEY'], 'replaced-dotenv-fixture-key')
        self.assertNotIn('initial-dotenv-fixture-key', redact('initial-dotenv-fixture-key'))
        self.assertNotIn('replaced-dotenv-fixture-key', redact('replaced-dotenv-fixture-key'))
        self.assertNotIn('stored-fixture-key', redact('stored-fixture-key'))
        self.assertNotIn('OPENALEX_API_KEY', child_environment())
        self.assertNotIn('DISCORD_WEBHOOK_URL', child_environment())

    def test_openalex_uses_workspace_key_without_putting_it_in_request_url(self):
        self.root.joinpath('.env').write_text('OPENALEX_API_KEY=source-dotenv-fixture-key\n')
        source = ScholarlySources(self.root)
        with patch('research_automation.literature.fetch_json', return_value={'results': []}) as request:
            self.assertEqual(source.search('openalex', 'genetic algorithms'), [])
        args, kwargs = request.call_args
        self.assertNotIn('source-dotenv-fixture-key', args[0])
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer source-dotenv-fixture-key')


if __name__ == '__main__':
    unittest.main()
