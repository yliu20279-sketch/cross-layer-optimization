"""Read-only 113 evidence audit. Pipe to python3 -; never imports project code."""
from pathlib import Path
import hashlib
import json
import time
import datetime

BASE = Path('/mnt/sda1/h3240101068')
Q15 = Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/qwen1_5_moe_a2_7b_v3_6/memory_bank_completion_v1')
started = time.monotonic()
budget = 512 * 1024**2
used = 0
cache = {}
checks = []


def hashed(path, expected=None):
    global used
    path = Path(path)
    key = str(path)
    if not path.is_file():
        return {'path': key, 'status': 'MISSING', 'expected': expected}
    if key not in cache:
        size = path.stat().st_size
        if used + size > budget or time.monotonic() - started > 45:
            return {'path': key, 'status': 'DEFERRED_READ_BUDGET', 'bytes': size, 'expected': expected}
        h = hashlib.sha256()
        with path.open('rb') as handle:
            for block in iter(lambda: handle.read(1024**2), b''):
                h.update(block)
        used += size
        cache[key] = (h.hexdigest(), size)
    value, size = cache[key]
    return {'path': key, 'sha256': value, 'bytes': size, 'expected': expected,
            'status': 'MATCH' if expected == value else 'MISMATCH' if expected else 'HASHED_NO_EXPECTED'}


def read(path):
    return json.loads(Path(path).read_text())


manifest_path = Q15 / 'provenance_bundle_v3/evidence_manifest.json'
manifest = read(manifest_path)
expected = {row['path']: row for row in manifest['files']}
checks.append(hashed(manifest_path))
cases = []
for group in ('matrix_full_v2', 'counterfactual_v1'):
    for run in sorted((Q15 / 'results' / group).iterdir()):
        if not run.is_dir() or not (run / 'launch.json').is_file():
            continue
        launch, result = read(run / 'launch.json'), read(run / 'run_manifest.json')
        control = launch.get('controls', {})
        graph = Path(launch.get('graph', control.get('HB_GRAPH', '')))
        meta = read(graph / 'graph_manifest.json')
        case = {'case': run.name, 'group': group, 'cycles': result['total_cycles'],
                'status': result.get('status'), 'completed': result.get('completed'),
                'operations': result.get('operations'), 'causal_violations': result.get('causal_violations'),
                'model': result.get('model'), 'memory_contract': meta.get('memory_contract'),
                'tx_bytes': result.get('architecture_transaction_bytes'),
                'tck_ns': result.get('dram_tck_ns'), 'controls': control,
                'recorded_binary_sha256': launch.get('binary_sha256'),
                'graph': str(graph), 'checks': []}
        # Verify all small identity documents against the prior frozen manifest.
        for path in [run / 'launch.json', run / 'run_manifest.json', run / 'audit.json',
                     graph / 'graph_manifest.json', graph / 'modes.csv',
                     Path(control.get('HB_RAM_CONFIG', '/nonexistent'))]:
            try:
                rel = str(path.relative_to(Q15))
            except ValueError:
                rel = str(path)
            case['checks'].append(hashed(path, expected.get(rel, {}).get('sha256')))
        # run_suite_v2 recorded graph_sha256 from ops.csv, not a whole-DAG hash.
        case['checks'].append(hashed(graph / 'ops.csv', launch.get('graph_sha256')))
        cases.append(case)

# Check binaries/libraries before large logs.
for row in manifest['files']:
    if row.get('role') == 'binary':
        checks.append(hashed(Q15 / row['path'], row['sha256']))

pair_deltas = []
byname = {case['case']: case for case in cases if case['group'] == 'matrix_full_v2'}
for case in cases:
    if case['group'] == 'counterfactual_v1':
        parent = byname.get(case['case'][:-len('_bank_balanced')])
        pair_deltas.append({'case': case['case'], 'paired': parent is not None,
                            'normal_cycles': parent['cycles'] if parent else None,
                            'counterfactual_cycles': case['cycles'],
                            'delta': parent['cycles'] - case['cycles'] if parent else None})

q3 = BASE / 'qwen3_30b_a3b_v3_6_experiment'
# Discover identities entirely from the server's own result directories.
# No local provenance, request data, hashes or metadata are sent to the server.
pair_roots = []
for parent in sorted((q3 / 'results').iterdir()):
    if not parent.is_dir() or not any(s in parent.name for s in ('owner_shadow', 'hsm_cap', 'high_skew_pair')):
        continue
    candidates = [parent] + [p for p in parent.iterdir() if p.is_dir()]
    pair_roots.extend(p for p in candidates if (p / 'normal/validation.json').is_file()
                      and (p / 'oracle/validation.json').is_file())
q3pairs = []
for parent in pair_roots:
    audit_path = parent / 'paired_audit.json'
    if not audit_path.is_file() and (parent.parent / 'paired_audit.json').is_file():
        audit_path = parent.parent / 'paired_audit.json'
    rows = [hashed(audit_path)]
    validation_paths = [parent / mode / 'validation.json' for mode in ('normal', 'oracle')]
    rows.extend(hashed(p) for p in validation_paths)
    endpoints = []
    for val in validation_paths:
        run = val.parent
        if not (run / 'launch.json').is_file() or not (run / 'run_manifest.json').is_file():
            endpoints.append({'run': str(run), 'status': 'MISSING_ENDPOINT_IDENTITY'})
            continue
        launch = read(run / 'launch.json')
        result = read(run / 'run_manifest.json')
        ctl = launch.get('controls', {})
        for name, sha in launch.get('graph_hashes', {}).items():
            rows.append(hashed(Path(ctl['HB_GRAPH']) / name, sha))
        rows.append(hashed(launch['command'][0], launch.get('binary_sha256')))
        rows.append(hashed(ctl['HB_RAM_CONFIG']))
        endpoints.append({'run': str(run), 'cycles': result['total_cycles'],
                          'status': result['status'], 'controls': ctl,
                          'recorded_library_sha256': launch.get('ramulator_library_sha256'),
                          'limitations': launch.get('limitations')})
    q3pairs.append({'case': str(parent.relative_to(q3)), 'checks': rows, 'endpoints': endpoints})

# Old bridge and stage2 evidence are small; do not replay their audit scripts.
other = []
for root, names in [(BASE / 'page_management_stage1_bridge_identity_20261028_v1', ['PLAN.json', 'STATUS.json', 'FREEZE.json']),
                    (BASE / 'page_management_stage2_natural_20261024_v2', ['CODE_FREEZE.json', 'FINAL_STATUS.json', 'FINAL_INTEGRITY.json', 'DSTAR_FREEZE.json'])]:
    for name in names:
        p = root / name
        if p.is_file():
            other.append({'path': str(p), 'hash': hashed(p), 'value': read(p)})

headers = []
checkpoint = Path('/mnt/sda1/models/Qwen3-30B-A3B-modelscope')
for p in sorted(checkpoint.glob('*.safetensors')):
    with p.open('rb') as handle:
        n = int.from_bytes(handle.read(8), 'little')
        if not 0 < n < 20000000:
            raise ValueError('invalid safetensors header')
        raw = handle.read(n)
    header = json.loads(raw)
    headers.append({'file': str(p), 'header_sha256': hashlib.sha256(raw).hexdigest(),
                    'file_bytes': p.stat().st_size, 'tensors': {k: v for k, v in header.items() if k != '__metadata__'}})

print(json.dumps({'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'scope': 'read-only identity/arithmetic; no trace replay or model execution',
                  'read_budget_bytes': budget, 'hashed_bytes': used, 'elapsed_seconds': time.monotonic() - started,
                  'q15_cases': cases, 'q15_pair_deltas': pair_deltas, 'binary_checks': checks,
                  'q3_pairs': q3pairs, 'q3_provenance_origin': 'remote directory discovery only',
                  'other': other, 'q3_tensor_headers': headers,
                  'raw_events_and_bank_payloads_fully_reaudited': False}, ensure_ascii=True))
