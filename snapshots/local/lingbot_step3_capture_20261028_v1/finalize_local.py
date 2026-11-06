import pathlib,json,hashlib,datetime
P=pathlib.Path(__file__).resolve().parent;E=P/'server_evidence'
a=json.loads((E/'INDEPENDENT_CAPTURE_AUDIT.json').read_text());v=json.loads((P/'LOCAL_VERIFICATION.json').read_text());runs=json.loads((E/'CAPTURE_RUNS.json').read_text());m=json.loads((E/'COMPACT_MANIFEST.json').read_text())
assert a['status']=='PASS_LIMITED_REAL_ROUTE_CAPTURE_AND_FIXTURE_INTEGRITY'
report=(P/'REPORT_DRAFT.md').read_text(encoding='utf8')
report=report.replace('最终状态和数字以独立审计及本地交付回执补齐。','步骤3采集和完整性验收已完成，状态PASS_LIMITED_REAL_ROUTE_CAPTURE_AND_FIXTURE_INTEGRITY；完整目标算子功能仍未认证。')
extra=f"""
## 最终机器回执与交付

[独立审计](server_evidence/INDEPENDENT_CAPTURE_AUDIT.json)：{a['check_count']}项检查0失败，六项原始数据负对照全部拒绝；3936条路由及3936条共享专家调用完整，完整40步3840条。逐项验证全部原始route文件，而非抽样。28个完整fixture张量通过SHA/finite检查。最大权重和偏差{a['max_weight_sum_error']}（阈值0.02）；有效权重为零的slot数{a['zero_effective_slots']}。token-layer出现次数为{json.dumps(a['token_layer_occurrences'])}，不是独立样例数。

[运行回执](server_evidence/CAPTURE_RUNS.json)：同进程probe_off/on的raw FP32 latent SHA均为{runs['probe_on']['latent_raw_sha256']}；40步raw SHA={runs['full_on']['latent_raw_sha256']}，与此前无采集40步参考一致。probe_off/on观测耗时分别{runs['probe_off']['seconds']:.3f}/{runs['probe_on']['seconds']:.3f}秒，40步on为{runs['full_on']['seconds']:.3f}秒。这些时间含包装/保存，只是一对观测，不是普遍采集开销或目标延迟。

完整原始路由与Golden保留在113：/mnt/sda1/h3240101068/lingbot_step3_capture_20261028_v1。采集载荷9679536472 B；[远端完整成员SHA清单](server_evidence/REMOTE_FULL_FILE_MANIFEST.json)记录封包时{m['full_remote_members']}成员、{m['full_remote_bytes']} B（含脚本/日志/元数据及review副本，非仅采集载荷）。层0权重不重复复制：[WEIGHT_REFERENCES.json](server_evidence/WEIGHT_REFERENCES.json)绑定canonical shard、tensor头部和此前完整权重校验SHA，本轮没有重算全模型69.69GB。

本地是明确标注的compact review包，不是全量回传：[LOCAL_VERIFICATION.json](LOCAL_VERIFICATION.json)核对外层SHA及{v['verified_members']}载荷成员、{v['verified_bytes']} B；外层{v['archive_bytes']} B，SHA256={v['archive_sha256']}。包含全部路由元数据/全量成员SHA、原始三份latent、六份选定路由、26份Golden选定行副本及审计/失败/协议代码。review行来自完整上下文运行的前32视频行和最后32条件行，不是缩短输入后的模型输出；完整Golden留113。temb常量行整行保留；完整sorted_positions只在远端。

外部参考进程已退出，检查时两GPU均仅23MiB，无本轮模型占用；未操作其他用户进程。没有目标GPU/模拟器/物理NPU执行，也没有HiBand/Sem-MoE收益结论。
"""
(P/'REPORT.md').write_text(report+extra,encoding='utf8')
status=dict(date='2026-10-28',status=a['status'],step3_scope='real route and Golden capture complete; target adaptation is step4',route_records=a['route_records'],full40_route_records=a['full40_route_records'],shared_records=a['shared_records'],fixture_tensors=a['fixture_tensors'],independent_checks=a['check_count'],negative_controls=6,probe_on_off_bitwise=True,full40_matches_prior_reference=True,target_GPU_count=0,target_simulator_runs=0,physical_NPU_runs=0,refiner=False,complete_target_function_certified=False,host_GiB=128,HB_GiB=8,full_raw_remote_only=True,remote_root=m['full_raw_root'],local_payload_members=v['verified_members'],local_payload_bytes=v['verified_bytes'],audit_failures_preserved=['attempt1 incorrect scheduler/model-timestep comparison','attempt2 incorrect FP32-only temb dtype assertion'])
(P/'STATUS.json').write_text(json.dumps(status,indent=2),encoding='utf8')
(P/'README.md').write_text('# LingBot步骤3：真实路由与单层Golden采集\n\n采集/完整性验收完成，目标算子功能未认证。见[报告](REPORT.md)、[状态](STATUS.json)、[本地交付回执](LOCAL_VERIFICATION.json)。目标无GPU，模拟器/物理NPU运行0；refiner排除。3936路由及共享调用、28完整fixture，外部参考输出一致性及独立审计通过。完整原始数据留113，本地仅compact review子集。两次审计假设错误及修订均保留。\n',encoding='utf8')
root=P.parent
summary='LingBot步骤3（2026-10-28）：[真实路由与Golden采集]({link})完成，3936路由/共享调用（完整40步3840）、28完整fixture；同进程采集开关单步及此前40步latent逐位一致，'+str(a['check_count'])+'项独立CPU审计、6负对照及compact本地SHA通过。约9.68GB原始数据留113，本地仅review子集；两次审计假设错误保留并修订。原混合BF16/F32、host128/HB8、refiner排除；GPU仅外部参考，目标GPU0/模拟器0/物理NPU0。步骤3为采集完成，非完整目标功能/时序或HiBand/Sem-MoE收益PASS。'
for rel,link in [('AGENTS.md','lingbot_step3_capture_20261028_v1/REPORT.md'),('project_maintenance/ASSETS.md','../lingbot_step3_capture_20261028_v1/REPORT.md'),('project_maintenance/CONVERSATIONS.md','../lingbot_step3_capture_20261028_v1/REPORT.md')]:
    q=root/rel;s=q.read_text(encoding='utf8');first,rest=s.split('\n',1)
    line=summary.format(link=link)
    if line not in s:q.write_text(first+'\n\n'+line+'\n'+rest,encoding='utf8')
manifest={str(q.relative_to(P)):{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in P.rglob('*') if q.is_file() and q.name!='LOCAL_ARTIFACT_MANIFEST.json' and '__pycache__' not in q.parts}
(P/'LOCAL_ARTIFACT_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
print(json.dumps(status))
