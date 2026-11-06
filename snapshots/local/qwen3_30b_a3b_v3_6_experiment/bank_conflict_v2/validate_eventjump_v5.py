#!/usr/bin/env python3
import concurrent.futures
import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent
BASE=ROOT/'results/bank_sampling_layer_stratified_v2'
OUT=ROOT/'results/eventjump_v6_validation'
LAYERS=[0,8,16,24,32,40,47]
BINARY=ROOT/'toolchain/popnet_cross_request_release_v2/build_eventjump_v6/popnet'
RAMULATOR=ROOT/'toolchain/ramulator2_cross_request_v1/libramulator.so'
RELEASE=ROOT/'results/bank_sampling_fulltrace_reference_v1/c8_simultaneous_release.csv'


def run_one(item):
    layer,mode=item;graph=BASE/'graphs'/f'layer{layer}_full';out=OUT/f'layer{layer}_{mode}'
    command=[sys.executable,HERE/'run_arrival_sampling.py','--root',ROOT,'--graph',graph,'--out',out,'--binary',BINARY,'--ramulator-library',RAMULATOR,'--request-releases',RELEASE,'--hiband','--timeout-seconds',1200]
    if mode=='oracle':command.append('--ignore-cross-request-bank-timing')
    env=os.environ.copy();env['HB_BANK_LOG_DETAIL']='0';logs=OUT/'launcher_logs';logs.mkdir(parents=True,exist_ok=True)
    with (logs/f'layer{layer}_{mode}.log').open('w') as handle:result=subprocess.run(list(map(str,command)),cwd=ROOT,env=env,stdout=handle,stderr=subprocess.STDOUT)
    return {'layer':layer,'mode':mode,'returncode':result.returncode}


def digest_aggregate(path):
    with path.open(newline='') as handle:
        rows=sorted(csv.DictReader(handle),key=lambda row:(int(row['partition']),int(row['bankgroup']),int(row['bank'])))
    fields=['partition','bankgroup','bank','transactions','transactions_with_cross_request_wait','represented_bytes','controller_queue_ticks','cross_request_bank_wait_ticks','cross_request_bank_wait_events','row_command_ticks','completion_ticks','row_status_0','row_status_1','row_status_other']
    return [[row[field] for field in fields] for row in rows]


def main():
    OUT.mkdir(parents=True,exist_ok=True);jobs=[(layer,mode) for layer in LAYERS for mode in ('normal','oracle')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run_one,jobs))
    failures=[row for row in results if row['returncode']]
    comparisons=[]
    for layer,mode in jobs:
        baseline=BASE/'runs'/(f'layer{layer}_full_oracle' if mode=='oracle' else f'layer{layer}_full')
        accelerated=OUT/f'layer{layer}_{mode}'
        old_validation=json.loads((baseline/'validation.json').read_text());new_validation=json.loads((accelerated/'validation.json').read_text())
        same_total=old_validation['total_cycles']==new_validation['total_cycles']
        same_aggregate=digest_aggregate(baseline/'bank_aggregate.csv')==digest_aggregate(accelerated/'bank_aggregate.csv')
        comparisons.append({'layer':layer,'mode':mode,'same_total_cycles':same_total,'same_bank_aggregate':same_aggregate,'baseline_cycles':old_validation['total_cycles'],'accelerated_cycles':new_validation['total_cycles'],'acceleration':json.loads((accelerated/'acceleration.json').read_text())})
        if not same_total or not same_aggregate:failures.append({'layer':layer,'mode':mode,'reason':'mismatch'})
    report={'status':'FAIL' if failures else 'PASS','binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest(),'runs':results,'comparisons':comparisons,'failures':failures}
    (OUT/'validation_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'comparisons':len(comparisons),'failures':failures,'event_jump_cycles':sum(x['acceleration']['event_jump_cycles'] for x in comparisons)},indent=2))
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
