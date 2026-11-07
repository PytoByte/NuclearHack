#!/usr/bin/env python3
"""Isolated Torch worker; no SDK or scoring dependency in reference env."""
import importlib.util
import json
from pathlib import Path
import sys
import time
import numpy as np
ROOT = Path(__file__).resolve().parents[2]


def worker(path):
    import torch
    torch.set_num_threads(4); torch.set_num_interop_threads(1); torch.manual_seed(0)
    spec = importlib.util.spec_from_file_location('pinned_nmesc', ROOT/'.tools/research/nmesc/offline_clustering.py')
    mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    vectors = np.load(path); n = len(vectors)
    began = time.perf_counter()
    engine = mod.SpeakerClustering(cuda=False, parallelism=False)
    result = engine.forward_infer(torch.from_numpy(vectors),
        torch.tensor([[float(i),float(i+1)] for i in range(n)]),
        torch.tensor([n]),torch.tensor([[1.]]),oracle_num_speakers=-1)
    print(json.dumps(dict(labels=result.tolist(), clustering_seconds=time.perf_counter()-began,
                          torch_version=torch.__version__, oracle_num_speakers=-1)), flush=True)


if __name__ == "__main__": worker(sys.argv[1])
