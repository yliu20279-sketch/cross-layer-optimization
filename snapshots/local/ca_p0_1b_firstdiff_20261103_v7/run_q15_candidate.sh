#!/bin/bash
set -eu
cd "$(dirname "$0")"
base=../ca_p0_1b_firstdiff_20261103_v7
cp -r "$base/core" "$base/tools" "$base/models" "$base/contracts" "$base/evidence" "$base/upstream" "$base/frozen_inputs" .
cp "$base/audit.py" "$base/compare.py" "$base/INPUTS.sha256" .
cp ../ca_p0_1b_softmax_20261103_v8/core/coupled_layer.py core/
python3 repair_q15_router.py
python3 -m py_compile core/live_moe.py
sha256sum -c INPUTS.sha256
ref=/mnt/sda1/h3240101068/qwen3_30b_a3b_v3_6_experiment/env/bin/python
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
nice -n 10 timeout 75m "$ref" tools/run_interleaved.py --model qwen15 --tag dual01 --allow-correctness-check > qwen15.target.log 2>&1 && rc=0 || rc=$?
echo "$rc" > qwen15.target.exit
test "$rc" = 0
python3 audit.py qwen15
for req in request_a request_b; do
    for suffix in layer k64_tp; do
        nice -n 10 timeout 20m "$ref" "tools/reference_${suffix}_cpu.py" --model qwen15 --run-tag "dual01_$req" > "qwen15.$req.$suffix.log" 2>&1 && rc=0 || rc=$?
        echo "$rc" > "qwen15.$req.$suffix.exit"
    done
done
find runs -type f -print0 | sort -z | xargs -0 -r sha256sum > RUNS.sha256
