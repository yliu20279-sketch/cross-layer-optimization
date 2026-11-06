import json
from pathlib import Path
r=Path(__file__).resolve().parent
status=dict(state='PASS_LIMITED_FOUR_GATE_FUNCTIONAL_BRIDGE',step3='PARTIAL',precision='original BF16',host_GiB=128,HB_GiB=8,accepted_gates=['front-half 68 strict stage comparisons','batch 258 groups / 645120 elements exact','two layers prefill19 + cached decode1: 12 strict output/KV checks exact','continuous HB handoff and generated KV dependency audit'],remaining=['original GPU prefill output 4249 / route 10 differences','softmax FP32 differences retained','772 host fallbacks with CPU costs null','N0 serial only; TP/EP and full timing not certified'],native_runs_this_task=3,native_runs_cumulative=14,Sniper_ROIs_cumulative=3,physical_NPU_runs=0,new_GPU_runs=0,delivery='LOCAL_DELIVERY_VERIFICATION.json',local_audit='LOCAL_CAUSALITY_AUDIT.json',remote_full_audit='coupled_attempt3/INDEPENDENT_AUDIT.json',report_upload='AUTO_REVIEW_REJECTED; local report retained; no retry')
(r/'FINAL_STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
(r/'FOUR_GATES_ACCEPTANCE.json').write_text(json.dumps(dict(state=status['state'],gates=status['accepted_gates'],scope=status['remaining']),ensure_ascii=False,indent=2),encoding='utf-8')
root=r.parent
for name in ['AGENTS.md','project_maintenance/ASSETS.md','project_maintenance/CONVERSATIONS.md']:
 p=root/name;text=p.read_text(encoding='utf-8');link=('' if name=='AGENTS.md' else '../')+r.name+'/REPORT.md'
 entry=f'2026-10-28 `swe_qwen3`[四项功能门槛/连续两层]({link})：N0串行原生矩阵/存储＋显式host回退路径PASS_LIMITED；前半层68项、两层prefill19/cached decode1输出与KV共12严格项逐位一致，batch258组645120元素零差异；2次连续HB交接、4次KV追加审计通过。139420事件/107915094事务，SRAM703744 B、HB范围102833632 B；260载荷本地SHA及因果复核通过。772次host回退成本null，非纯NPU/TP16/EP16/完整时序；原GPU prefill输出4249与路由10位置差异、softmax FP32差异保留，步骤3仍PARTIAL。失败两次保留，本轮原生3、累计14/Sniper3/物理0，无新GPU/agent/留出/NoC；原BF16/host128/HB8不变。本地报告上传被自动审批拒绝，未重试。\n\n'
 if entry not in text:
  first,sep,rest=text.partition('\n');p.write_text(first+sep+'\n'+entry+rest.lstrip('\n'),encoding='utf-8')
print('Local status and three indexes updated; existing entries preserved.')
