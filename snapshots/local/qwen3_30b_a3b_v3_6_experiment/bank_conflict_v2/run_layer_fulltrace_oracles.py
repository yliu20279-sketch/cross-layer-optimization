#!/usr/bin/env python3
import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent
SUITE=ROOT/'results/bank_sampling_layer_stratified_v2'
LAYERS=[0,8,16,24,32,40,47]
BINARY=ROOT/'toolchain/popnet_cross_request_release_v2/build_fulltrace_v4/popnet'
RAMULATOR=ROOT/'toolchain/ramulator2_cross_request_v1/libramulator.so'
RELEASE=ROOT/'results/bank_sampling_fulltrace_reference_v1/c8_simultaneous_release.csv'


def one(layer):
    graph=SUITE/'graphs'/f'layer{layer}_full';out=SUITE/'runs'/f'layer{layer}_full_oracle'
    val=out/'validation.json'
    if val.exists() and json.loads(val.read_text()).get('status')=='PASS':return {'layer':layer,'status':'SKIP_PASS'}
    cmd=[sys.executable,HERE/'run_arrival_sampling.py','--root',ROOT,'--graph',graph,'--out',out,'--binary',BINARY,'--ramulator-library',RAMULATOR,'--request-releases',RELEASE,'--hiband','--ignore-cross-request-bank-timing','--timeout-seconds',1200]
    env=os.environ.copy();env['HB_BANK_LOG_DETAIL']='0'
    logs=SUITE/'launcher_logs';logs.mkdir(parents=True,exist_ok=True)
    with (logs/f'layer{layer}_full_oracle.log').open('w') as handle:r=subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env,stdout=handle,stderr=subprocess.STDOUT)
    return {'layer':layer,'status':'PASS' if r.returncode==0 else 'FAIL','returncode':r.returncode}


def main():
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(one,LAYERS):print(json.dumps(result),flush=True);results.append(result)
    (SUITE/'oracle_launcher_status.json').write_text(json.dumps(results,indent=2)+'\n')
    if any(x['status']=='FAIL' for x in results):raise SystemExit(1)


if __name__=='__main__':main()
