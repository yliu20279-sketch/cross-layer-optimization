"""Copied into separate acceptance root after development gate; frozen before issue access."""
import json,hashlib,datetime,traceback
from pathlib import Path
import pyarrow.parquet as pq
import backend as b
import experiment as e
R=Path(__file__).resolve().parent
OLD=R.parent/'swe_qwen3_step3_gpu_20261026_v1'

def main():
    freeze=json.loads((R/'FREEZE.json').read_text())
    for name,digest in freeze['files'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,name
    assert json.loads((R/'IMAGE_VERIFICATION.json').read_text())['state']=='PASS'
    registration=json.loads((R/'NEW_HOLDOUT_REGISTRATION.json').read_text())['tasks']
    ids=[t['instance_id'] for t in registration];columns=['instance_id','repo','base_commit','problem_statement','version']
    rows=pq.read_table(OLD/'test.parquet',filters=[('instance_id','in',ids)],columns=columns).to_pylist()
    tasks=[next(t for t in rows if t['instance_id']==i) for i in ids]
    for t,r in zip(tasks,registration):assert t['base_commit']==r['base_commit']
    b.save(R/'AGENT_INPUTS.json',tasks)
    b.save(R/'PROBLEM_ACCESS.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),after_freeze_utc=freeze['utc'],columns=columns,ids=ids,
        problem_sha256={t['instance_id']:hashlib.sha256(t['problem_statement'].encode()).hexdigest() for t in tasks},gold_column_read=False,hidden_tests_to_actor=False))
    selected=json.loads((R/'SELECTED_METHOD.json').read_text());mode=selected['mode']
    backend=b.Backend();backend.skip_empty_experts=True;backend.instrument()
    # Functional capture perturbation gate, not an overhead estimate.
    backend.thinking=False;backend.decoding=dict(do_sample=False)
    messages=[dict(role='user',content='Reply only READY.')]
    off=backend.generate(messages,'capture_gate_off',16,False);on=backend.generate(messages,'capture_gate_on',16,True)
    assert off['new_token_ids']==on['new_token_ids']
    b.save(R/'CAPTURE_PERTURBATION.json',dict(equal_tokens=True,scope='one short greedy pair, not general equivalence or overhead estimate'))
    results=[]
    for task in tasks:
        b.ROOT=R/'inference'/'acceptance'/task['instance_id'];b.ROOT.mkdir(parents=True)
        b.save(R/'STATUS.json',dict(state='ACCEPTANCE_RUNNING',mode=mode,task=task['instance_id'],completed=results,NPU_runs=0))
        results.append(e.run_task(backend,task,mode,'acceptance',True));b.save(R/'ACCEPTANCE_RESULTS.json',results)
    b.save(R/'STATUS.json',dict(state='ACCEPTANCE_GENERATION_DONE',completed=results,NPU_runs=0))
if __name__=='__main__':
    try:main()
    except Exception:b.save(R/'STATUS.json',dict(state='ACCEPTANCE_INFRA_FAILURE',traceback=traceback.format_exc(),NPU_runs=0));raise
