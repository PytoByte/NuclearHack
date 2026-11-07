#!/usr/bin/env python3
"""Run a finite, reviewable research queue serially; never overwrite completed runs."""
import argparse
import json
import re
import shutil
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('queue',type=Path);args=p.parse_args()
    jobs=json.loads(args.queue.read_text())
    for job in jobs:
        eid=job['experiment']
        if not re.fullmatch(r'exp_[0-9]+',eid):raise ValueError('Queue experiment must be exp_NNNN')
        out=ROOT/'.audio-runs'/eid
        if out.exists():
            if (out/'failure.json').exists() or (out/'invalidity.json').exists():raise SystemExit(eid+': failed/invalid run exists; allocate a new ID')
            if (out/'metrics.json').exists() or (out/'scored-metrics.json').exists():
                print(eid+': already completed, preserved',flush=True);continue
            raise SystemExit(eid+': partial/failed run exists; inspect it and allocate a new ID')
        script=(ROOT/job['script']).resolve()
        if not script.is_relative_to(ROOT/'eval/scripts') or script.suffix!='.py':
            raise ValueError('Queue scripts must be local research tools')
        command=[sys.executable,str(script),'--experiment',eid,*job.get('args',[])]
        print(json.dumps(dict(experiment=eid,hypothesis=job['hypothesis'],command=command)),flush=True)
        dispatch=ROOT/'.audio-runs/dispatch';dispatch.mkdir(parents=True,exist_ok=True)
        stdout_path=dispatch/(eid+'.stdout.log');stderr_path=dispatch/(eid+'.stderr.log')
        with stdout_path.open('x') as stdout,stderr_path.open('x') as stderr:
            result=subprocess.run(command,cwd=ROOT,stdout=stdout,stderr=stderr)
        out.mkdir(parents=True,exist_ok=True)
        for source,name in [(stdout_path,'dispatch.stdout.log'),(stderr_path,'dispatch.stderr.log')]:
            shutil.copyfile(source,out/name)
        completed=(out/'metrics.json').exists() or (out/'scored-metrics.json').exists()
        if result.returncode or not completed:
            if not (out/'config.json').exists():(out/'config.json').write_text(json.dumps(dict(experiment_id=eid,script=job['script'],args=job.get('args',[]),hypothesis=job['hypothesis']),indent=2))
            if not (out/'failure.json').exists():(out/'failure.json').write_text(json.dumps(dict(stage='research_dispatch' if result.returncode else 'missing_results',exit_code=result.returncode,command=command,logs=['dispatch.stdout.log','dispatch.stderr.log']),indent=2))
            report=ROOT/'eval/results'/eid;report.mkdir(parents=True,exist_ok=True)
            for name in ['config.json','environment.json','failure.json']:
                if (out/name).exists() and not (report/name).exists():shutil.copyfile(out/name,report/name)
            raise SystemExit(f'{eid}: failed (exit {result.returncode}, completed metrics {completed}); logs/config/failure preserved, allocate a new ID')
    print('Finite queue complete; review metrics before selecting next hypotheses',flush=True)


if __name__=='__main__':main()
