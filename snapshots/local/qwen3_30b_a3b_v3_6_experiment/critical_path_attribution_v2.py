#!/usr/bin/env python3
"""Conserving critical-path decomposition using emitted DeepStack fields."""
import argparse,csv,json,math
from collections import defaultdict
from pathlib import Path

COMPONENTS=("Compute","NoC","DRAM ideal service","Bank mapping/row conflict","Bank queue/residual","Paging DMA","Sync/other")

def rows(path):
    with path.open(newline='',encoding='utf-8') as f:yield from csv.DictReader(f)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--graph',type=Path,required=True);ap.add_argument('--run',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    ops={int(r['id']):r for r in rows(a.graph/'ops.csv')};events={int(r['id']):r for r in rows(a.run/'events.csv')};parents=defaultdict(list)
    for e in rows(a.graph/'deps.csv'):parents[int(e['dst'])].append(int(e['src']))
    manifest=json.loads((a.run/'run_manifest.json').read_text())
    end=max(events,key=lambda i:(float(events[i]['done']),i));chain=[];cur=end
    while True:
        chain.append(cur)
        if not parents[cur]:break
        ready=float(events[cur]['ready']);cur=max(parents[cur],key=lambda i:(float(events[i]['done']),i))
        if not math.isclose(float(events[cur]['done']),ready,abs_tol=1e-6):raise RuntimeError(f'critical predecessor mismatch at op {chain[-1]}')
    chain.reverse();comp={k:0.0 for k in COMPONENTS};detail=[]
    for op_id in chain:
        op,ev=ops[op_id],events[op_id];ready,start,done=map(float,(ev['ready'],ev['start'],ev['done']));wait=max(0.0,start-ready);duration=max(0.0,done-start);kind=op['kind']
        split={k:0.0 for k in COMPONENTS}
        if kind=='COMPUTE':split['Compute']=duration;split['Sync/other']=wait
        elif kind=='NET':split['NoC']=wait+duration
        elif kind in ('LOAD','STORE'):
            ideal=min(duration,float(ev.get('ideal_bank_cycles') or 0));penalty=min(duration-ideal,float(ev.get('bank_penalty_cycles') or 0))
            split['DRAM ideal service']=ideal;split['Bank mapping/row conflict']=penalty;split['Bank queue/residual']=wait+duration-ideal-penalty
        elif kind in ('DMA_H2D','DMA_D2H'):split['Paging DMA']=wait+duration
        else:split['Sync/other']=wait+duration
        for k,v in split.items():comp[k]+=v
        detail.append(dict(op_id=op_id,kind=kind,task=op['task'],ready=ready,start=start,done=done,wait=wait,duration=duration,components={k:v for k,v in split.items() if v}))
    makespan=float(manifest['total_cycles']);attributed=sum(comp.values())
    if not math.isclose(attributed,makespan,rel_tol=1e-10,abs_tol=1e-6):raise RuntimeError(f'non-conservative attribution: {attributed} != {makespan}')
    payload=dict(schema_version='critical-path-attribution-2.0',definition='latest-parent DAG critical path; emitted DeepStack ideal and bank-penalty fields; remaining memory resource wait is queue/residual',makespan_cycles=makespan,attributed_cycles=attributed,conservation_error_cycles=attributed-makespan,components=comp,critical_path_op_ids=chain,detail=detail,limitations=['Critical-path attribution, not sum of all device busy time.','Bank queue/residual includes memory-resource waiting not explained by emitted per-op DeepStack ideal and mapping/row penalty.','NoC and DMA resource wait are assigned to their respective operation classes; compute wait and barriers are Sync/other.'])
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(payload,indent=2)+'\n');print(json.dumps({k:payload[k] for k in ('makespan_cycles','components','conservation_error_cycles')},indent=2))
if __name__=='__main__':main()
