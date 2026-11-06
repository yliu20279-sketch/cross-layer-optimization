"""CPU-only bounded-memory decoded FP16 artifacts; old layer0 tensors reused.

Does not import torch, run inference, use CUDA, or launch a simulator.
Run only in a fresh isolated directory. All outputs are target assets, not a
Hugging Face ready-to-load model; layouts and source byte spans are explicit.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.gptq import decode, independent_decode
from core.common import require, digest

DTYPES = {'I32': '<i4', 'F16': '<f2', 'F32': '<f4', 'BF16': '<u2'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(4 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def finite_array_hash(array):
    flat = array.reshape(-1)
    h = hashlib.sha256()
    for begin in range(0, flat.size, 1024 * 1024):
        chunk = flat[begin:begin + 1024 * 1024]
        require(np.isfinite(chunk).all(), 'nonfinite dense tensor')
        h.update(chunk.tobytes())
    return h.hexdigest()


def save(path, value):
    tmp = path.with_name(path.name + '.writing')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(str(tmp), str(path))


def header(path):
    with Path(path).open('rb') as handle:
        n = int.from_bytes(handle.read(8), 'little')
        require(0 < n < 20000000, 'invalid safetensors header')
        raw = handle.read(n)
    return n + 8, json.loads(raw), hashlib.sha256(raw).hexdigest()


class Tensor:
    def __init__(self, path, name):
        base, head, h = header(path)
        value = head[name]
        self.path, self.name, self.value, self.header_sha256 = Path(path), name, value, h
        self.offset = base + value['data_offsets'][0]
        self.array = np.memmap(str(path), dtype=DTYPES[value['dtype']], mode='r',
                               offset=self.offset, shape=tuple(value['shape']))

    def part(self):
        return {'file': str(self.path), 'tensor': self.name, 'offset': self.offset,
                'dtype': self.value['dtype'], 'shape': self.value['shape'],
                'bytes': self.value['data_offsets'][1] - self.value['data_offsets'][0],
                'container': 'safetensors', 'header_sha256': self.header_sha256}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--old-materialized', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    source, old, out = Path(args.source), Path(args.old_materialized), Path(args.out)
    require(not out.exists(), 'output exists; refuse overwrite')
    require(shutil.disk_usage(out.parent).free > 64 * 1024**3, 'need 64GiB free before materialization')
    out.mkdir()
    (out / 'weights').mkdir()
    start = time.monotonic()
    save(out / 'CONTRACT.json', {'source_model': 'Qwen/Qwen1.5-MoE-A2.7B-Chat-GPTQ-Int4',
         'target': 'GPTQ-decoded-FP16', 'source_quantization': 'legacy GPTQ4 group128',
         'execution_dtype': 'F16', 'projection_layout': 'input-major K,N',
         'dense_layout': 'source row-major, explicitly preserved',
         'runtime_unpack_ops': 0, 'runtime_packed_reads': 0,
         'source_packed_storage_is_archival': True, 'full_model_forward': False,
         'offline_conversion_wall_seconds_not_simulator_ticks': True})
    config = json.loads((source / 'config.json').read_text())
    require(config.get('quantization_config', {}).get('bits') == 4 and
            config['quantization_config']['group_size'] == 128 and
            config['num_hidden_layers'] == 24 and config['num_experts'] == 60, 'wrong checkpoint')
    files = sorted(source.glob('*.safetensors'))
    table, source_headers = {}, []
    for path in files:
        _, head, h = header(path)
        source_headers.append({'file': str(path), 'bytes': path.stat().st_size, 'header_sha256': h})
        for name in head:
            if name != '__metadata__':
                require(name not in table, 'duplicate source tensor')
                table[name] = path
    old_manifest = json.loads((old / 'weight_manifest.json').read_text())
    old_checks = []
    for row in old_manifest:
        value = sha(row['file'])
        require(value == row['sha256'], 'old layer0 file changed')
        old_checks.append({'file': row['file'], 'sha256': value})
    save(out / 'OLD_LAYER0_REUSE.json', old_checks)
    prefixes = sorted(name[:-len('.qweight')] for name in table if name.endswith('.qweight'))
    require(len(prefixes) == 4488, 'unexpected projection count')
    manifest, decode_checks = [], []
    reused, copied, output_bytes = 0, 0, 0
    consumed = set()
    for number, prefix in enumerate(prefixes):
        fields = {suffix: Tensor(table[prefix + '.' + suffix], prefix + '.' + suffix)
                  for suffix in ('qweight', 'qzeros', 'scales', 'g_idx', 'bias')}
        for suffix in fields:
            consumed.add(prefix + '.' + suffix)
        arrays = [fields[x].array for x in ('qweight', 'qzeros', 'scales', 'g_idx')]
        weight = decode(*arrays)
        reference = independent_decode(*arrays)
        require(np.array_equal(weight.view(np.uint16), reference.view(np.uint16)), 'independent decode mismatch')
        payload_hash = hashlib.sha256(weight.tobytes()).hexdigest()
        parts = []
        reuse_kind = None
        if prefix.startswith('model.layers.0.mlp.experts.'):
            expert, projection = prefix.split('.')[-2:]
            tensor = Tensor(old / 'weights' / ('expert_%03d.safetensors' % int(expert)), projection)
            require(tensor.array.shape == weight.shape and
                    np.array_equal(tensor.array.view(np.uint16), weight.view(np.uint16)), 'old expert differs')
            parts = [tensor.part()]
            reuse_kind = 'old_layer0_expert_exact'
        elif prefix.startswith('model.layers.0.mlp.shared_expert.'):
            projection = prefix.rsplit('.', 1)[1]
            tensors = [Tensor(old / 'weights' / ('shared_rank%d.safetensors' % rank), projection) for rank in range(4)]
            axis = 0 if projection == 'down_proj' else 1
            joined = np.concatenate([tensor.array for tensor in tensors], axis=axis)
            require(np.array_equal(joined.view(np.uint16), weight.view(np.uint16)), 'old shared parts differ')
            parts = [dict(tensor.part(), concat_axis=axis, tp_rank=rank) for rank, tensor in enumerate(tensors)]
            reuse_kind = 'old_layer0_shared_TP4_exact'
        else:
            path = out / 'weights' / ('projection_%04d.f16' % number)
            with path.open('xb') as handle:
                handle.write(weight.tobytes())
            require(sha(path) == payload_hash, 'persisted decode differs')
            parts = [{'file': str(path), 'offset': 0, 'dtype': 'F16', 'shape': list(weight.shape),
                      'bytes': weight.nbytes, 'container': 'raw_fp16', 'sha256': payload_hash}]
        reused += int(reuse_kind is not None)
        copied += int(reuse_kind is None)
        manifest.append({'name': prefix + '.weight', 'dtype': 'F16', 'shape': list(weight.shape),
                         'layout': 'input_major', 'bytes': weight.nbytes, 'payload_sha256': payload_hash,
                         'parts': parts, 'reuse': reuse_kind, 'runtime_quantized': False})
        output_bytes += weight.nbytes
        bias = np.asarray(fields['bias'].array)
        require(bias.dtype == np.float16 and np.isfinite(bias).all(), 'invalid GPTQ bias')
        if np.any(bias != 0):
            manifest.append({'name': prefix + '.bias', 'dtype': 'F16', 'shape': list(bias.shape),
                             'layout': 'source', 'bytes': bias.nbytes, 'parts': [fields['bias'].part()],
                             'payload_sha256': hashlib.sha256(bias.tobytes()).hexdigest()})
            output_bytes += bias.nbytes
        decode_checks.append({'projection': prefix, 'elements': int(weight.size), 'exact_independent': True,
                              'reuse': reuse_kind, 'bias_nonzero': int(np.count_nonzero(bias)),
                              'decoded_payload_sha256': payload_hash})
        if number % 50 == 0 or number + 1 == len(prefixes):
            save(out / 'PROGRESS.json', {'completed': number + 1, 'total': len(prefixes),
                 'reused': reused, 'new_files': copied, 'elapsed_seconds': time.monotonic() - start})
            print('DECODE %d/%d reused=%d' % (number + 1, len(prefixes), reused), flush=True)
    for name in sorted(set(table) - consumed):
        tensor = Tensor(table[name], name)
        require(tensor.value['dtype'] == 'F16', 'unexpected unquantized dtype')
        # Keep exact FP16 source spans. Packed tensors in the same archive are
        # not runtime objects and are never charged as FP16 execution operands.
        value = tensor.array
        payload_sha256 = finite_array_hash(value)
        manifest.append({'name': name, 'dtype': 'F16', 'shape': list(value.shape), 'layout': 'source',
                         'bytes': value.nbytes, 'parts': [tensor.part()],
                         'payload_sha256': payload_sha256,
                         'runtime_quantized': False})
        output_bytes += value.nbytes
    save(out / 'TARGET_MANIFEST.json', manifest)
    save(out / 'DECODE_CHECKS.json', decode_checks)
    metadata = []
    for name in ['config.json', 'tokenizer.json', 'tokenizer_config.json', 'model.safetensors.index.json']:
        path = source / name
        if path.is_file():
            metadata.append({'file': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)})
    source_hashes = [{'file': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in files]
    save(out / 'SOURCE_IDENTITY.json', {'files': source_hashes, 'metadata': metadata,
         'source_headers': source_headers, 'content_snapshot_sha256': digest(source_hashes + metadata)})
    save(out / 'COMPLETE.json', {'status': 'PASS_ALL_PROJECTION_DECODE_AND_PERSISTENCE_SCOPED',
         'projections': len(prefixes), 'independent_checks': len(decode_checks),
         'reused_projection_tensors': reused, 'new_projection_files': copied,
         'target_objects': len(manifest), 'target_valid_bytes': output_bytes,
         'target_manifest_sha256': sha(out / 'TARGET_MANIFEST.json'),
         'zero_bias_projections': sum(x['bias_nonzero'] == 0 for x in decode_checks),
         'elapsed_seconds': time.monotonic() - start, 'full_model_forward': False,
         'gpu_runs': 0, 'native_simulations': 0})
    print(json.dumps(json.loads((out / 'COMPLETE.json').read_text())), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Preserve any partial outputs; never overwrite/retry silently.
        print('FAILED: ' + repr(error), file=sys.stderr)
        raise
