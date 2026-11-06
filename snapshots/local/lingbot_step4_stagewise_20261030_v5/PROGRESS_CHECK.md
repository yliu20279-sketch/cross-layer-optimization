# 步骤4两阶段验收进度核查

本轮只读核查，未重启、推进或修改远端实验；未运行新增GPU或目标原生任务。当前仍PARTIAL，完整单层数值核对和独立审计尚未完成。

第一阶段A（attention和自主FFN输入）：条件分支49883行已完成，A_COMPLETE.json记录输入SHA为7b28b11eedce79c371436b2a84583161d01f2f178a3a81cfe99df93cd7c10eb9。无条件分支已通过42752行；合计92635/98869行，约93.69%。当前块为无条件[42752,42816)，不是已经通过的块。

监督进程1245915存活，观察时累计运行约5小时28分钟，日志继续出现逐块0差异记录，未再次停止。第二阶段B（自主全路由批量专家、归约和层输出）尚未开始；RESULT.json、INDEPENDENT_AUDIT.json、PERMISSION_AUDIT.json及独立审计日志尚未生成。不能把A的通过行数称为完整层输出通过。

最近每64行约15—16秒，A还余6234行，粗估约25分钟；这是第一阶段剩余时间估计，不包括B及独立审计，不能当完整验收完成时间。旧FFN4元素失败和修复记录保留，逐位门槛未放宽，原混合BF16/FP32、host128/HB8及目标GPU0不变。

来源：PROGRESS_CHECK_REMOTE.json、PROGRESS_CHECK_SUMMARY.json；远端full_layer_stagewise_v1/STATUS.json、cond/A_COMPLETE.json、EXITS.json、stagewise_layer.log及监督进程ps。未重验完整大载荷，待既定独立审计运行后再判完整单层结果。
