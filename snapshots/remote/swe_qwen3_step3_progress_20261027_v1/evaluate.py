"""Evaluator-only hidden test access after all actor generation exits; gold column excluded."""
import json,sys,subprocess,traceback
from pathlib import Path
import pyarrow.parquet as pq
R=Path(__file__).resolve().parent;OLD=R.parent/'swe_qwen3_step3_gpu_20261026_v1'
sys.path.insert(0,str(OLD/'official_legacy_harness_v3'))
from swebench.harness.test_spec.test_spec import make_test_spec
from swebench.harness.grading import get_eval_report

def evaluate(arm,tasks):
    rows=pq.read_table(OLD/'dev.parquet',filters=[('instance_id','in',[t['instance_id'] for t in tasks])],
        columns=['instance_id','repo','base_commit','version','test_patch','FAIL_TO_PASS','PASS_TO_PASS','environment_setup_commit']).to_pylist()
    scores=[]
    for task in tasks:
        tid=task['instance_id'];actor=R/arm/tid;out=actor/'official_evaluation';out.mkdir(exist_ok=False)
        pred=dict(instance_id=tid,model_name_or_path='Qwen3-original-BF16-'+arm,model_patch=(actor/'COMPLETE_PATCH.diff').read_text())
        row=next(x for x in rows if x['instance_id']==tid);spec=make_test_spec(row,namespace='swebench')
        (out/'eval.sh').write_text(spec.eval_script);(out/'patch.diff').write_text(pred['model_patch'])
        cid=subprocess.check_output(['docker','run','-d','--network','none','--cpus','2','--memory','4g','--pids-limit','512','--label','swe_qwen3_progress_eval=1','-w','/testbed',spec.instance_image_key,'sleep','25m'],text=True).strip()
        try:
            subprocess.run(['docker','exec',cid,'git','reset','--hard',task['base_commit']],check=True,capture_output=True,timeout=60)
            for name in ['eval.sh','patch.diff']:subprocess.run(['docker','cp',str(out/name),cid+':/'+name],check=True,capture_output=True)
            if pred['model_patch']:
                p=subprocess.run(['docker','exec',cid,'git','apply','--verbose','/patch.diff'],capture_output=True,text=True,timeout=60)
                (out/'PATCH_APPLY.json').write_text(json.dumps(dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)))
                if p.returncode:raise RuntimeError('patch apply failed')
            paths=subprocess.check_output(['docker','exec',cid,'git','diff','--name-only',task['base_commit']],text=True).splitlines()
            protected=[p for p in paths if p.startswith('tests/') or '/tests/' in p]
            with (out/'test_output.txt').open('w') as f:subprocess.run(['docker','exec',cid,'bash','/eval.sh'],stdout=f,stderr=subprocess.STDOUT,timeout=900)
            report=get_eval_report(test_spec=spec,prediction=pred,test_log_path=out/'test_output.txt',include_tests_status=True)
            (out/'report.json').write_text(json.dumps(report,indent=2))
            resolved=bool(report[tid]['resolved'])
            scores.append(dict(instance_id=tid,resolved=resolved,changed_existing_tests=protected,admissible=resolved and not protected,report=report))
        except Exception:scores.append(dict(instance_id=tid,resolved=False,admissible=False,infrastructure_error=traceback.format_exc()))
        finally:subprocess.run(['docker','stop','--time','2',cid],capture_output=True,timeout=15)
    (R/arm/'OFFICIAL_EVALUATION.json').write_text(json.dumps(scores,indent=2));return scores

def main():
    tasks=json.loads((R/'DEVELOPMENT_INPUTS.json').read_text());result={}
    for arm in ['development_nonthinking','development_thinking']:result[arm]=evaluate(arm,tasks)
    passing=[a for a,rs in result.items() if len(rs)==2 and all(r['admissible'] for r in rs)
             and all(json.loads((R/a/t['instance_id']/'RESULT.json').read_text())['status']!='INFRA_ERROR' for t in tasks)]
    def cost(a):return (sum(json.loads((R/a/t['instance_id']/'RESULT.json').read_text())['new_tokens'] for t in tasks),a!='development_nonthinking')
    selected=min(passing,key=cost) if passing else None
    gate=dict(state='DEVELOPMENT_GATE_PASS' if selected else 'DEVELOPMENT_GATE_FAILED',selected=selected,results=result,gold_column_read=False,hidden_tests_to_actor=False,NPU_runs=0)
    (R/'DEVELOPMENT_GATE.json').write_text(json.dumps(gate,indent=2))
    print(json.dumps(dict(state=gate['state'],selected=selected)))
if __name__=='__main__':main()
