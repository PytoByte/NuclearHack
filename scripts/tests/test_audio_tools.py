import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('audio_tools', Path(__file__).parents[1] / 'audio_tools.py')
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


class Contracts(unittest.TestCase):
    def turn(self, **changes):
        return dict(speaker_id='speaker_1', start_ms=0, end_ms=1000, text='Да.\n«Ещё»', **changes)

    def test_empty_and_overlapping_transcripts(self):
        tools.transcript({'transcript': []})
        a = self.turn()
        b = dict(a, speaker_id='speaker_2', start_ms=500)
        tools.transcript({'transcript': [a, b]})

    def test_invalid_exports(self):
        a = self.turn()
        for bad in (dict(a, start_ms=True), dict(a, start_ms=-1), dict(a, end_ms=0),
                    dict(a, end_ms=1.5), dict(a, speaker_id=None), dict(a, text=12),
                    dict(a, summary='extra')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                tools.transcript({'transcript': [bad]})
        with self.assertRaises(ValueError):
            tools.transcript({'transcript': [dict(a, start_ms=500), a]})

    def test_task_path_boundaries(self):
        self.assertEqual(tools.protected(['task/a', 'task', 'tasks/a', 'docs/task/a']), ['task/a', 'task'])

    def test_strict_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'export.json'
            for invalid in ('{"transcript": [], "transcript": []}', '{"transcript": NaN}'):
                path.write_text(invalid)
                with self.assertRaises(ValueError):
                    tools.load_json(path)

    def test_staged_task_change_blocks_commit(self):
        with patch.object(tools, 'git', return_value=b'task/task.md\0'):
            with self.assertRaisesRegex(ValueError, 'read-only'):
                tools.check(True)

    def test_staged_manifest_is_checked_from_index(self):
        manifest = b'<manifest xmlns:android="http://schemas.android.com/apk/res/android"><uses-permission android:name="android.permission.INTERNET"/></manifest>'
        with patch.object(tools, 'git', side_effect=[b'', b'src/app/AndroidManifest.xml\0', manifest]):
            with self.assertRaisesRegex(ValueError, 'INTERNET'):
                tools.check(True)

    def test_model_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'model').write_bytes(b'weights')
            manifest = root / 'manifest.json'
            item = dict(path='model', source='test fixture', version='test', license='test',
                        sha256=tools.hashlib.sha256(b'weights').hexdigest())
            manifest.write_text(json.dumps({'files': [item]}))
            with patch.object(tools, 'ROOT', root):
                tools.models(manifest)
                (root / 'model').write_bytes(b'corrupt')
                with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                    tools.models(manifest)


if __name__ == '__main__':
    unittest.main()
