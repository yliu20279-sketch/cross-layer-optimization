import json
from pathlib import Path
r=Path(__file__).resolve().parent
s=dict(state='PASS_LIMITED_FIRST_DIFFERENCE_DIAGNOSIS',step3='PARTIAL',precision='original BF16',host_GiB=128,HB_GiB=8,first_internal='input RMSNorm FP32 mean(square): 9 variance differences; disappear at BF16 boundary',first_persistent_BF16='Q/K/V projection GEMM: 74 / 5 / 3 differences on identical inputs',GPU_capture_identity_checks=4,route_slot_differences=10,route_same_set_slot_differences=9,route_boundary_expert_replacement=1,full_layer_output_differences=4249,full_layer_reexecuted_this_round=False,softmax_FP32='RETAINED',numeric_implementation_changed=False,external_GPU_reference_diagnostics_this_round=1,target_GPU_runs=0,new_native_runs=0,cumulative_native_runs=14,cumulative_Sniper_ROIs=3,physical_NPU_runs=0,previous_report_upload='APPROVED_BY_USER_AND_SHA_VERIFIED',next='source GPU Q/K/V BF16 GEMM reduction and rounding; do not assume sole root cause')
(r/'FINAL_STATUS.json').write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')
for name in ['AGENTS.md','project_maintenance/ASSETS.md','project_maintenance/CONVERSATIONS.md']:
 p=r.parent/name;t=p.read_text(encoding='utf-8');link=('' if name=='AGENTS.md' else '../')+r.name+'/REPORT.md'
 entry=f'2026-10-28 `swe_qwen3`[prefill首差异定位]({link})：同R0002首内部差异为input RMSNorm FP32 mean(square)9行，但回BF16全消失；首持续BF16差异为同输入Q/K/V GEMM74/5/3元素。新GPU前半层/router四项与旧采集逐位一致，CPU9阶段绑定此前两层路径；50阶段/100二进制本地与远端审计通过。10路由slot差异含9个同集合换序、1个边界平局换专家，不能全归因于QKV；原4249输出及softmax FP32差异保留，未重跑完整层或改实现。1次有界外部GPU诊断（峰值73374720 B），目标GPU0/新原生0/物理0，累计原生14/Sniper3；原BF16/host128/HB8，步骤3仍PARTIAL。用户已批准旧报告上传113，已完成并核对SHA，更新旧拒绝快照。\n\n'
 if entry not in t:
  first,sep,rest=t.partition('\n');p.write_text(first+sep+'\n'+entry+rest.lstrip('\n'),encoding='utf-8')
print('Status and indexes saved.')
