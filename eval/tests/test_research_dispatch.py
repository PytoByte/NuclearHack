"""The research dispatcher must retain failures and never replay partial IDs."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/run_research_queue.py'
spec=importlib.util.spec_from_file_location('research_dispatch',SCRIPT)
dispatch=importlib.util.module_from_spec(spec);spec.loader.exec_module(dispatch)

class ResearchDispatch(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'eval/scripts').mkdir(parents=True)
        self.queue=self.root/'queue.json'
    def run_job(self,body):
        (self.root/'eval/scripts/job.py').write_text(body)
        self.queue.write_text(json.dumps([dict(experiment='exp_0001',script='eval/scripts/job.py',args=[],hypothesis='test artifact lifecycle')]))
        with patch.object(dispatch,'ROOT',self.root),patch.object(sys,'argv',['queue',str(self.queue)]):dispatch.main()
    def test_failure_logs_config_and_replay_are_preserved(self):
        with self.assertRaises(SystemExit):self.run_job("print('partial observation'); raise SystemExit(7)")
        out=self.root/'.audio-runs/exp_0001'
        self.assertEqual(json.loads((out/'failure.json').read_text())['exit_code'],7)
        self.assertIn('partial observation',(out/'dispatch.stdout.log').read_text())
        self.assertTrue((self.root/'eval/results/exp_0001/config.json').exists())
        original=(out/'dispatch.stdout.log').read_bytes()
        with self.assertRaises(SystemExit):self.run_job("raise AssertionError('must not execute')")
        self.assertEqual((out/'dispatch.stdout.log').read_bytes(),original)
    def test_zero_exit_without_metrics_is_not_completion(self):
        with self.assertRaises(SystemExit):self.run_job("print('preparation only')")
        out=self.root/'.audio-runs/exp_0001'
        self.assertEqual(json.loads((out/'failure.json').read_text())['stage'],'missing_results')
    def test_completed_observations_are_not_overwritten(self):
        body="from pathlib import Path\np=Path(__file__).resolve().parents[2]/'.audio-runs/exp_0001'\np.mkdir(parents=True)\n(p/'metrics.json').write_text('{}')\nprint('complete')"
        self.run_job(body)
        log=self.root/'.audio-runs/exp_0001/dispatch.stdout.log';original=log.read_bytes()
        self.run_job("raise AssertionError('must not execute')")
        self.assertEqual(log.read_bytes(),original)

if __name__=='__main__':unittest.main()
