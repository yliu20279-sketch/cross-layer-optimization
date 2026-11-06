"""Wait only; no stop, move, signal or duplicate run of the previous actor."""
import json,time,subprocess,hashlib,traceback
from pathlib import Path
R=Path(__file__).resolve().parent;P=R.parent/'swe_qwen3_step3_progress_20261027_v2';A=R.parent/'swe_qwen3_step3_acceptance_20261027_v1'
def read(path):
    try:return json.loads(path.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return None
def main():
    deadline=time.monotonic()+12*3600
    while time.monotonic()<deadline:
        gate=read(P/'DEVELOPMENT_GATE.json');delivery=read(P/'DELIVERY.json')
        if gate and gate['state']=='DEVELOPMENT_GATE_PASS':
            (R/'WAIT_STATUS.json').write_text(json.dumps(dict(state='SKIPPED_V2_PASSED')));return
        if gate and delivery:break
        if read(P/'PIPELINE_FAILURE.json'):raise RuntimeError('Previous pipeline failed; inspect before any candidate launch')
        time.sleep(10)
    else:raise RuntimeError('Previous pipeline wait twelve-hour bound')
    assert gate['state']=='DEVELOPMENT_GATE_FAILED'
    ready=read(R/'CANDIDATE_READY.json');assert ready is not None,'Candidate not sealed'
    for name,digest in ready['files'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,name
    assert not A.exists(),'New holdout root exists: do not reuse identities or override evidence'
    assert read(P/'IMAGE_VERIFICATION.json')['state']=='PASS'
    import shutil
    shutil.copy2(P/'IMAGE_VERIFICATION.json',R/'IMAGE_VERIFICATION.json')
    (R/'PREVIOUS_GATE.json').write_text(json.dumps(dict(gate=gate,delivery=delivery,previous_root=str(P)),indent=2))
    PY=R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
    (R/'WAIT_STATUS.json').write_text(json.dumps(dict(state='PREVIOUS_COMPLETE_FAILED_STARTING_SINGLE_CANDIDATE')))
    subprocess.run([str(PY),str(R/'launch.py')],cwd=R,check=True)
if __name__=='__main__':
    try:main()
    except Exception:(R/'WAIT_FAILURE.json').write_text(json.dumps(dict(traceback=traceback.format_exc()),indent=2));raise
