import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import load_secrets as loader


class LoaderTests(unittest.TestCase):
    def test_three_keys(self):
        mappings = loader.parse_mappings('username: DB_USERNAME\npassword: DB_PASSWORD\nhost: DB_HOST')
        vault = {'secrets': [{'key': key, 'value': key + '-value'} for key, _ in mappings]}
        self.assertEqual(loader.select_values(vault, mappings), [
            (name, key + '-value') for key, name in mappings])

    def test_invalid_mappings(self):
        for raw in ('', 'username', 'a: X\nb: x', 'a: GITHUB_ENV', 'a: PATH', 'a: BASH_ENV'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                loader.parse_mappings(raw)

    def test_missing_duplicate_and_non_string(self):
        for secrets in ([], [{'key': 'a', 'value': '1'}] * 2, [{'key': 'a', 'value': None}]):
            with self.assertRaises(ValueError):
                loader.select_values({'secrets': secrets}, [('a', 'A')])

    def test_request_and_multiline_export(self):
        vault = {'krn': 'krn:test', 'secrets': [{'key': 'a', 'value': 'first\nsecond%'}]}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'env'
            env = {'KV_TOKEN': 'Bearer test-token', 'KV_URL': 'https://vault.example.com',
                   'KV_KRN': 'krn:test', 'KV_SECRETS': 'a: VALUE', 'GITHUB_ENV': str(output)}
            with patch.dict(os.environ, env), patch.object(loader, 'build_opener') as opener:
                opener.return_value.open.return_value = contextlib.closing(io.StringIO(json.dumps(vault)))
                log = io.StringIO()
                with contextlib.redirect_stdout(log):
                    loader.main()
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(request.full_url, 'https://vault.example.com/vault-app/vaults/integration/GITHUB_ACTIONS')
                self.assertEqual(dict((k.lower(), v) for k, v in request.header_items())['kubbeeaccesstoken'], 'Bearer test-token')
                self.assertEqual(dict((k.lower(), v) for k, v in request.header_items())['kubbeevaultkrn'], 'krn:test')
                lines = output.read_text().splitlines()
                self.assertEqual(lines[0].split('<<')[1], lines[-1])
                self.assertEqual(lines[1:-1], ['first', 'second%'])
                self.assertIn('::add-mask::first%0Asecond%25', log.getvalue())

    def test_missing_key_does_not_export(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'env'
            env = {'KV_TOKEN': 'test-token', 'KV_URL': 'https://vault.example.com',
                   'KV_KRN': 'krn:test', 'KV_SECRETS': 'a: A\nb: B', 'GITHUB_ENV': str(output)}
            vault = {'krn': 'krn:test', 'secrets': [{'key': 'a', 'value': 'secret'}]}
            with patch.dict(os.environ, env), patch.object(loader, 'build_opener') as opener:
                opener.return_value.open.return_value = contextlib.closing(io.StringIO(json.dumps(vault)))
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                    loader.main()
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
