#!/bin/bash
set -u
cd /mnt/sda1/h3240101068/qwen15_step4_tx32_W0VFwG
while test ! -f pp56rmsfixed.exit || test ! -f referencekv.exit; do sleep 15; done
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
p=../qwen3_30b_a3b_v3_6_experiment/env/bin/python
"$p" tools/audit_rmsfixed.py > rmsfixed_audit.log 2>&1
rc=$?
echo "$rc" > rmsfixed_audit.exit
if test -f rmsfixed_review/SHA256SUMS; then sha256sum -c rmsfixed_review/SHA256SUMS > rmsfixed_review/VERIFY.log; fi
if test "$rc" != 0; then exit "$rc"; fi
nice -n 10 timeout 4h "$p" tools/run_fourstage_rmsfixed.py --model qwen15 --tag fourstage_rmsfixed --timeout 13800 --allow-correctness-check > fourstage_rmsfixed.log 2>&1
echo $? > fourstage_rmsfixed.exit
