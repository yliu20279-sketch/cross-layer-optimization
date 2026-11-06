import hashlib
import json
from pathlib import Path
import time

root=Path(__file__).resolve().parent
for model,baseline in [('qwen3','ca_p0_1b_softmax_20261103_v8'),('qwen15','ca_p0_1b_q15_k64_20261103_v9')]:
    exit_file=root/f'{model}.audit.exit'
    deadline=time.monotonic()+160*60
    while not exit_file.exists() and time.monotonic()<deadline:
        time.sleep(10)
    if not exit_file.exists() or exit_file.read_text().strip()!='0':
        continue
    run=root/'runs'/f'{model}_dual01'
    old=root.parent/baseline/'runs'/run.name
    files=sorted(run.glob('request_*.bin'))
    assert files
    compared={}
    for file in files:
        current=file.read_bytes()
        assert current==(old/file.name).read_bytes(), file.name
        compared[file.name]=hashlib.sha256(current).hexdigest()
    migration=json.loads((run/'DUAL_REQUEST_MIGRATION.json').read_text())
    assert migration['after_ns']>migration['before_ns']
    (run/'MIGRATION_AUDIT.json').write_text(json.dumps({
        'simulated_ns':migration['after_ns']-migration['before_ns'],
        'bitwise_outputs_and_kv':compared,
        'target_cpu_pcie_cache_maintenance_verified':False,
        'hardware_simultaneous_service_verified':False,
        'formal_performance':False,
    },indent=2))
