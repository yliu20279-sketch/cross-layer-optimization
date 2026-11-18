#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
arm=$1
cat > "map_$arm.ys" <<EOF
read_liberty -lib NangateOpenCellLibrary_typical.lib
read_verilog -sv mesh.sv circuits.sv noc_paired.sv coherence_mesh.sv dual_plane_noc.sv
hierarchy -check -top dual_plane_noc -chparam ENHANCED $arm
synth -top dual_plane_noc -flatten -noabc
dfflibmap -liberty NangateOpenCellLibrary_typical.lib
abc -D 800 -liberty NangateOpenCellLibrary_typical.lib
clean
check -assert
stat -liberty NangateOpenCellLibrary_typical.lib
write_verilog -noattr mapped_$arm.v
setundef -zero
hilomap -singleton -hicell LOGIC1_X1 Z -locell LOGIC0_X1 Z
write_verilog -noattr physical_mapped_$arm.v
EOF
yosys -Q -T -l "map_$arm.log" -s "map_$arm.ys"
printf 'PASS_MAPPING %s\n' "$arm"
