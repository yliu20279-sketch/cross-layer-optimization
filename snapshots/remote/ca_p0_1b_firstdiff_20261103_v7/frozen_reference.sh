#!/bin/bash
set -eu
cd "$(dirname "$0")"
base=../ca_p0_1b_interleaved_20261103_v6
ref=/mnt/sda1/h3240101068/qwen3_30b_a3b_v3_6_experiment/env/bin/python
for model in qwen3 qwen15; do
    for req in request_a request_b; do
        original="$base/runs/${model}_dual01_$req"
        dest="runs/${model}_frozen_$req"
        mkdir -p "$dest"
        cp -L "$original/"*.json "$original/"*.bin "$dest/"
        OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 nice -n 10 timeout 20m "$ref" tools/reference_layer_cpu.py --model "$model" --run-tag "frozen_$req" > "$model.$req.frozen_reference.log" 2>&1 && rc=0 || rc=$?
        echo "$rc" > "$model.$req.frozen_reference.exit"
    done
done
find runs -path '*/pinned_cpu_reference/*' -type f -print0 | sort -z | xargs -0 -r sha256sum > FROZEN_REFERENCE.sha256
