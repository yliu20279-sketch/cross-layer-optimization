#!/usr/bin/env bash
set -euo pipefail
tools="$HOME/.cache/noc-table-v-tools/unpack"
export LD_LIBRARY_PATH="$tools/../openroad/opt/or-tools/lib:$tools/usr/lib/x86_64-linux-gnu:$tools/lib/x86_64-linux-gnu"
export PATH="$tools/usr/bin:$PATH"
export TCL_LIBRARY="$tools/usr/share/tcltk/tcl8.6"
for arm in "$@"; do
  test -s "mapped_$arm.v"
  NOC_NETLIST="mapped_$arm.v" "$tools/../openroad/usr/bin/openroad" -no_init -exit -threads 4 synth_power.tcl > "synth_timing_power_$arm.log" 2>&1
  if grep -q '^Error:' "synth_timing_power_$arm.log"; then cat "synth_timing_power_$arm.log"; exit 1; fi
  grep -q 'Leakage' "synth_timing_power_$arm.log"
done
