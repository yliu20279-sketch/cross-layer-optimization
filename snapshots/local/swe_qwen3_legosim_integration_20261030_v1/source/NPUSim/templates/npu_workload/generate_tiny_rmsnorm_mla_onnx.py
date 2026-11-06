#!/usr/bin/env python3
"""生成 NPUSim 模板的极小静态 ONNX smoke 图。

图刻意很小，但覆盖 decoder 中常见的：
分解 RMSNorm -> latent projection -> Q/K/V -> QK^T -> Softmax -> PV。
所有权重直接嵌入 model.onnx，只使用标准 ONNX 算子。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


def value(name: str, shape: list[int]):
    # 为 graph 输入/输出声明静态 shape；动态维度会被当前 NPUSim lowerer 拒绝。
    return helper.make_tensor_value_info(name, TensorProto.FLOAT, shape)


def weights(name: str, shape: tuple[int, ...], offset: int):
    # 生成确定性的小权重，避免随机数导致不同机器上的图内容不一致。
    data = (np.arange(np.prod(shape), dtype=np.float32).reshape(shape) + offset) % 19
    return numpy_helper.from_array((data - 9.0) / 19.0, name)


def main() -> int:
    output = Path("model.onnx")
    # B=1, token 数 S=2, hidden=8, latent=4, head_dim=4。
    hidden = value("hidden", [1, 2, 8])
    context = value("context", [1, 2, 4])
    scalar_epsilon = numpy_helper.from_array(np.array([1.0e-5], dtype=np.float32), "epsilon")
    scalar_scale = numpy_helper.from_array(np.array([0.5], dtype=np.float32), "attn_scale")
    gamma = numpy_helper.from_array(np.linspace(0.8, 1.2, 8, dtype=np.float32), "rms_gamma")
    initializers = [
        scalar_epsilon,
        scalar_scale,
        gamma,
        weights("down_projection", (8, 4), 1),
        weights("query_projection", (4, 4), 3),
        weights("key_projection", (4, 4), 5),
        weights("value_projection", (4, 4), 7),
    ]
    nodes = [
        # 用 Mul/ReduceMean/Sqrt/Reciprocal 分解 RMSNorm，避免依赖某一版
        # ONNX 才有的 RMSNormalization 专用算子。
        helper.make_node("Mul", ["hidden", "hidden"], ["hidden_sq"], name="rms_square"),
        helper.make_node("ReduceMean", ["hidden_sq"], ["mean_square"], name="rms_mean", axes=[-1], keepdims=1),
        helper.make_node("Add", ["mean_square", "epsilon"], ["rms_variance"], name="rms_epsilon"),
        helper.make_node("Sqrt", ["rms_variance"], ["rms"], name="rms_sqrt"),
        helper.make_node("Reciprocal", ["rms"], ["inverse_rms"], name="rms_reciprocal"),
        helper.make_node("Mul", ["hidden", "inverse_rms"], ["normalized"], name="rms_apply"),
        helper.make_node("Mul", ["normalized", "rms_gamma"], ["norm_hidden"], name="rms_scale"),
        # Latent attention 的小型投影与注意力主链。
        helper.make_node("MatMul", ["norm_hidden", "down_projection"], ["latent"], name="latent_projection"),
        helper.make_node("MatMul", ["latent", "query_projection"], ["query"], name="query_projection"),
        helper.make_node("MatMul", ["latent", "key_projection"], ["key"], name="key_projection"),
        helper.make_node("MatMul", ["latent", "value_projection"], ["value"], name="value_projection"),
        helper.make_node("Transpose", ["key"], ["key_t"], name="key_transpose", perm=[0, 2, 1]),
        helper.make_node("MatMul", ["query", "key_t"], ["scores"], name="qk_scores"),
        helper.make_node("Mul", ["scores", "attn_scale"], ["scaled_scores"], name="attention_scale"),
        helper.make_node("Softmax", ["scaled_scores"], ["probabilities"], name="attention_softmax", axis=-1),
        helper.make_node("MatMul", ["probabilities", "value"], ["context"], name="attention_value"),
    ]
    graph = helper.make_graph(nodes, "tiny_rmsnorm_mla", [hidden], [context], initializer=initializers)
    # 使用 opset 17，确保 ReduceMean 的 axes attribute 和其它算子形式稳定。
    model = helper.make_model(graph, producer_name="NPUSim-template", opset_imports=[helper.make_opsetid("", 17)])
    onnx.checker.check_model(model)
    # 预先写入中间 tensor 的静态 shape，方便 NPUSim 直接进行事件 lowering。
    model = onnx.shape_inference.infer_shapes(model)
    onnx.checker.check_model(model)
    onnx.save(model, output)
    print("[TINY-MLA-ONNX][PASS] model=model.onnx nodes={} shape=[1,2,8]".format(len(nodes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
