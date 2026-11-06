import json,re,subprocess,datetime
from pathlib import Path
R=Path(__file__).resolve().parent;P=R.parent/'swe_qwen3_step3_progress_20261027_v1'
cids=re.findall(r'\b[0-9a-f]{64}\b',(P/'RUN.log').read_text())
closed=[]
for cid in dict.fromkeys(cids):
    info=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
    if info['Config']['Labels'].get('swe_qwen3_progress_v1')!='1':continue
    assert info['HostConfig']['NetworkMode']=='none'
    subprocess.run(['docker','stop','--time','2',cid],check=True,capture_output=True,timeout=20);closed.append(cid)
receipt=dict(state='INTERRUPTED_FOR_BACKEND_DIAGNOSTIC',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    reason='Source MoE scans all128 experts, per-token sparse decode overhead. Preserve completed/partial requests; v2 validates ascending nonempty-only loop before restarting bounded paired development.',
    stopped_pids=[3163007,3163008],containers_stopped=closed,model_precision='original BF16',new_holdout_bodies_read=False,NPU_runs=0)
(P/'INTERRUPTION.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))
