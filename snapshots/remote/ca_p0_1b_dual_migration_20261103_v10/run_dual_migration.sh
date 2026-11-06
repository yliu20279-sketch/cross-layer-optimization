#!/bin/bash
set -eu
cd "$(dirname "$0")"
base=../ca_p0_1b_q15_k64_20261103_v9
cp -r "$base/core" "$base/tools" "$base/models" "$base/contracts" "$base/evidence" "$base/upstream" "$base/frozen_inputs" .
cp "$base/INPUTS.sha256" "$base/audit.py" .
python3 install_dual_migration.py
sha256sum -c INPUTS.sha256
ref=/mnt/sda1/h3240101068/qwen3_30b_a3b_v3_6_experiment/env/bin/python
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
for model in qwen3 qwen15; do
    nice -n 10 timeout 75m "$ref" tools/run_interleaved.py --model "$model" --tag dual01 --allow-correctness-check > "$model.target.log" 2>&1 && rc=0 || rc=$?
    echo "$rc" > "$model.target.exit"
    test "$rc" = 0 || continue
    python3 audit.py "$model" > "$model.audit.log" 2>&1 && rc=0 || rc=$?
    echo "$rc" > "$model.audit.exit"
done
find runs -type f -print0 | sort -z | xargs -0 -r sha256sum > RUNS.sha256
