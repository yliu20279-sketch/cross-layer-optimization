"""Complete the already authorized serial pipeline; explicit gate prevents holdout access on dev failure."""
import json,time,subprocess,datetime,traceback,shutil
from pathlib import Path
R=Path(__file__).resolve().parent;A=R.parent/'swe_qwen3_step3_acceptance_20261027_v1'
PY=R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
deadline=time.monotonic()+12*3600
def read(p):
    try:return json.loads(p.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return None
def wait_file(path):
    while time.monotonic()<deadline:
        value=read(path)
        if value is not None:return value
        time.sleep(10)
    raise RuntimeError('Pipeline twelve-hour bound exceeded')
def main():
    # Existing finish_development.py alone performs dev scoring after actor exit.
    while time.monotonic()<deadline:
        gate=read(R/'DEVELOPMENT_GATE.json')
        if gate:break
        state=read(R/'STATUS.json') or {}
        if state.get('state')=='INFRA_FAILURE':raise RuntimeError(state)
        time.sleep(10)
    else:raise RuntimeError('Development gate deadline')
    if gate['state']!='DEVELOPMENT_GATE_PASS':
        final=dict(state='STEP3_DEVELOPMENT_GATE_FAILED_NO_NEW_HOLDOUT_ACCESS',gate=gate,
                   precision='original BF16',host_GiB=128,HB_GiB=8,NPU_runs=0,new_holdout_bodies_read=False,
                   next='Return to development; no claim that current method passed.')
        (R/'FINAL_STATUS.json').write_text(json.dumps(final,indent=2))
        (R/'REPORT.md').write_text('# 步骤3新开发结果\n\n本轮候选方法未满足预登记的两开发官方修复门槛，未运行新留出。\n\n来源：DEVELOPMENT_GATE.json、DEVELOPMENT_RESULTS.json、各任务official_evaluation/report.json。\n\n原BF16及host128/HB8不变，NPU运行0。旧失败保留，开发选择不是总体成功率。详见FINAL_STATUS.json；当前方法没有功能准入。\n')
        subprocess.run([str(PY),str(R/'package_evidence.py')],check=True);return
    image=wait_file(R/'IMAGE_VERIFICATION.json');assert image['state']=='PASS'
    subprocess.run([str(PY),str(R/'prepare_acceptance.py')],check=True)
    shutil.copy2(R/'package_evidence.py',A/'package_evidence.py')
    subprocess.run([str(PY),str(A/'launch_acceptance.py')],check=True)
    final=wait_file(A/'FINAL_STATUS.json')
    (A/'REPORT.md').write_text('# 步骤3新冻结留出结果\n\n状态：'+final['state']+'。\n\n详见FINAL_STATUS.json、OFFICIAL_EVALUATION.json、FREEZE.json、PROBLEM_ACCESS.json、CAPTURE_AUDIT_ALL.json。\n\n原BF16与host128/HB8不变，NPU运行0。仅开发选择＋两新留出pilot，不是总体成功率、目标数值/时序或HiBand/Sem-MoE收益认证。\n')
    subprocess.run([str(PY),str(A/'package_evidence.py')],check=True)
    (R/'PIPELINE_COMPLETE.json').write_text(json.dumps(dict(state='NEW_HOLDOUT_FINISHED',acceptance_root=str(A),final=final),indent=2))
    subprocess.run([str(PY),str(R/'package_evidence.py')],check=True)
if __name__=='__main__':
    try:main()
    except Exception:(R/'PIPELINE_FAILURE.json').write_text(json.dumps(dict(traceback=traceback.format_exc()),indent=2));raise
