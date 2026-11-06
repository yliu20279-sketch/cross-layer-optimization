import hashlib,json,traceback,datetime
from pathlib import Path
import pyarrow.parquet as pq
import backend as b
import run_repair as rr
R=Path(__file__).resolve().parent
OLD=R.parent/'swe_qwen3_step3_gpu_20261026_v1'
def main():
    frozen=json.loads((R/'FREEZE.json').read_text())
    for name,digest in frozen['files'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,name
    images=json.loads((R/'IMAGE_VERIFICATION.json').read_text());assert images['state']=='PASS'
    registration=[x for x in json.loads((OLD/'TASK_REGISTRATION.json').read_text())['tasks'] if x['split']=='test'];ids=[x['instance_id'] for x in registration]
    columns=['instance_id','repo','base_commit','problem_statement','version']
    rows=pq.read_table(OLD/'test.parquet',filters=[('instance_id','in',ids)],columns=columns).to_pylist()
    tasks=[next(row for row in rows if row['instance_id']==tid) for tid in ids]
    for task,item in zip(tasks,registration):assert task['base_commit']==item['base_commit']
    inputs=R/'agent_inputs';inputs.mkdir();b.save(inputs/'development_agent_inputs.json',tasks)
    b.save(R/'PROBLEM_ACCESS.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),after_freeze_utc=frozen['utc'],ids=ids,columns=columns,problem_sha256={t['instance_id']:hashlib.sha256(t['problem_statement'].encode()).hexdigest() for t in tasks},gold_column_read=False,hidden_tests_to_actor=False,helper_filename_note='development_agent_inputs is the reused engine filename; split is test'))
    rr.OLD=inputs
    b.save(R/'STATUS.json',dict(state='HOLDOUT_LOADING',NPU_runs=0))
    backend=b.Backend();backend.instrument();backend.decoding=dict(do_sample=True,temperature=0.7,top_p=0.8,top_k=20)
    b.save(R/'STATUS.json',dict(state='HOLDOUT_RUNNING',NPU_runs=0))
    results=rr.development(backend)
    b.save(R/'HOLDOUT_PROGRESS.json',results)
    b.save(R/'STATUS.json',dict(state='GENERATION_FINISHED_EVALUATION_PENDING',requests=len(backend.requests),split='test',NPU_runs=0))
if __name__=='__main__':
    try:main()
    except Exception:b.save(R/'STATUS.json',dict(state='FAILED_RETAINED',traceback=traceback.format_exc(),NPU_runs=0));raise
