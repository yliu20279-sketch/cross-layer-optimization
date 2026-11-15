#!/usr/bin/env bash
set -euo pipefail
tools="$HOME/.cache/noc-table-v-tools"
export LD_LIBRARY_PATH="$tools/openroad/opt/or-tools/lib:$tools/unpack/usr/lib/x86_64-linux-gnu:$tools/unpack/lib/x86_64-linux-gnu"
export TCL_LIBRARY="$tools/unpack/usr/share/tcltk/tcl8.6"
for arm in "$@"; do
  NOC_ARM="$arm" "$tools/openroad/usr/bin/openroad" -no_init -exit -threads 8 physical.tcl 2>&1 | tee "physical_$arm.log"
  grep -q "^PASS_PHYSICAL $arm$" "physical_$arm.log"
done
