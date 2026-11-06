#!/usr/bin/env python3
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
SUITE=ROOT/'results/bank_sampling_layer_stratified_v2'
LAYERS=[0,8,16,24,32,40,47]
WEIGHTS={0:5,8:8,16:8,24:8,32:8,40:7,47:4}
COMPONENTS=['Compute','NoC','DRAM service and non-cross-request memory wait','Paging DMA','Sync/other','Strict cross-request Bank exposed']


def rows(path):
    with path.open(newline='') as handle:return list(csv.DictReader(handle))


def oracle_critical_path(graph,run):
    ops={int(row['id']):row for row in rows(graph/'ops.csv')}
    events={int(row['id']):row for row in rows(run/'events.csv')}
    parents=defaultdict(list)
    for edge in rows(graph/'deps.csv'):parents[int(edge['dst'])].append(int(edge['src']))
    end=max(events,key=lambda key:(float(events[key]['done']),key));chain=[];current=end
    while True:
        chain.append(current)
        if not parents[current]:break
        ready=float(events[current]['ready'])
        current=max(parents[current],key=lambda key:(float(events[key]['done']),key))
        if not math.isclose(float(events[current]['done']),ready,abs_tol=1e-6):raise RuntimeError('critical predecessor mismatch')
    chain.reverse();components={key:0.0 for key in COMPONENTS};detail=[]
    for op_id in chain:
        op,ev=ops[op_id],events[op_id]
        ready,start,done=map(float,(ev['ready'],ev['start'],ev['done']))
        wait=max(0.0,start-ready);duration=max(0.0,done-start);kind=op['kind'];split={key:0.0 for key in COMPONENTS}
        if kind=='COMPUTE':split['Compute']=duration;split['Sync/other']=wait
        elif kind=='NET':split['NoC']=wait+duration
        elif kind in ('LOAD','STORE'):split['DRAM service and non-cross-request memory wait']=wait+duration
        elif kind in ('DMA_H2D','DMA_D2H'):split['Paging DMA']=wait+duration
        else:split['Sync/other']=wait+duration
        for key,value in split.items():components[key]+=value
        detail.append({'op_id':op_id,'kind':kind,'task':op['task'],'ready':ready,'start':start,'done':done,'split':{k:v for k,v in split.items() if v}})
    total=float(json.loads((run/'run_manifest.json').read_text())['total_cycles'])
    if not math.isclose(sum(components.values()),total,abs_tol=1e-6):raise RuntimeError('oracle attribution does not conserve')
    return total,components,chain,detail


def bank_stats(path):
    data=rows(path);return {
        'transactions':sum(int(row['transactions']) for row in data),
        'transactions_with_wait':sum(int(row['transactions_with_cross_request_wait']) for row in data),
        'strict_wait_ticks':sum(float(row['cross_request_bank_wait_ticks']) for row in data),
    }


def main():
    cases=[];weighted={key:0.0 for key in COMPONENTS};weighted_normal=0.0
    for layer in LAYERS:
        graph=SUITE/'graphs'/f'layer{layer}_full';normal=SUITE/'runs'/f'layer{layer}_full';oracle=SUITE/'runs'/f'layer{layer}_full_oracle'
        normal_launch=json.loads((normal/'launch.json').read_text());oracle_launch=json.loads((oracle/'launch.json').read_text())
        for key in ('binary_sha256','ramulator_library_sha256','graph_hashes','deepstack_timing_sha256'):
            if normal_launch.get(key)!=oracle_launch.get(key):raise RuntimeError(f'layer {layer}: {key} differs')
        left=dict(normal_launch['controls']);right=dict(oracle_launch['controls']);flag=right.pop('HB_IGNORE_CROSS_REQUEST_BANK_TIMING',None)
        if flag!='1':raise RuntimeError(f'layer {layer}: oracle flag missing')
        for controls in (left,right):controls.pop('HB_OUT',None);controls.pop('POPNET_STATS_DIR',None)
        if left!=right:raise RuntimeError(f'layer {layer}: non-intervention controls differ')
        normal_total=float(json.loads((normal/'validation.json').read_text())['total_cycles'])
        oracle_total,components,chain,detail=oracle_critical_path(graph,oracle)
        exposed=normal_total-oracle_total;components['Strict cross-request Bank exposed']=exposed
        error=sum(components.values())-normal_total
        if not math.isclose(error,0,abs_tol=1e-6):raise RuntimeError('paired attribution does not conserve')
        weight=WEIGHTS[layer];weighted_normal+=weight*normal_total
        for key in COMPONENTS:weighted[key]+=weight*components[key]
        cases.append({'layer':layer,'weight':weight,'normal_cycles':normal_total,'oracle_cycles':oracle_total,'strict_bank_exposed_cycles':exposed,'strict_bank_exposed_fraction':exposed/normal_total,'components':components,'conservation_error_cycles':error,'normal_bank':bank_stats(normal/'bank_aggregate.csv'),'oracle_bank':bank_stats(oracle/'bank_aggregate.csv'),'critical_path_op_ids':chain,'critical_path_detail':detail})
    weighted_error=sum(weighted.values())-weighted_normal
    report={'status':'PASS','schema':'fulltrace-paired-conserving-attribution-v1','definition':'Oracle critical-path components plus paired normal-minus-owner-shadow delta. Only the paired delta is strict cross-request Bank exposed time.','components_order':COMPONENTS,'cases':cases,'weighted_48_layer_estimate':{'method':'nearest-representative-layer weights; extrapolation, not measured full-model endpoint','weights':WEIGHTS,'normal_cycles':weighted_normal,'components':weighted,'conservation_error_cycles':weighted_error},'claim_boundary':['Seven one-step layer-isolated full-transaction traces with simultaneous c8 release.','Exact conservation holds per measured layer and for the weighted extrapolation.','The weighted 48-layer result is not an end-to-end full-model simulation.','Zero exposed Bank cycles means Bank waiting is off the measured critical path; it does not mean zero cumulative Bank contention.']}
    out=SUITE/'step7_conserving_attribution.json';out.write_text(json.dumps(report,indent=2)+'\n')
    with (SUITE/'step7_components.csv').open('w',newline='') as handle:
        fields=['layer','weight','normal_cycles','oracle_cycles']+COMPONENTS+['conservation_error_cycles'];writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
        for case in cases:writer.writerow({'layer':case['layer'],'weight':case['weight'],'normal_cycles':case['normal_cycles'],'oracle_cycles':case['oracle_cycles'],**case['components'],'conservation_error_cycles':case['conservation_error_cycles']})
    evidence=[]
    for path in [out,SUITE/'step7_components.csv',SUITE/'oracle_launcher_status.json']:
        evidence.append({'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    for layer in LAYERS:
        for suffix in ('full','full_oracle'):
            run=SUITE/'runs'/f'layer{layer}_{suffix}'
            for name in ('validation.json','launch.json','run_manifest.json','events.csv','bank_aggregate.csv'):
                path=run/name;evidence.append({'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    prov=SUITE/'step7_provenance.json';prov.write_text(json.dumps({'status':'EVIDENCE_COMPLETE','experiment_status':'PASS','files':evidence},indent=2)+'\n')
    print(json.dumps({'status':'PASS','layers':len(cases),'weighted_normal_cycles':weighted_normal,'weighted_components':weighted,'weighted_conservation_error':weighted_error,'provenance_files':len(evidence)},indent=2))


if __name__=='__main__':main()
