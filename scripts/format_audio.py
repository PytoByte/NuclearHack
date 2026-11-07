#!/usr/bin/env python3
"""Apply/check the pinned native style; staged checks read Git blobs verbatim."""
import argparse
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/audio'
EXTENSIONS={'.c','.h','.cpp','.hpp'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--staged',action='store_true')
    args=parser.parse_args()
    if args.staged and not args.check:parser.error('--staged requires --check')
    formatter=ROOT/'.venv/bin/clang-format'
    if args.staged:
        names=subprocess.check_output(['git','diff','--cached','--name-only','--diff-filter=ACMR','-z','--','src/audio'],cwd=ROOT).decode().split('\0')
        paths=[ROOT/name for name in names if name and Path(name).suffix in EXTENSIONS]
    else:paths=sorted(p for p in SOURCE.rglob('*') if p.suffix in EXTENSIONS and p.is_file())
    if not paths:return
    if not formatter.is_file():raise SystemExit('Install pinned native formatter: uv sync --frozen')
    for path in paths:
        if not path.resolve().is_relative_to(SOURCE):raise ValueError('Native formatting path outside module')
        if args.staged:
            content=subprocess.check_output(['git','show',':'+str(path.relative_to(ROOT))],cwd=ROOT)
            subprocess.run([str(formatter),'--dry-run','--Werror','--assume-filename='+str(path)],input=content,check=True,cwd=ROOT)
        else:
            subprocess.run([str(formatter),*(['--dry-run','--Werror'] if args.check else ['-i']),str(path)],check=True,cwd=ROOT)
    print(f'Native style {"checked" if args.check else "formatted"}: {len(paths)} files')


if __name__=='__main__':main()
