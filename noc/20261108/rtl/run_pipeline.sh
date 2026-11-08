#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
mkdir -p build
printf 'running\n' > build/pipeline.exit
python3 run_tests.py
result=$?
if [ "$result" -eq 0 ]; then
    python3 check_artifacts.py
    result=$?
fi
if [ "$result" -eq 0 ]; then
    python3 run_synthesis.py
    result=$?
fi
printf '%s\n' "$result" > build/pipeline.exit
exit "$result"
