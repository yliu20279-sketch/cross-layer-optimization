"""Isolated DMA resource and unchanged-path regression microtests."""
import argparse,csv,hashlib,json,os,subprocess
from pathlib import Path

def write(p,rows,fields):
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);args=ap.parse_args(); e=args.root
    prior=Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/qwen1_5_moe_a2_7b_v3_6/memory_bank_completion_v1/results/matrix_full_v2/c1_rep1_hiband_sem_moe/launch.json')
    launch=json.loads(prior.read_text()); binary=e/'toolchain/popnet_paging_src/build_paging_v1/popnet'; base=e/'results/dma_microtests_v1';base.mkdir(exist_ok=True)
    fields=['id','kind','task','phase','pe','bytes','sample_bytes','address','cycles','src','dst','scope','rank']
    def run(name,dma,exe,memory=False):
        root=base/name;g=root/'graph';out=root/'run';g.mkdir(parents=True,exist_ok=True);out.mkdir(exist_ok=True)
        kinds=['DMA_H2D','DMA_H2D','DMA_D2H','COMPUTE','COMPUTE','BARRIER'] if dma else ['CPU','CPU','CPU','COMPUTE','COMPUTE','BARRIER']
        ops=[dict(id=i,kind=k,task=f't{i}',phase='COMPUTE',pe=1 if i==4 else 0,bytes=5504 if dma and i<3 else 0,sample_bytes=0,address=0,cycles=500 if i==3 else 10 if i==4 else 0,src=-1,dst=-1,scope='local',rank=0) for i,k in enumerate(kinds)]
        edges=[{'src':0,'dst':4}]+[{'src':i,'dst':5} for i in (1,2,3,4)]
        if memory:
            for i,k in enumerate(['DMA_H2D','STORE','LOAD','COMPUTE','DMA_D2H','BARRIER']):
                ops[i].update(kind=k,pe=0,bytes=5504 if i in (0,1,2,4) else 0,sample_bytes=256 if i in (1,2) else 0,address=65536 if i in (1,2) else 0,cycles=10 if i==3 else 0)
            edges=[dict(src=s,dst=d) for s,d in [(0,1),(1,2),(2,3),(2,4),(3,5),(4,5)]]
        write(g/'ops.csv',ops,fields);write(g/'deps.csv',edges,['src','dst'])
        write(g/'modes.csv',[dict(mode=m,local_bytes_per_cycle=l,global_bytes_per_cycle=v) for m,l,v in [('FULL_LOCAL',1536,0),('LOCAL_BIAS',1024,512),('GLOBAL_BIAS',512,1024),('FULL_GLOBAL',0,1536)]],['mode','local_bytes_per_cycle','global_bytes_per_cycle'])
        empty=out/'empty.trace';empty.write_text('')
        env=os.environ.copy();env.update(launch['controls']);env.pop('HB_DEEPSTACK_TIMING',None)
        env.update(HB_GRAPH=str(g),HB_OUT=str(out),POPNET_STATS_DIR=str(out),HB_PCIE_GBPS='55.04',HB_PCIE_LATENCY_NS='270')
        cmd=launch['command'].copy();cmd[0]=str(exe);cmd[cmd.index('-I')+1]=str(empty)
        with (out/'stdout.log').open('w') as log:subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
        return out,json.loads((out/'run_manifest.json').read_text())
    out,m=run('dma',True,binary)
    with (out/'dma_resources.csv').open(newline='') as f: rows=list(csv.DictReader(f))
    byid={int(r['op_id']):r for r in rows}
    assert len(rows)==3 and m['total_cycles']==500
    assert float(byid[0]['start'])==0 and float(byid[1]['start'])==100 and float(byid[2]['start'])==0
    assert float(byid[0]['done'])==370 and float(byid[1]['done'])==470 and float(byid[2]['done'])==370
    with (out/'events.csv').open(newline='') as f: events={int(r['id']):r for r in csv.DictReader(f)}
    assert float(events[4]['start'])==370 and float(events[3]['start'])==0
    new,nm=run('no_dma_new',False,binary);old,om=run('no_dma_old',False,Path(launch['command'][0]))
    assert nm['total_cycles']==om['total_cycles'] and (new/'events.csv').read_bytes()==(old/'events.csv').read_bytes()
    mem,mm=run('dma_memory_commit',True,binary,memory=True)
    with (mem/'events.csv').open(newline='') as f: me={int(r['id']):r for r in csv.DictReader(f)}
    for s,d in [(0,1),(1,2),(2,3),(2,4)]: assert float(me[d]['start'])>=float(me[s]['done'])
    assert mm['represented_mem_bytes']==11008 and mm['sampled_mem_bytes']==512
    with (mem/'bank_requests.csv').open(newline='') as f: br=list(csv.DictReader(f))
    assert {int(r['op_id']) for r in br}=={1,2}
    for r in br: assert float(me[int(r['op_id'])]['done'])>=float(r['callback_cycle'])
    payload={'status':'PASS','binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'checks':['same-direction bandwidth serialized','opposite directions concurrent','dependent compute waits for DMA','independent compute overlaps DMA','no-DMA events byte-identical to frozen baseline'], 'limitations':['page-level throughput/latency model, not packet-accurate PCIe','HB read/write and cache ownership must still be connected in workload lowering','64 pooled DMA credits abstract four queues times sixteen outstanding; no per-queue packet arbitration']}
    payload['checks'].append('DMA-HB write-read-compute chain preserves backend callbacks and byte accounting')
    payload['memory_commit_total_cycles']=mm['total_cycles']
    (base/'validation.json').write_text(json.dumps(payload,indent=2)+'\n');print(json.dumps(payload,indent=2))
if __name__=='__main__': main()
