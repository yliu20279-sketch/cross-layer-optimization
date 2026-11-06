"""Bounded metadata-only search; never downloads or loads tensor values."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('roots', nargs='+')
    parser.add_argument('--seconds', type=int, default=30)
    parser.add_argument('--directories', type=int, default=100000)
    parser.add_argument('--skip-experiment-results', action='store_true')
    args = parser.parse_args()
    start = time.monotonic()
    visited, config_count, errors, candidates = 0, 0, [], []
    pruned = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'blobs'}
    if args.skip_experiment_results:
        pruned.update({'results', 'runs', 'safe_review', 'logs', 'epochs', 'epoch', 'traces'})
    status = 'EXHAUSTED_SELECTED_ROOTS'
    for top in args.roots:
        if not Path(top).exists():
            errors.append({'root': top, 'status': 'MISSING_ROOT'})
            continue
        for directory, dirs, files in os.walk(top, followlinks=False,
                                               onerror=lambda error: errors.append({'error': str(error)})):
            visited += 1
            dirs[:] = [x for x in dirs if x not in pruned and not x.startswith('sealed_')]
            if visited > args.directories or time.monotonic() - start > args.seconds:
                status = 'LIMIT_REACHED'
                break
            if 'config.json' not in files:
                continue
            path = Path(directory) / 'config.json'
            if path.stat().st_size > 2 * 1024**2:
                continue
            config_count += 1
            try:
                raw = path.read_bytes()
                config = json.loads(raw)
                if not isinstance(config, dict) or config.get('num_hidden_layers') != 24 or config.get('num_experts') != 60:
                    continue
                lower = str(path).lower()
                quant = config.get('quantization_config')
                dtype = config.get('torch_dtype', config.get('dtype'))
                excluded = bool(quant) or 'chat' in lower or 'gptq' in lower
                checkpoint_files = [name for name in files if name.endswith('.safetensors') or name in ('pytorch_model.bin',)]
                actual = []
                for name in checkpoint_files:
                    p = Path(directory) / name
                    with p.open('rb') as handle:
                        prefix = handle.read(64)
                    actual.append({'name': name, 'bytes': p.stat().st_size,
                                   'lfs_pointer': prefix.startswith(b'version https://git-lfs.github.com/spec/v1')})
                candidates.append({'config': str(path), 'config_sha256': hashlib.sha256(raw).hexdigest(),
                                   'dtype': dtype, 'quantized': bool(quant),
                                   'excluded_chat_or_quantized': excluded,
                                   'classification': 'EXCLUDED_VARIANT' if excluded else 'UNVERIFIED_ORIGINAL_CANDIDATE',
                                   'checkpoint_files': actual,
                                   'tokenizer_present': (Path(directory) / 'tokenizer.json').is_file(),
                                   'note': 'config shape alone does not prove checkpoint identity'})
            except (OSError, ValueError) as error:
                errors.append({'path': str(path), 'error': str(error)})
        if status == 'LIMIT_REACHED':
            break
    print(json.dumps({'status': status, 'roots': args.roots, 'visited_directories': visited,
                      'configs_read': config_count, 'elapsed_seconds': time.monotonic() - start,
                      'limits': {'seconds': args.seconds, 'directories': args.directories},
                      'pruned': sorted(pruned) + ['sealed_*', 'symlink directories'],
                      'candidates': candidates, 'errors': errors,
                      'downloads': 0, 'model_runs': 0}, ensure_ascii=True))


if __name__ == '__main__':
    main()
