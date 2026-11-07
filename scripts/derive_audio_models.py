#!/usr/bin/env python3
"""Reproduce pinned local model derivations; source weights stay unchanged."""
import hashlib
from pathlib import Path
from bootstrap_models import ROOT,sha256


def derive(item):
    spec=item['derivation']
    source=(ROOT/spec['input']).resolve();output=(ROOT/item['path']).resolve()
    for p in (source,output):
        if not p.is_relative_to(ROOT) or p.is_relative_to(ROOT/'task'):raise ValueError('Invalid derivation path')
    if sha256(source)!=spec['input_sha256']:raise ValueError('Invalid derivation source')
    if source==output:raise ValueError('Derivation cannot overwrite its source')
    if spec['kind']=='ort-matmul-dynamic-int8-v1':
        import tempfile
        import onnx
        import onnxruntime
        from onnxruntime.quantization import quantize_dynamic,QuantType
        if onnx.__version__!=spec['onnx_version'] or onnxruntime.__version__!=spec['ort_version']:
            raise ValueError('Unexpected ONNX/ORT quantizer versions')
        output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent) as temp:
            temporary=Path(temp)/'model.onnx'
            quantize_dynamic(source,temporary,op_types_to_quantize=['MatMul'],per_channel=True,
                weight_type=QuantType.QInt8,extra_options={'MatMulConstBOnly':True})
            actual=sha256(temporary)
            if item.get('sha256') and actual!=item['sha256']:raise ValueError('Derived ONNX SHA mismatch')
            temporary.replace(output)
        return dict(sha256=actual,size_bytes=output.stat().st_size)
    if spec['kind']=='llama-q8-to-q4-k-m-v1':
        import subprocess
        import tempfile
        tool=ROOT/'.build/audio/nh-audio-quantize'
        if not tool.exists():raise ValueError('Build the pinned native quantizer with make native-build')
        commit=subprocess.check_output(['git','-C',str(ROOT/'third_party/llama.cpp'),'rev-parse','HEAD'],text=True).strip()
        if commit!=spec['llama_commit']:raise ValueError('Unexpected quantizer runtime source')
        output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent) as temp:
            temporary=Path(temp)/'quantized.gguf'
            subprocess.run([str(tool),str(source),str(temporary),str(spec['threads'])],check=True)
            actual=sha256(temporary)
            if item.get('sha256') and actual!=item['sha256']:raise ValueError('Derived GGUF SHA mismatch')
            temporary.replace(output)
        return dict(sha256=actual,size_bytes=output.stat().st_size,quantizer_sha256=sha256(tool))
    if spec['kind']!='sherpa-gigaam-v3-ctc-metadata-v1':raise ValueError('Unknown model derivation')
    import onnx
    if onnx.__version__!='1.17.0':raise ValueError('Derivation requires pinned onnx==1.17.0')
    model=onnx.load(source)
    if len(model.graph.input)!=2 or model.graph.input[0].type.tensor_type.shape.dim[1].dim_value!=64:
        raise ValueError('Unexpected GigaAM feature inputs')
    def tensor_hash():
        h=hashlib.sha256()
        for tensor in model.graph.initializer:h.update(tensor.SerializeToString(deterministic=True))
        return h.hexdigest()
    weights=tensor_hash()
    del model.metadata_props[:]
    metadata=dict(vocab_size=34,normalize_type='',subsampling_factor=4,model_type='EncDecCTCModel',version=1,
        model_author='https://github.com/salute-developers/GigaAM',
        license='https://github.com/salute-developers/GigaAM/blob/main/LICENSE',language='Russian',comment='v3',is_giga_am=1)
    for key,value in metadata.items():
        prop=model.metadata_props.add();prop.key=key;prop.value=str(value)
    if tensor_hash()!=weights:raise AssertionError('Metadata adaptation changed model weights')
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_suffix('.part')
    temporary.write_bytes(model.SerializeToString(deterministic=True))
    actual=sha256(temporary)
    if item.get('sha256') and actual!=item['sha256']:raise ValueError('Derived model SHA mismatch')
    temporary.replace(output)
    return dict(sha256=actual,size_bytes=output.stat().st_size,initializer_sha256=weights)
