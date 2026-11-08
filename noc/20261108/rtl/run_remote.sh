#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
mkdir -p build
printf 'running\n' > build/runner.exit
python3 run_tests.py
result=$?
printf '%s\n' "$result" > build/runner.exit
exit "$result"
