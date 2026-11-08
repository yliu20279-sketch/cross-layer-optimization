#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
printf 'running\n' > build/final_checks.exit
python3 run_tests.py && python3 check_artifacts.py && python3 run_netlist_tests.py
result=$?
printf '%s\n' "$result" > build/final_checks.exit
exit "$result"
