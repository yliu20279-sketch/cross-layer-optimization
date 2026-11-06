#!/bin/bash
set -eu
cd "$(dirname "$0")"
base=../ca_p0_1b_firstdiff_20261103_v7
cp -r "$base/core" "$base/tools" "$base/models" "$base/contracts" "$base/evidence" "$base/upstream" "$base/frozen_inputs" .
cp "$base/audit.py" "$base/compare.py" "$base/INPUTS.sha256" .
python3 repair_softmax.py
sha256sum -c INPUTS.sha256
ref=/mnt/sda1/h3240101068/qwen3_30b_a3b_v3_6_experiment/env/bin/python
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
nice -n 10 timeout 75m "$ref" tools/run_interleaved.py --model qwen3 --tag dual01 --allow-correctness-check > qwen3.target.log 2>&1 && rc=0 || rc=$?
echo "$rc" > qwen3.target.exit
test "$rc" = 0
python3 audit.py qwen3
for req in request_a request_b; do
    nice -n 10 timeout 20m "$ref" tools/reference_layer_cpu.py --model qwen3 --run-tag "dual01_$req" > "qwen3.$req.reference.log" 2>&1 && rc=0 || rc=$?
    echo "$rc" > "qwen3.$req.reference.exit"
done
python3 compare.py qwen3 > qwen3.FIRST_DIFF.json
find runs -type f -print0 | sort -z | xargs -0 -r sha256sum > RUNS.sha256
