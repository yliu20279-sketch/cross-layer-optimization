#!/bin/bash
set -u
cd "$(dirname "$0")"
for model in qwen3 qwen15; do
    for ((i=0;i<930;i++)); do
        test ! -f "$model.exit" || break
        sleep 10
    done
    if [[ "$(cat "$model.exit" 2>/dev/null)" != 0 ]]; then
        echo "$model target did not complete"
        continue
    fi
    python3 audit.py "$model" > "$model.audit.log" 2>&1
    echo "$?" > "$model.audit.exit"
    for req in request_a request_b; do
        OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 nice -n 10 timeout 20m python3 tools/reference_layer_cpu.py --model "$model" --run-tag "dual01_$req" > "$model.$req.reference.log" 2>&1
        echo "$?" > "$model.$req.reference.exit"
    done
done
find runs -type f \( -name '*.json' -o -name '*.bin' \) -print0 | sort -z | xargs -0 -r sha256sum > AUDIT_EVIDENCE.sha256
