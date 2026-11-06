import datetime,hashlib,json,os,shutil,subprocess,tarfile,time,traceback
from pathlib import Path
R=Path(__file__).resolve().parent
OLD=R.parent/'swe_qwen3_step3_gpu_20261026_v1'
PY=OLD/'venv/bin/python';EVAL=OLD/'eval_venv/bin/python3.11'

def run(script,log,python=PY,timeout=1800):
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='0',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
    with (R/log).open('xb') as f:subprocess.run([str(python),str(script)],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=timeout,check=True)

def main():
    pid=json.loads((R/'LAUNCH.json').read_text())['pid']
    for _ in range(1080):
        p=Path('/proc')/str(pid)
        if not p.exists():break
        assert str(R/'continue_development.py').encode() in (p/'cmdline').read_bytes().split(b'\0')
        time.sleep(5)
    else:raise RuntimeError('Development still active; no concurrent model load')
    assert json.loads((R/'STATUS.json').read_text())['state']=='GENERATION_FINISHED_EVALUATION_PENDING'
    run(R/'collect_all_outcomes.py','PATCH_COLLECTION.log',timeout=300)
    run(R/'evaluate_development.py','OFFICIAL_EVAL.log',python=EVAL)
    run(R/'run_followup.py','FOLLOWUP.log')
    run(R/'audit_capture.py','CAPTURE_AUDIT.log',timeout=600)
    shutil.copyfile(R/'audit_capture.py',R/'diagnostic_followup/audit_capture.py')
    run(R/'diagnostic_followup/audit_capture.py','FOLLOWUP_AUDIT.log',timeout=600)
    reports=json.loads((R/'OFFICIAL_EVALUATION.json').read_text())
    b=dict(state='AUTHORIZED_DEVELOPMENT_WORK_FINISHED_HOLDOUT_NOT_RUN',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),official_evaluation=reports,holdout_problem_access=False,NPU_runs=0,scope='Outcomes and infrastructure checks completed; no promotion of model success, target numerical/timing or strategy benefit')
    (R/'AUTHORIZED_COMPLETION.json').write_text(json.dumps(b,indent=2))
    excluded={'FINISH.log','EVIDENCE.tar.gz','EVIDENCE.sha256','FILE_MANIFEST.json'}
    files=[p for p in sorted(R.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name not in excluded]
    manifest=[]
    for p in files:
        h=hashlib.sha256()
        with p.open('rb') as f:
            while chunk:=f.read(8*1024*1024):h.update(chunk)
        manifest.append(dict(path=p.relative_to(R).as_posix(),bytes=p.stat().st_size,sha256=h.hexdigest()))
    (R/'FILE_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
    with tarfile.open(R/'EVIDENCE.tar.gz','w:gz',compresslevel=1) as tar:
        for p in files+[R/'FILE_MANIFEST.json']:tar.add(p,arcname=p.relative_to(R).as_posix(),recursive=False)
    h=hashlib.sha256()
    with (R/'EVIDENCE.tar.gz').open('rb') as f:
        while chunk:=f.read(8*1024*1024):h.update(chunk)
    (R/'EVIDENCE.sha256').write_text(h.hexdigest()+'  EVIDENCE.tar.gz\n')

if __name__=='__main__':
    try:main()
    except Exception:
        (R/'FINISH_FAILURE.json').write_text(json.dumps(dict(traceback=traceback.format_exc()),indent=2));raise
