"""The device sampler must preserve process failures and write valid memory JSON."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from probe_stream_cli import device_script


class Sampler(unittest.TestCase):
    def run_child(self, command):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        script = device_script(command, str(directory))
        process = subprocess.run(['sh', '-c', script], capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, int((directory/'exit-code').read_text()))
        self.assertTrue((directory/'pid').read_text().strip().isdigit())
        return directory, process

    def test_success_produces_parseable_positive_samples(self):
        directory, process = self.run_child(['sleep', '.3'])
        self.assertEqual(process.returncode, 0)
        samples = list(map(json.loads, (directory/'memory.jsonl').read_text().splitlines()))
        self.assertTrue(samples)
        self.assertTrue(all(s['pss_kib']>0 and s['rss_kib']>=s['pss_kib'] for s in samples))

    def test_immediate_failure_retains_empty_memory_file_and_error(self):
        directory, process = self.run_child(['sh', '-c', 'echo sentinel >&2; exit 7'])
        self.assertEqual(process.returncode, 7)
        self.assertTrue((directory/'memory.jsonl').exists())
        self.assertIn('sentinel', (directory/'stderr.log').read_text())


if __name__ == '__main__':
    unittest.main()
