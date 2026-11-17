#!/usr/bin/env bash
set -euo pipefail
root=/mnt/sda1/h3240101068/qwen15_step4_tx32_W0VFwG
binary=build/coupled_backend
arms=(hiband_reference project_noc)

run_case() {
    local tag="$1" tokens="$2" seed="$3" arm name
    for arm in "${arms[@]}"; do
        name="${tag}_${arm}"
        test ! -e "$name"
        local command=(/usr/bin/python3 -B -u run_multitoken_calibration.py "$root" "$binary" "$name" "$tokens" "$seed" "$arm")
        nice -n 10 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "${command[@]}" > "$name.log" 2>&1 &
        children+=("$!")
        printf '%s %s\n' "$name" "$!" > "$name.pid"
    done
}

wait_all() {
    local pid failed=0
    for pid in "${children[@]}"; do
        wait "$pid" || failed=1
    done
    children=()
    return "$failed"
}

test -s smoke_hiband_reference/RESULT.json
test -s smoke_project_noc/RESULT.json
sha256sum -c INPUTS.sha256
children=()
run_case pilot16 16 161101
wait_all
/usr/bin/python3 -B audit_multitoken_pair.py . 16 pilot16

run_case input64a 64 641101
run_case input64b 64 641102
run_case input64c 64 641103
wait_all
/usr/bin/python3 -B audit_multitoken_pair.py . 64 input64a input64b input64c
