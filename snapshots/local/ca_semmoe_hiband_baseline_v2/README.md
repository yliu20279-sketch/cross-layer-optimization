# CA / Sem-MoE / HiBand P0 隔离实现

此目录只承载 P0-1a 合同、P0-1b 软件修正参考和 P0-1c 旧证据分类。
不是可运行的完整目标基线，不是作者代码等价实现，不包含性能收益结论。

## 实际实现

- `core/scheduling.py`：显式数据分组、源/请求token去重、只接受profile的平衡放置、因果token调度。方法为token-affinity-only项目消融，未实现论文2-gram。
- `core/collectives.py`：有token身份的SRS/SAG语义参考。调用者显式提供加法语义，不默认等同GPU浮点归约或融合原生算子。
- `core/graph.py`：真实目的peer、slot/权重保持、local/global分类、语义依赖图；Q15包含shared专家路径，但不是完整opcode lowering。
- `core/memory.py`：实际shape/dtype字节、跨页/尾字节、生命周期/别名检查、绑定decoder后的partition内双射。
- `core/coaccess.py`：历史成功接收到callback区间画像、独立请求共访、确定评价次数的CA/Heat参考搜索。区间不是Bank命令驻留，尚未接真实sidecar。
- `core/runtime.py`：时钟转换、模式预算/排空参考、成本缺项拒绝。无后端启动能力，不替代真实CPU/缓存/切换成本。
- `core/capture.py`：捕获数据的原模型身份校验；不采集、不加载模型。
- `core/reuse.py`：12项身份条件比较；双方都缺字段不视为匹配。
- `core/readiness.py`、`runner.py`：缺资产/能力/成本/运行栈即拒绝准入。runner只有检查入口，没有模型或模拟器执行入口。

`models/`只提供两模型的显式适配与候选拓扑，不继承旧脚本的有副作用导入、评价未来路由或环境变量。

## 检查范围

`validation/test_contracts.py`是小型软件语义/拒绝控制检查，不是P0-2，也不是模型数值、完整层或目标时序验收。检查用合成整数/小型对象并明确标记，不能写成真实负载PASS。

`contracts/gates.json`记录每模型仍缺的准入条件；任何软件检查成功都不自动将native capability设为verified。

## 证据与历史隔离

`evidence/REMOTE_REUSE_AUDIT.json`为113只读返回，未重放旧实验；`REUSE_DECISIONS.json`区分历史证据和新合同周期复用。
旧源码与结果保持原字节，核对回执见`HISTORICAL_SOURCE_PRESERVATION.json`。

远端隔离目录：`/mnt/sda1/h3240101068/ca_semmoe_hiband_baseline_20261102_v2`。
最初上传版及其14项软件检查保留；后续版本另放`revision_02`，不覆盖最初上传内容。
