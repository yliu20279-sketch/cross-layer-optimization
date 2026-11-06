"""Separate hidden evaluation using pinned official v3 test scripts and grading."""
import json,sys,subprocess,time,traceback
from pathlib import Path
import pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'official_legacy_harness_v3'))
from swebench.harness.test_spec.test_spec import make_test_spec
from swebench.harness.grading import get_eval_report

def main():
    rows=pq.read_table(ROOT/'dev.parquet',columns=['instance_id','repo','base_commit','version','test_patch','FAIL_TO_PASS','PASS_TO_PASS','environment_setup_commit']).to_pylist()
    records={r['instance_id']:r for r in rows}
    for line in (ROOT/'development_run/predictions.jsonl').read_text().splitlines():
        pred=json.loads(line);tid=pred['instance_id'];out=ROOT/'development_run'/tid/'hidden_evaluation';out.mkdir(exist_ok=False)
        spec=make_test_spec(records[tid],namespace='swebench')
        (out/'eval.sh').write_text(spec.eval_script)
        (out/'patch.diff').write_text(pred['model_patch'])
        image=spec.instance_image_key
        cid=subprocess.check_output(['docker','run','-d','--network','none','--cpus','2','--memory','4g','--pids-limit','512','--label','swe_qwen3_step3_eval=1','-w','/testbed',image,'sleep','25m'],text=True).strip()
        try:
            subprocess.run(['docker','exec',cid,'git','reset','--hard',records[tid]['base_commit']],check=True,capture_output=True,timeout=60)
            for name in ['eval.sh','patch.diff']:subprocess.run(['docker','cp',str(out/name),cid+':/'+name],check=True)
            apply=subprocess.run(['docker','exec',cid,'bash','-lc','cd /testbed && git apply --allow-empty /patch.diff'],capture_output=True,text=True,timeout=60)
            (out/'PATCH_APPLY.json').write_text(json.dumps(dict(returncode=apply.returncode,stdout=apply.stdout,stderr=apply.stderr)))
            if apply.returncode:raise RuntimeError('Prediction patch application failed')
            with (out/'test_output.txt').open('w') as f:
                p=subprocess.run(['docker','exec',cid,'bash','/eval.sh'],stdout=f,stderr=subprocess.STDOUT,text=True,timeout=900)
            report=get_eval_report(test_spec=spec,prediction=pred,test_log_path=out/'test_output.txt',include_tests_status=True)
            (out/'report.json').write_text(json.dumps(report,indent=2))
            (out/'BINDING.json').write_text(json.dumps(dict(container_id=cid,image=image,harness_commit='670fb056fc68105fdcd3c6b71dae618778f14b86',scope='official test_spec.eval_script and get_eval_report, isolated network-disabled wrapper; not upstream CLI'),indent=2))
        except Exception:
            (out/'FAILURE.json').write_text(json.dumps(dict(traceback=traceback.format_exc(),container_id=cid)))
        finally:subprocess.run(['docker','stop','--time','2',cid],capture_output=True,timeout=15)

if __name__=='__main__':main()
