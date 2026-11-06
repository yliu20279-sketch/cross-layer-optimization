"""Launch and independently audit the baseline paging diagnostic, not SOTA."""
import argparse,csv,hashlib,json,math,os,subprocess,time
from pathlib import Path

def rows(path):
    with path.open(newline='') as f:return list(csv.DictReader(f))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--graph',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--binary',type=Path);ap.add_argument('--ramulator-library',type=Path);ap.add_argument('--hiband',action='store_true');ap.add_argument('--deepstack-timing',type=Path);ap.add_argument('--ignore-cross-request-bank-timing',action='store_true');ap.add_argument('--audit-existing',action='store_true');ap.add_argument('--timeout-seconds',type=int,default=3600);a=ap.parse_args()
    prior=Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/qwen1_5_moe_a2_7b_v3_6/memory_bank_completion_v1/results/matrix_full_v2/c1_rep1_hiband_sem_moe/launch.json')
    launch=json.loads(prior.read_text());binary=a.binary or a.root/'toolchain/popnet_paging_src/build_paging_v1/popnet';a.out.mkdir(parents=True,exist_ok=True)
    empty=a.out/'empty.trace';empty.write_text('');env=os.environ.copy();env.update(launch['controls']);env.pop('HB_DEEPSTACK_TIMING',None)
    if a.deepstack_timing:
        if not a.deepstack_timing.is_file():raise FileNotFoundError(a.deepstack_timing)
        env['HB_DEEPSTACK_TIMING']=str(a.deepstack_timing.resolve())
    controls=dict(HB_GRAPH=str(a.graph),HB_OUT=str(a.out),POPNET_STATS_DIR=str(a.out),HB_PCIE_GBPS='55.04',HB_PCIE_LATENCY_NS='270')
    if not a.hiband:controls['HB_FIXED_MODE']='GLOBAL_BIAS'
    else:env.pop('HB_FIXED_MODE',None)
    if a.ignore_cross_request_bank_timing:controls['HB_IGNORE_CROSS_REQUEST_BANK_TIMING']='1'
    else:env.pop('HB_IGNORE_CROSS_REQUEST_BANK_TIMING',None)
    env.update(controls);cmd=launch['command'].copy();cmd[0]=str(binary);cmd[cmd.index('-I')+1]=str(empty)
    graph_meta=json.loads((a.graph/'graph_manifest.json').read_text())
    timing_note='ScaleSim shape-level compute timing' if graph_meta.get('compute_timing')=='scalesim_shape_profile' else 'analytical graph compute timing only'
    bank_note='DeepStack per-operation Bank timing enabled' if a.deepstack_timing else 'DeepStack full-operation Bank timing disabled'
    if a.ramulator_library and not a.ramulator_library.is_file():raise FileNotFoundError(a.ramulator_library)
    evidence=dict(command=cmd,controls={k:v for k,v in env.items() if k.startswith(('HB_','POPNET_','RAMULATOR'))},binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),ramulator_library_sha256=hashlib.sha256(a.ramulator_library.read_bytes()).hexdigest() if a.ramulator_library else None,graph_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.graph.iterdir() if p.is_file()},deepstack_timing_sha256=hashlib.sha256(a.deepstack_timing.read_bytes()).hexdigest() if a.deepstack_timing else None,execution_timeout_seconds=a.timeout_seconds,limitations=['diagnostic only; no formal Sem-MoE or HiBand SOTA claim',bank_note,timing_note])
    if not a.audit_existing:
        (a.out/'launch.json').write_text(json.dumps(evidence,indent=2)+'\n')
        started=time.monotonic()
        with (a.out/'stdout.log').open('w') as log:subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=a.timeout_seconds)
        wall_seconds=time.monotonic()-started
    else:wall_seconds=None
    ops=rows(a.graph/'ops.csv');events={int(r['id']):r for r in rows(a.out/'events.csv')};assert len(events)==len(ops)
    for d in rows(a.graph/'deps.csv'):assert float(events[int(d['dst'])]['start'])>=float(events[int(d['src'])]['done'])
    dma=rows(a.out/'dma_resources.csv');byid={int(r['op_id']):r for r in dma}
    for r in dma:
        assert float(r['service_cycles'])==math.ceil(int(r['bytes'])/55.04)
        assert float(r['done'])==float(r['start'])+float(r['service_cycles'])+270
    for direction in {r['direction'] for r in dma}:
        ordered=sorted((r for r in dma if r['direction']==direction),key=lambda r:float(r['start']))
        for x,y in zip(ordered,ordered[1:]):assert float(y['start'])>=float(x['start'])+float(x['service_cycles'])
    graph=json.loads((a.graph/'graph_manifest.json').read_text())
    assert len(dma)==2*graph['misses']
    for page in graph['page_operations']:
        assert float(events[page['evict']]['start'])>=float(events[page['fetch']]['done'])
        assert float(events[page['commit']]['start'])>=float(events[page['evict']]['done'])
    for r in rows(a.out/'bank_requests.csv'):assert float(events[int(r['op_id'])]['done'])>=float(r['callback_cycle'])
    manifest=json.loads((a.out/'run_manifest.json').read_text())
    assert manifest['represented_mem_bytes']==sum(int(o['bytes']) for o in ops if o['kind'] in ('LOAD','STORE'))
    compute=rows(a.out/'compute_resources.csv');byengine={}
    for r in compute:byengine.setdefault((int(r['npu']),r['engine']),[]).append((float(r['start']),float(r['done'])))
    hic_overlap=sum(max(0,min(b,d)-max(a0,c)) for (n,e),xs in byengine.items() if e=='BSA' for a0,b in xs for c,d in byengine.get((n,'BGA'),[]))
    result=dict(status='PASS',total_cycles=manifest['total_cycles'],operations=len(ops),dma_operations=len(dma),page_misses=graph['misses'],hic_overlap_npu_cycles=hic_overlap,hic_overlap_capacity_fraction=hic_overlap/(16*manifest['total_cycles']) if manifest['total_cycles'] else 0,checks=['all operations completed','all DAG dependencies respected','directional PCIe service conserved','page fetch-evict-commit order respected','HB callbacks precede operation completion','represented memory bytes conserved'],limitations=evidence['limitations']+graph['limitations'])
    result['simulation_wall_seconds']=wall_seconds
    (a.out/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
