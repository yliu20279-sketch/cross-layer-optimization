#!/bin/bash
set -eu
cd "$(dirname "$0")"
test -f qwen3_native_probe/RESULT.json
test -f qwen15_native_probe/RESULT.json
base=../ca_p0_1b_dual_migration_20261103_v10
cp -r "$base/models" "$base/contracts" "$base/frozen_inputs" .
cp "$base/core/"{coupled_layer.py,live_moe.py} core/
cp "$base/tools/run_interleaved.py" tools/
cp "$base/INPUTS.sha256" "$base/audit.py" .
python3 install_model.py
python3 -m py_compile core/coupled_layer.py tools/run_interleaved.py
sha256sum -c INPUTS.sha256
ref=../qwen3_30b_a3b_v3_6_experiment/env/bin/python
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
for model in qwen3 qwen15; do
    nice -n 10 timeout 75m "$ref" tools/run_interleaved.py --model "$model" --tag dual01 --allow-correctness-check > "$model.target.log" 2>&1 && rc=0 || rc=$?
    echo "$rc" > "$model.target.exit"
    test "$rc" = 0 || continue
    python3 audit.py "$model" > "$model.audit.log" 2>&1 && rc=0 || rc=$?
    echo "$rc" > "$model.audit.exit"
    python3 audit_model.py "$model" > "$model.native_model.json" 2> "$model.native_model.log" && rc=0 || rc=$?
    echo "$rc" > "$model.native_model.exit"
done
find runs -type f -print0 | sort -z | xargs -0 -r sha256sum > RUNS.sha256
