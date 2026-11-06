import hashlib,json,os,subprocess,tarfile,time,traceback
from pathlib import Path
R=Path(__file__).resolve().parent;OLD=R.parent/'swe_qwen3_step3_gpu_20261026_v1'
def run(name,log,py,timeout):
    with (R/log).open('xb') as f:subprocess.run([str(py),str(R/name)],cwd=R,stdout=f,stderr=subprocess.STDOUT,timeout=timeout,check=True)
def main():
    pid=json.loads((R/'LAUNCH.json').read_text())['pid']
    for _ in range(1320):
        p=Path('/proc')/str(pid)
        if not p.exists():break
        time.sleep(5)
    else:raise RuntimeError('Generation still running')
    assert json.loads((R/'STATUS.json').read_text())['state']=='GENERATION_FINISHED_EVALUATION_PENDING'
    run('collect_all_outcomes.py','PATCH_COLLECTION.log',OLD/'venv/bin/python',600)
    run('evaluate_holdout.py','OFFICIAL_EVAL.log',OLD/'eval_venv/bin/python3.11',2100)
    run('audit_capture.py','CAPTURE_AUDIT.log',OLD/'venv/bin/python',1200)
    reports=json.loads((R/'OFFICIAL_EVALUATION.json').read_text());assert len(reports)==2
    (R/'COMPLETION.json').write_text(json.dumps(dict(state='TWO_FROZEN_HOLDOUTS_EVALUATED',official=reports,gold_patch_read=False,hidden_tests_to_actor=False,NPU_runs=0,scope='pilot execution/evidence complete, task success and numerical/timing certification separate'),indent=2))
    excluded={'EVIDENCE.tar.gz','EVIDENCE.sha256','FILE_MANIFEST.json','FINISH.log'}
    files=[p for p in sorted(R.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name not in excluded and not p.name.endswith('.docker.tar.gz')]
    manifest=[]
    for p in files:
        h=hashlib.sha256()
        with p.open('rb') as f:
            while b:=f.read(8*1024*1024):h.update(b)
        manifest.append(dict(path=p.relative_to(R).as_posix(),bytes=p.stat().st_size,sha256=h.hexdigest()))
    (R/'FILE_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
    with tarfile.open(R/'EVIDENCE.tar.gz','w:gz',compresslevel=1) as tar:
        for p in files+[R/'FILE_MANIFEST.json']:tar.add(p,arcname=p.relative_to(R).as_posix(),recursive=False)
    h=hashlib.sha256()
    with (R/'EVIDENCE.tar.gz').open('rb') as f:
        while b:=f.read(8*1024*1024):h.update(b)
    (R/'EVIDENCE.sha256').write_text(h.hexdigest()+'  EVIDENCE.tar.gz\n')
if __name__=='__main__':
    try:main()
    except Exception:(R/'FINISH_FAILURE.json').write_text(json.dumps(dict(traceback=traceback.format_exc())));raise
