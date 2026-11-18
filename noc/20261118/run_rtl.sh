#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
arm=$1
iverilog -g2012 -s tb_dual -Ptb_dual.ENHANCED="$arm" -o "tb_$arm.vvp" \
  mesh.sv circuits.sv noc_paired.sv coherence_mesh.sv dual_plane_noc.sv tb_dual.sv
vvp "tb_$arm.vvp"
