#!/usr/bin/env python3
"""Run a finite, reviewable research queue serially; never overwrite completed runs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('queue',type=Path);args=p.parse_args()
    jobs=json.loads(args.queue.read_text())
    for job in jobs:
        eid=job['experiment'];out=ROOT/'.audio-runs'/eid
        if out.exists():
            if (out/'metrics.json').exists() or (out/'scored-metrics.json').exists():
                print(eid+': already completed, preserved',flush=True);continue
            raise SystemExit(eid+': partial/failed run exists; inspect it and allocate a new ID')
        script=(ROOT/job['script']).resolve()
        if not script.is_relative_to(ROOT/'eval/scripts') or script.suffix!='.py':
            raise ValueError('Queue scripts must be local research tools')
        command=[sys.executable,str(script),'--experiment',eid,*job.get('args',[])]
        print(json.dumps(dict(experiment=eid,hypothesis=job['hypothesis'],command=command)),flush=True)
        result=subprocess.run(command,cwd=ROOT)
        if result.returncode:raise SystemExit(f'{eid}: failed ({result.returncode}); old artifacts preserved')
    print('Finite queue complete; review metrics before selecting next hypotheses',flush=True)


if __name__=='__main__':main()
