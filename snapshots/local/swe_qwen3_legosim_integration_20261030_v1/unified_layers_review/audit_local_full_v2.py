import runpy,json,re,collections,hashlib
from pathlib import Path
H=Path(__file__).resolve().parent;R=H/'unified_layers_fifo_v2'
runpy.run_path(str(H/'audit_local_phase1_v2.py'))
bench=[list(map(int,s.split())) for s in (R/'run3/bench.txt').read_text().splitlines()]
delays=[list(map(int,s.split())) for s in (R/'run3/delayInfo.txt').read_text().splitlines()]
assert len(bench)==len(delays)==156105
assert collections.Counter((v[0],v[2],v[3],v[5]) for v in bench)==collections.Counter(tuple(v[:4]) for v in delays)
assert all(v[4]==2 and 0<=v[5]<=v[6] for v in delays)
status=list(map(int,re.findall(r'terminate with status = (\d+)',(R/'RUN3.log').read_text())))
assert len(status)==4 and all(v==0 for v in status)
remote=json.loads((R/'COLLECTOR_AUDIT.json').read_text());assert remote['returncode']==0
out=dict(state='PASS_LIMITED_UNIFIED_TWO_LAYER_FULL_REPLAY_LOCAL_AUDIT',stage_files=56,strict_layer_KV_checks=12,CPU_actual_outputs=2,NoC_records=156105,packet_identity_multiset_exact=True,subprocesses_zero=4,archive_members=113,archive_sha256=hashlib.sha256((H/'UNIFIED_LAYERS_FIFO_V2_REVIEW.tar.gz').read_bytes()).hexdigest(),full_steps_1_7=False,scope='one active NPU/HB diagnostic topology, not canonical16 or full target timing')
(H/'LOCAL_FULL_V2_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
