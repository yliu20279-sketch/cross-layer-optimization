#!/bin/bash
set -eu
cd "$(dirname "$0")"
base=../ca_p0_1b_interleaved_20261103_v6
cp -r "$base/core" "$base/tools" "$base/models" "$base/contracts" "$base/evidence" "$base/upstream" .
cp "$base/audit.py" .
for model in qwen3 qwen15; do
    mkdir -p "frozen_inputs/$model"
    cp "$base/runs/${model}_dual01/"*_input.bin "frozen_inputs/$model/"
done
python3 instrument.py .
python3 -m py_compile tools/run_interleaved.py tools/reference_layer_cpu.py core/coupled_layer.py
find frozen_inputs -type f -print0 | sort -z | xargs -0 sha256sum > INPUTS.sha256
ref=/mnt/sda1/h3240101068/qwen3_30b_a3b_v3_6_experiment/env/bin/python
for model in qwen3 qwen15; do
    if OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 nice -n 10 timeout 75m python3 tools/run_interleaved.py --model "$model" --tag dual01 --allow-correctness-check > "$model.target.log" 2>&1; then
        echo 0 > "$model.target.exit"
        python3 audit.py "$model" > "$model.audit.log" 2>&1 || continue
        for req in request_a request_b; do
            OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 nice -n 10 timeout 20m "$ref" tools/reference_layer_cpu.py --model "$model" --run-tag "dual01_$req" > "$model.$req.reference.log" 2>&1 && rc=0 || rc=$?
            echo "$rc" > "$model.$req.reference.exit"
        done
        python3 compare.py "$model" > "$model.FIRST_DIFF.json" || true
    else
        echo "$?" > "$model.target.exit"
    fi
done
find runs -type f -print0 | sort -z | xargs -0 -r sha256sum > RUNS.sha256
