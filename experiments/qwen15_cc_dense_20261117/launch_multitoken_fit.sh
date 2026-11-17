#!/usr/bin/env bash
set -euo pipefail
root=/mnt/sda1/h3240101068/qwen15_step4_tx32_W0VFwG
paired=$(realpath ../pair_v3)
export PYTHONPATH="$paired"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1

run_sample() {
    local tokens="$1" seed="$2" name="fit${1}_${2}"
    test ! -e "$name"
    nice -n 10 /usr/bin/python3 -B -u run_multitoken_fit.py "$root" "$paired/build/coupled_backend" "$name" "$tokens" "$seed" hiband_reference > "$name.log" 2>&1 &
    sample_pid=$!
    printf '%s %s\n' "$name" "$sample_pid" > "$name.pid"
}

run_fit() {
    local seed="$1" small="$2" large="$3" target="$4"
    local first second sample_pid failed=0
    run_sample "$small" "$seed"
    first=$sample_pid
    run_sample "$large" "$seed"
    second=$sample_pid
    wait "$first" || failed=1
    wait "$second" || failed=1
    test "$failed" = 0
    /usr/bin/python3 -B fit_multitoken_scaling.py . "$seed" "$small" "$large" "$target"
}

(
    cd "$paired"
    sha256sum -c INPUTS.sha256
)
run_fit 161101 4 8 16 &
children=("$!")
for seed in 641101 641102 641103; do
    run_fit "$seed" 16 32 64 &
    children+=("$!")
done
failed=0
for pid in "${children[@]}"; do
    wait "$pid" || failed=1
done
exit "$failed"
