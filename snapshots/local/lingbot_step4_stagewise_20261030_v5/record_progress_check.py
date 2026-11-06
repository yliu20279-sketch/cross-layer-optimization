import pathlib,json
p=pathlib.Path('lingbot_step4_stagewise_20261030_v5');r=json.loads((p/'PROGRESS_CHECK_REMOTE.json').read_text(encoding='utf-8-sig'));assert r['state']=='RUNNING' and r['phase']=='A_attention_and_FFN_input' and r['branch']=='uncond';done=49883+r['begin'];remaining=98869-done;summary=dict(state='PARTIAL_STAGE_A_RUNNING',A_verified_rows=done,A_total_rows=98869,A_progress_percent=100*done/98869,cond_A_complete_rows=49883,uncond_A_verified_rows=r['begin'],B_started=False,full_layer_numerical_complete=False,independent_audit_complete=False,final_result_receipt_exists=False,independent_audit_receipt_exists=False,supervisor_alive_observed=True,old_failure_preserved=True,target_GPU_count=0,host_GiB=128,HB_GiB=8,precision='unchanged mixed BF16/FP32',remote_observation=r,scope='read-only progress check; no experiments/restart/new GPU/new native run');(p/'PROGRESS_CHECK_SUMMARY.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');body=f'''# 步骤4两阶段验收进度核查

本轮只读核查，未重启、推进或修改远端实验；未运行新增GPU或目标原生任务。当前仍PARTIAL，完整单层数值核对和独立审计尚未完成。

第一阶段A（attention和自主FFN输入）：条件分支49883行已完成，A_COMPLETE.json记录输入SHA为7b28b11eedce79c371436b2a84583161d01f2f178a3a81cfe99df93cd7c10eb9。无条件分支已通过{r['begin']}行；合计{done}/98869行，约{100*done/98869:.2f}%。当前块为无条件[{r['begin']},{r['end']})，不是已经通过的块。

监督进程1245915存活，观察时累计运行约5小时28分钟，日志继续出现逐块0差异记录，未再次停止。第二阶段B（自主全路由批量专家、归约和层输出）尚未开始；RESULT.json、INDEPENDENT_AUDIT.json、PERMISSION_AUDIT.json及独立审计日志尚未生成。不能把A的通过行数称为完整层输出通过。

最近每64行约15—16秒，A还余{remaining}行，粗估约{remaining/64*15.5/60:.0f}分钟；这是第一阶段剩余时间估计，不包括B及独立审计，不能当完整验收完成时间。旧FFN4元素失败和修复记录保留，逐位门槛未放宽，原混合BF16/FP32、host128/HB8及目标GPU0不变。

来源：PROGRESS_CHECK_REMOTE.json、PROGRESS_CHECK_SUMMARY.json；远端full_layer_stagewise_v1/STATUS.json、cond/A_COMPLETE.json、EXITS.json、stagewise_layer.log及监督进程ps。未重验完整大载荷，待既定独立审计运行后再判完整单层结果。
''';(p/'PROGRESS_CHECK.md').write_text(body,encoding='utf-8');s=json.loads((p/'STATUS.json').read_text());s['state']='PARTIAL_STAGEWISE_A_RUNNING';s['latest_progress_check']=summary;(p/'STATUS.json').write_text(json.dumps(s,indent=2),encoding='utf-8');print(json.dumps(dict(A_verified_rows=done,A_percent=round(100*done/98869,2),A_remaining_rows=remaining)))
