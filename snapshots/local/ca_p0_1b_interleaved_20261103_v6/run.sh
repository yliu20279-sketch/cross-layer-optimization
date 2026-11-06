set -eu
cd /mnt/sda1/h3240101068/ca_p0_1b_interleaved_20261103_v6
base=../ca_semmoe_hiband_coupled_20261102_v5
cp -r "$base/core" "$base/tools" "$base/models" "$base/contracts" "$base/evidence" "$base/upstream" .
tar -xzf source.tgz
mv coupled_layer.py core/
python3 make_driver.py .
python3 -m py_compile core/coupled_layer.py tools/run_interleaved.py
sha256sum source.tgz core/coupled_layer.py tools/run_interleaved.py > SOURCE.sha256
for model in qwen3 qwen15; do
    set +e
    OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 nice -n 10 timeout 75m python3 tools/run_interleaved.py --model "$model" --tag dual01 --allow-correctness-check > "$model.log" 2>&1
    rc=$?
    set -e
    echo "$rc" > "$model.exit"
done
find runs -type f ! -name '*.fifo' -print0 | sort -z | xargs -0 -r sha256sum > RUNS.sha256
