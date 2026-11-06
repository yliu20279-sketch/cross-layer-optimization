# 第一阶段总验收：证据、归因与结论

验收日期：2026-10-24（Asia/Shanghai）。用户明确将步骤7定义为汇总步骤1—6证据、归因和结论；本步骤仅复核与归档，没有启动仿真、采集或第二阶段。

## 判定

第一阶段约定的执行、比较与证据汇总工作已完成；研究结论为部分受控支持、自然完整块工程收益未建立，整体NO_PROMOTION。不能验收为“三策略均有收益”，也不能把完成步骤1—7写成页级管理价值已证明。不同范围的PASS沿用原边界，不改判历史失败。各门槛见[EVIDENCE_MATRIX.csv](EVIDENCE_MATRIX.csv)，机器判定见[ACCEPTANCE.json](ACCEPTANCE.json)。

研究问题按[步骤1合同](../page_management_stage1_plan_v1/STEP1_RESEARCH_CONTRACT.md)分别检验RR、Heat、CA相对同一O；不是挑选三者oracle。O是项目分配器RR前地址，人工O_fixture另列，并非作者Sem-MoE地址。六组可恢复、合法且不等于RR的来源核查见[步骤2](../page_management_stage1_plan_v1/STEP2_REPORT.md)，固定输入与历史标签绑定见[步骤3](../page_management_stage1_step3_inputs_v1/README.md)。

## 证据结果

受控面板108次新原生、156逻辑行，6项预指定1%工程检验只有4项通过：RR的R两模型均0增量；Heat的eA相对O_fixture下降18.6761%/59.0228%，CA的eC下降34.1078%/38.8112%。Heat与条件随机同周期，CA对对应随机均值仍下降14.5902%/4.7102%。这支持Heat与CA在人工合同中的有限存在性，未支持三策略全部成功。来源：[步骤4报告与主张](../page_management_stage1_step4_execution_v1/REPORT.md)、[预指定验收](../page_management_stage1_step4_execution_v1/PRIMARY_CLAIMS.json)。

自然面板是两模型各old/A/B六组已见第0层完整目标FP16 MoE块，ctx512、一次cached decode、每组4请求；不等于独立新请求或全模型端到端。6个O周期已补齐，18逻辑策略对照7正11负，无一达1%；去除Heat=RR重复后12项4正8负。来源：[步骤5](../page_management_stage1_step5_execution_v1/REPORT.md)、[步骤6统一78行周期表](../page_management_stage1_step6_execution_v1/UNIFIED_CYCLES.csv)。

下表收益均为周期下降比例，负号表示更慢。对O按同模型三组周期求和；对随机按三seed的随机周期总和与重复三次策略周期总和计算，不是逐case百分比算术平均。

|模型|策略|相对O加权收益|相对各自条件随机加权收益|
|---|---|---:|---:|
|Qwen3|RR|-0.002067%|1.437832%|
|Qwen3|Heat|-0.002067%|1.437832%|
|Qwen3|CA|-0.061756%|3.088361%|
|Qwen1.5|RR|-0.003725%|0.271523%|
|Qwen1.5|Heat|-0.003725%|0.271523%|
|Qwen1.5|CA|-0.265550%|23.848720%|

来源：[步骤6独立复算主张](../page_management_stage1_step6_execution_v1/CLAIMS.json)、[18项随机比较](../page_management_stage1_step6_execution_v1/STRATEGY_RANDOM_COMPARISON.csv)。三策略在18个case/strategy项上均优于各自随机均值，但相对O的六个模型/策略汇总全部略慢；随机对照不能替代O主检验。Heat六组完整映射与RR相同，其结果不是额外独立证据。CA在两个模型的三组周期和中也未优于RR。不同策略的匹配随机池不同，相对各自随机的收益大小不能直接用于给策略排序。

## 归因与不能外推的部分

已确认：在当前仿真和固定块合同下，某些人工地址布局可改变完成周期；自然布局相对本次条件随机也具有优势。随机保持各partition精确改动集合D、实际活跃集合A及D∩A和D\A各自目的frame池，只改变池内排列。因此它检验继承策略槽位集合后的排列效果，不是全页空间的均匀无信息随机。自然Heat=RR没有展示频率画像增量。协议和生成器见[步骤6报告](../page_management_stage1_step6_execution_v1/REPORT.md)与[冻结运行协议](../page_management_stage1_step6_execution_v1/EXECUTION_PROTOCOL.json)。

合理解释但尚未单独识别：地址变动同时改变Bank、row/column和空间局部性，可能改变排队、行命中和关键路径暴露。随机可能破坏原布局局部性；尤其Qwen1.5 CA随机参考变慢较多，不能据此称CA相对O加速，也不能把差值全归于Bank冲突。累计等待减少但完成周期不变的受控R反例表明，等待指标不能替代端到块完成周期。当前没有隔离上述机制的额外实验。

暂未验证：新独立来源、非第0层及全模型泛化；实际安装/复制/迁移/采集维护成本和净收益；物理芯片性能。目标FP16数值证据沿[已有目标参考](../selector_all_moe_formula_v1/TARGET_FP16_REPORT.md)继承，本轮时序引擎不执行新的张量forward；源BF16失败不因目标实现一致而改判。4KiB独立选Bank相对强固定4KiB交织及16/64KiB的表达力/周期价值属于第二阶段，未在本轮执行，不能用第一阶段结果证明逐页表必要性或原Sem-MoE系统胜负。

## 证据与执行验收

步骤4为108次新原生，步骤5为8次，步骤6成功控制器为38次（36随机+2RR身份）；步骤6另有旧控制器兼容性失败前已经完成的2RR，全部保留，累计40次。三步累计实际新原生156次；不同合同和身份回归不等于156独立样本。首次控制器因Python路径API兼容问题停止，0随机启动；新版本保持seed/输入/阈值及原绝对dispatch截止，未重抽随机。来源：[步骤6修订](../page_management_stage1_step6_execution_v1/AMENDMENT_1_RUNTIME_COMPATIBILITY.json)与[失败归档核验](../page_management_stage1_step6_execution_v1/runtime_failure_v1/FAILURE_LOCAL_VERIFICATION.json)。

各步保存逻辑地址/事务/回调/信用/依赖审计、身份回归、独立元数据与算术复核以及本地压缩包逐成员哈希核验通过。这里继承对应验收，不冒充一次新的完整事务审计、完整flit或物理硬件证明。原始日志保存在本地证据压缩包，步骤6旧失败单独保留。具体范围见[步骤4本地核验](../page_management_stage1_step4_execution_v1/LOCAL_VERIFICATION.json)、[步骤5本地核验](../page_management_stage1_step5_execution_v1/LOCAL_VERIFICATION.json)、[步骤6本地核验](../page_management_stage1_step6_execution_v1/LOCAL_VERIFICATION.json)和[独立复算](../page_management_stage1_step6_execution_v1/INDEPENDENT_VALIDATION.json)。本步骤所引用文件的字节/哈希绑定见[SOURCE_MANIFEST.json](SOURCE_MANIFEST.json)。

## 第一阶段最终结论

RR：受控预指定场景零周期收益；自然组汇总未优于O。Heat：人工受控对O有收益，但条件随机已复现，且自然Heat=RR；未建立独立画像贡献。CA：人工受控对O及匹配随机有有限正例；自然组相对随机较好，却没有相对O的汇总工程收益。因此保留受控存在性，不升级自然/部署结论，不为获得正例替换本轮输入、O或门槛。第一阶段可以结束证据验收；尚未通过的研究门槛留作明确缺口，不自动启动补实验或第二阶段。

就本批汇总周期而言，O仍是自然面板较好的基准；这只是已见三组求和结果，不是已部署的最优策略。建议保留O和RR为后续强基线，第二阶段另按已授权的独立规划范围讨论，不自动修改默认运行路径。当前不足以推荐安装CA或Heat来获得自然请求净收益。

周报摘要：完成六组自然完整块的O与三策略、三seed等改动随机统一对照，补齐36个不同随机原生参考并归档，完成第一阶段总验收。受控主检验4/6达1%，自然18项无一达1%，Heat=RR，三策略自然汇总均略慢于O。结论为受控存在性部分支持、自然工程价值未建立，NO_PROMOTION；未启动第二阶段。
