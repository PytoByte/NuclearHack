#!/usr/bin/env python3
"""Run a finite, reviewable research queue serially; never overwrite completed runs."""
import argparse
import json
import re
import shutil
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def environment():
    def git(*args):
        result=subprocess.run(['git','-C',str(ROOT),*args],capture_output=True,text=True)
        return result.stdout.strip() if result.returncode==0 else None
    cpu_model=None
    cpuinfo=Path('/proc/cpuinfo')
    if cpuinfo.exists():
        cpu_model=next((line.split(':',1)[1].strip() for line in cpuinfo.read_text().splitlines() if line.startswith('model name')),None)
    return dict(captured_at_utc=datetime.now(timezone.utc).isoformat(),git_sha=git('rev-parse','HEAD'),
        git_dirty=bool(git('status','--porcelain')),host=platform.platform(),machine=platform.machine(),
        cpu_model=cpu_model,logical_cpus=os.cpu_count(),python=sys.version,executable=sys.executable,
        cpu_affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
        thread_environment={k:os.environ[k] for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'] if k in os.environ})


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
        env_path=dispatch/(eid+'.environment.json')
        with env_path.open('x') as stream:json.dump(environment(),stream,indent=2)
        with stdout_path.open('x') as stdout,stderr_path.open('x') as stderr:
            result=subprocess.run(command,cwd=ROOT,stdout=stdout,stderr=stderr)
        out.mkdir(parents=True,exist_ok=True)
        for source,name in [(stdout_path,'dispatch.stdout.log'),(stderr_path,'dispatch.stderr.log')]:
            shutil.copyfile(source,out/name)
        report=ROOT/'eval/results'/eid;report.mkdir(parents=True,exist_ok=True)
        for directory in [out,report]:
            with (directory/'dispatch-environment.json').open('x') as stream:stream.write(env_path.read_text())
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
