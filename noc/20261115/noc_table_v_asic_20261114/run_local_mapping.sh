#!/bin/bash
set -euo pipefail
work=$PWD
tools="$HOME/.cache/noc-table-v-tools"
mkdir -p "$tools"
cd "$tools"
apt-get download yosys berkeley-abc opensta libtcl8.6 libreadline8 libffi8 libboost-filesystem1.74.0 libboost-system1.74.0 libgcc-s1
for package in *.deb; do dpkg-deb -x "$package" unpack; done
export PATH="$tools/unpack/usr/bin:$PATH"
export LD_LIBRARY_PATH="$tools/unpack/usr/lib/x86_64-linux-gnu:$tools/unpack/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
yosys -V
ldd "$(command -v sta)" | sed -n '/not found/p'
cd "$work"
for arm in 0 1; do
  cat > "map_$arm.ys" <<EOF
read_liberty -lib NangateOpenCellLibrary_typical.lib
read_verilog -sv mesh.sv circuits.sv noc_paired.sv
hierarchy -check -top noc_paired -chparam ENHANCED $arm
synth -top noc_paired -flatten -noabc
dfflibmap -liberty NangateOpenCellLibrary_typical.lib
abc -D 800 -exe berkeley-abc -liberty NangateOpenCellLibrary_typical.lib
clean
check -assert
stat -liberty NangateOpenCellLibrary_typical.lib
write_verilog -noattr mapped_$arm.v
EOF
  yosys -Q -T -l "map_$arm.log" -s "map_$arm.ys" > /dev/null
done
