"""Portable paths, immutable input checks, and local numeric caches."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import numpy as np
PACKAGE = Path(__file__).resolve().parent.parent
SRC = PACKAGE / 'src'
INPUT = PACKAGE / 'inputs'
RUNTIME = PACKAGE / 'runtime'
VALIDATION = PACKAGE / 'validation'
REFERENCE = PACKAGE / 'reference_results'
RUNS = Path(os.environ.get('THERMAL_RUN_DIR', str(PACKAGE / 'runs'))).expanduser().resolve()
CACHE = PACKAGE / '.cache'
def resolve(path):
    p = Path(path)
    return p if p.is_absolute() else PACKAGE / p
def sha(path):
    return hashlib.sha256(resolve(path).read_bytes()).hexdigest()
def verify_inputs():
    manifest = json.loads((INPUT / 'MANIFEST.json').read_text())
    for name, digest in manifest['sha256'].items():
        assert sha(name) == digest, name
    return manifest
def warm_record(requests=4):
    return json.loads((INPUT / f'warm_{requests}req.json').read_text())
def warm_state(requests=4):
    return np.asarray(warm_record(requests)['state'], dtype=float)
def kernel_path():
    CACHE.mkdir(exist_ok=True)
    target = CACHE / 'thermal_kernel.npz'
    stamp = CACHE / 'kernel_input.sha256'
    digest = sha(INPUT / 'thermal_kernel.json')
    if not target.exists() or not stamp.exists() or stamp.read_text().strip() != digest:
        values = json.loads((INPUT / 'thermal_kernel.json').read_text())
        np.savez_compressed(target, **{k: np.asarray(v, dtype=float) for k, v in values.items()})
        stamp.write_text(digest + '\n')
    return target
def seed_plan(root):
    verify_inputs()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / 'plan.json'
    if not target.exists():
        plan = json.loads((INPUT / 'mechanism_plan.json').read_text())
        plan['historical_source_hashes'] = plan.pop('source_hashes')
        manifest = json.loads((INPUT / 'MANIFEST.json').read_text())
        plan['source_hashes'] = manifest['sha256']
        plan['portability'] = 'Original decisions/layout retained; local inputs checked by a separate package manifest.'
        target.write_text(json.dumps(plan, indent=2) + '\n')
    table = root / 'energy_OPP_table.json'
    if not table.exists():
        shutil.copy2(INPUT / 'energy_OPP_table.json', table)
def reference_case(case, requests=4):
    return REFERENCE / 'mechanisms' / f'{case}_{requests}req'
def assert_first_schedule(folder, case):
    fingerprints = json.loads((REFERENCE / 'first_cohort_fingerprints.json').read_text())
    for filename in ['tasks.csv', 'flows.csv']:
        assert sha(Path(folder) / filename) == fingerprints[case][filename], (case, filename)
