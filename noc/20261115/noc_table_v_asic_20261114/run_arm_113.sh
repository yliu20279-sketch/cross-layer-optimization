#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
arm=$1
case "$arm" in 0|1) ;; *) exit 2;; esac
export NOC_ARM="$arm"
exec 9>"arm_${arm}.lock"
flock -n 9
image=noc-table-v-openroad:2.0-17598
run() {
  docker run --rm --network none --cpus 12 --memory 30g --user "$(id -u):$(id -g)" \
    -e NOC_ARM -e HOME=/tmp -v "$PWD:/experiment" -w /experiment "$image" \
    -no_init -exit -threads 12 "$1"
}
run resume_detail_route.tcl 2>&1 | tee "physical_$arm.log"
grep -qx "PASS_PHYSICAL $arm" "physical_$arm.log"
test -s "route_$arm.spef"
grep -m1 -q '^\*D_NET[[:space:]]' "route_$arm.spef"
run check_extracted.tcl 2>&1 | tee "extracted_$arm.log"
grep -qx "PASS_PHYSICAL $arm" "extracted_$arm.log"
if grep -Eq '^\[ERROR |^Error:' "extracted_$arm.log"; then exit 1; fi
sha256sum "route_$arm.spef" "route_$arm.odb" "extracted_$arm.log" "drc_$arm.rpt" > "result_$arm.sha256"
