# NPUSim workload 模板

将整个目录复制为一个独立 benchmark 后使用：

```bash
cd LEGOSIM_MICRO
cp -r NPUSim/templates/npu_workload benchmark/my_npu_workload
cd benchmark/my_npu_workload
make prepare
```

模板保留两条入口：`onnx-run` 和 `cpp-run`。两者共用 `npu_chiplet_config.json`，
并固定 NPU=`(1,0)`、LPDDR5=`(2,0)`。

## ONNX

```bash
make tiny-onnx
make onnx-run
```

流程是：CPU 写入输入，NPU 进行片内计算并访问共享 LPDDR5，最后 CPU 读取输出。
LPDDR5 时序由 LEGOSim 的联合仿真链路单独决定，后续 NPU event 通过 completion
依赖推进。

## C++ 原语

编辑 `npu_primitives_template.cpp`，用 `dmaLoad`、`macCompute`、`vectorCompute`、
`reduceCompute`、`barrier`、`dmaStore` 组合出 NPU 时序，再运行：

```bash
make cpp-run
```

## 主要输出

```text
output/*/bench_npu_intra.txt
output/*/reports/npu_intra_delay_profile.txt
output/*/bench.txt
output/*/delayInfo.txt
output/*/reports/npusim_dram_transactions_*
output/*/reports/ramulator2_lpddr5_timing.csv
```

## 说明

如果修改坐标，请同步调整 `cpu_onnx_chiplet.yml`、`cpp_chiplet.yml` 和
`npu_chiplet_config.json`。
