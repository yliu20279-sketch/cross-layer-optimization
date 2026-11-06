#!/bin/bash
set -eu
cd "$(dirname "$0")"
ref=/mnt/sda1/h3240101068/qwen3_30b_a3b_v3_6_experiment/env/bin/python
"$ref" -c 'import torch,transformers; assert transformers.__version__=="4.51.3"; print(torch.__version__,transformers.__version__)'
for model in qwen3 qwen15; do
    for ((i=0;i<930;i++)); do
        test ! -f "$model.audit.exit" || break
        sleep 10
    done
    test "$(cat "$model.audit.exit" 2>/dev/null)" = 0 || continue
    for req in request_a request_b; do
        OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 nice -n 10 timeout 20m "$ref" tools/reference_layer_cpu.py --model "$model" --run-tag "dual01_$req" > "$model.$req.pinned_reference.log" 2>&1 && rc=0 || rc=$?
        echo "$rc" > "$model.$req.pinned_reference.exit"
    done
done
find runs -path '*/independent_cpu_reference/*' -type f -print0 | sort -z | xargs -0 -r sha256sum > PINNED_REFERENCE.sha256
