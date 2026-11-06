"""Full-depth real-route decode paging DAG, baseline EP16 diagnostic.

Compute cycles and aggregated collectives are analytical proxies; not a
complete Sem-MoE/HiBand performance experiment.
"""
import argparse,csv,gzip,json,math
from collections import OrderedDict,Counter,defaultdict
from pathlib import Path
from paging_preflight import budget,PAGE,PINNED,HOST

FIELDS=['id','kind','task','phase','pe','bytes','sample_bytes','address','cycles','src','dst','scope','rank','inference_request_id']
def write(path,rows,fields):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--context',type=int,default=128);ap.add_argument('--batch',type=int,default=1);ap.add_argument('--steps',type=int,default=1);ap.add_argument('--microbatch-size',type=int,default=0);ap.add_argument('--partition-capacity-mib',type=int,default=512);ap.add_argument('--cohort-policy',default='fixed_source_order');ap.add_argument('--cohort-repeat',type=int,default=1);ap.add_argument('--placement',type=Path);ap.add_argument('--compute-profile',type=Path);ap.add_argument('--hiband',action='store_true');ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    placement=json.loads(args.placement.read_text()) if args.placement else None
    profile=json.loads(args.compute_profile.read_text()) if args.compute_profile else None
    source=args.root/f'results/routes_context{args.context}'; manifest=json.loads((source/'trace_manifest.json').read_text())
    cohorts=json.loads((args.root/'results/route_characterization/cohort_manifest.json').read_text())['cohorts']
    match=[x for x in cohorts if x['policy']==args.cohort_policy and x['repeat']==args.cohort_repeat and x['scale']==args.batch]
    if len(match)!=1:raise RuntimeError('cohort selection is not unique')
    selected=match[0]['request_ids'];request_owner={rid:i for i,rid in enumerate(selected)};routes=defaultdict(list)
    with gzip.open(source/'routing_trace.csv.gz','rt',newline='') as f:
        for r in csv.DictReader(f):
            step=int(r['position'])-args.context
            if r['request_id'] in selected and step<args.steps: routes[step,int(r['layer'])].append((r['request_id'],int(r['token_id']),int(r['expert'])))
    part=args.partition_capacity_mib*2**20;b=budget(args.context,args.batch,part=part);assert b['combined_capacity_possible']
    slots=b['cache_slots_per_partition'];start=part-slots*PAGE
    caches=[OrderedDict() for _ in range(16)];host=set();slot_of={};last_use={};slot_free={};stage_free={};dma_events=[];ops=[];deps=[];addresses=[]
    owner={(l,e):(int(placement[str(l)]['expert_to_rank'][str(e)]) if placement else e%16) for l in range(48) for e in range(128)}
    for rank in range(16):
        pages=[(l,e) for l in range(48) for e in range(128) if owner[l,e]==rank]
        for i,key in enumerate(pages):
            if i<slots:caches[rank][key]=True;slot_of[key]=i
            else:host.add(key)
    initial_host=len(host)*PAGE;assert initial_host<=HOST
    def op(kind,task,pe,nbytes=0,sample=0,address=0,cycles=0,src=-1,dst=-1,owner=-1):
        phase=('COMPUTE_BGA' if args.hiband and kind=='COMPUTE' and '_SwiGLU' in task else 'COMPUTE_BSA' if args.hiband and kind=='COMPUTE' else 'COMPUTE')
        scope=('local' if args.hiband and kind=='NET' and abs(src//4-dst//4)+abs(src%4-dst%4)<=1 else 'global') if kind=='NET' else 'local'
        i=len(ops);ops.append(dict(id=i,kind=kind,task=task,phase=phase,pe=pe,bytes=nbytes,sample_bytes=sample,address=address,cycles=cycles,src=src,dst=dst,scope=scope,rank=pe,inference_request_id=owner));return i
    def dep(s,d):
        if s is not None:deps.append(dict(src=s,dst=d))
    current_owner=-1
    def mem(kind,task,rank,nbytes,address,parent,tensor):
        assert nbytes>0 and 0<=address and address+nbytes<=part
        i=op(kind,task,rank,nbytes,min(4096,nbytes),address,owner=current_owner);dep(parent,i);addresses.append(dict(op_id=i,tensor=tensor,partition=rank,address=address,bytes=nbytes,sample_bytes=min(4096,nbytes),inference_request_id=current_owner));return i
    def join(task,ids):
        i=op('BARRIER',task,0)
        for p in ids:dep(p,i)
        return i
    micro=args.microbatch_size or args.batch;assert 1<=micro<=args.batch
    if profile:assert micro==1 and args.context in (128,512)
    groups=[selected[i:i+micro] for i in range(0,args.batch,micro)];wave_tails=[None]*len(groups);hits=misses=evictions=0
    for step in range(args.steps):
        for layer in range(48):
          all_rr=routes[step,layer];assert len(all_rr)==args.batch*8
          for wave,group in enumerate(groups):
            current_owner=request_owner[group[0]] if len(group)==1 else -1
            rr=[x for x in all_rr if x[0] in group];assert len(rr)==len(group)*8
            tag=f'S{step}L{layer}W{wave}';tail=wave_tails[wave];group_offset=sum(len(x) for x in groups[:wave]);nreq=len(group)
            ready=[]
            for rank in range(16):
                weight=mem('LOAD',f'{tag}_attention_weight_{rank}',rank,2048*(4096+512*2+4096)//2//16,(2*151936*2048//2//16)+layer*600000,tail,'nonexpert_weight')
                kvbase=50*2**20+layer*args.batch*(args.context+16)*128+group_offset*(args.context+16)*128
                kv=mem('LOAD',f'{tag}_KV_read_{rank}',rank,nreq*(args.context+step)*2*4*128*2//16,kvbase,tail,'KV')
                if profile:
                    c=profile['cycles'];attn_cycles=c['attention_qkv_tp16']+c['attention_output_tp16']+c[f'qk_ctx{args.context}_two_heads']+c[f'av_ctx{args.context}_two_heads']
                else:attn_cycles=math.ceil(nreq*(2048*(4096+512*2+4096)+2*32*128*(args.context+step+1))/(16*65536))
                comp=op('COMPUTE',f'{tag}_attention_{rank}',rank,cycles=attn_cycles)
                dep(weight,comp);dep(kv,comp)
                append=mem('STORE',f'{tag}_KV_append_{rank}',rank,nreq*128,kvbase+(args.context+step)*nreq*128,comp,'KV')
                ready.append(append)
            attention=join(f'{tag}_attention_collective_ready',ready)
            collective=[]
            for rank in range(16):
                n=op('NET',f'{tag}_attention_ring_aggregate_{rank}',rank,2*15*math.ceil(nreq*4096/16),src=rank,dst=(rank+1)%16);dep(attention,n);collective.append(n)
            router_ops=[]
            for rank in range(16):
                router=op('COMPUTE',f'{tag}_router_{rank}',rank,cycles=profile['cycles']['router_tp16'] if profile else 1);dep(collective[rank],router);router_ops.append(router)
            router_ready=join(f'{tag}_router_ready',router_ops)
            if placement:
                reqcounts=defaultdict(Counter)
                for req,token,e in rr:reqcounts[req][owner[layer,e]]+=1
                loads=[0]*16;request_rank={}
                for req in sorted(reqcounts,key=lambda q:(-sum(reqcounts[q].values()),q)):
                    choices=[r for r in range(16) if loads[r]<(nreq+15)//16]
                    r=max(choices,key=lambda x:(reqcounts[req][x],-loads[x],-x));request_rank[req]=r;loads[r]+=1
                flows=Counter((request_rank[req],owner[layer,e]) for req,token,e in rr)
            else:flows=Counter((token%16,e%16) for req,token,e in rr)
            arrivals=defaultdict(list)
            for (src,dst),count in flows.items():
                if src!=dst:
                    n=op('NET',f'{tag}_dispatch_{src}_{dst}',src,count*4096,src=src,dst=dst);dep(router_ready,n);arrivals[dst].append(n)
            expert_counts=Counter(e for req,token,e in rr);done_by_rank=defaultdict(list)
            for expert,count in sorted(expert_counts.items()):
                rank=owner[layer,expert];key=(layer,expert);cache=caches[rank];arrival=join(f'{tag}E{expert}_arrival',[router_ready]+arrivals[rank])
                if key in cache:hits+=1;cache.move_to_end(key);resident=arrival
                else:
                    misses+=1;assert key in host
                    victim,_=cache.popitem(last=False);slot=slot_of.pop(victim);evictions+=1
                    fetch=op('DMA_H2D',f'{tag}E{expert}_fetch',rank,PAGE);dep(arrival,fetch);dep(stage_free.get(rank),fetch)
                    victim_read=mem('LOAD',f'{tag}E{expert}_victim_read',rank,PAGE,start+slot*PAGE,last_use.get(victim),'expert_eviction')
                    evict=op('DMA_D2H',f'{tag}E{expert}_evict',rank,PAGE);dep(fetch,evict);dep(victim_read,evict)
                    resident=mem('STORE',f'{tag}E{expert}_commit',rank,PAGE,start+slot*PAGE,evict,'expert_page_commit')
                    stage_free[rank]=resident;host.remove(key);host.add(victim);assert len(host)*PAGE<=HOST
                    slot_of[key]=slot;cache[key]=True
                    dma_events.append(dict(fetch=fetch,evict=evict,commit=resident,page=list(key),victim=list(victim),rank=rank,slot=slot))
                slot=slot_of[key];load=mem('LOAD',f'{tag}E{expert}_weight_read',rank,PAGE,start+slot*PAGE,resident,'expert_weight');dep(slot_free.get((rank,slot)),load)
                expert_cycles=count*(profile['cycles']['expert_gate_up_one_token']+profile['cycles']['expert_down_one_token']) if profile else math.ceil(count*3*2048*768/65536)
                compute=op('COMPUTE',f'{tag}E{expert}_SwiGLU',rank,cycles=expert_cycles);dep(load,compute)
                last_use[key]=compute;slot_free[rank,slot]=compute;done_by_rank[rank].append(compute)
            combined=[]
            for (src,dst),count in flows.items():
                if src!=dst:
                    n=op('NET',f'{tag}_combine_{dst}_{src}',dst,count*4096,src=dst,dst=src)
                    for p in done_by_rank[dst]:dep(p,n)
                    combined.append(n)
            wave_tails[wave]=join(f'{tag}_residual_ready',combined+[p for v in done_by_rank.values() for p in v])
            if layer==47 and profile:
                heads=[]
                for rank in range(16):
                    h=op('COMPUTE',f'S{step}W{wave}_lm_head_{rank}',rank,cycles=profile['cycles']['lm_head_tp16']);dep(wave_tails[wave],h);heads.append(h)
                wave_tails[wave]=join(f'S{step}W{wave}_lm_head_ready',heads)
    assert all(0<=d['src']<d['dst']<len(ops) for d in deps), 'graph must be forward-only DAG'
    assert set(routes)=={(s,l) for s in range(args.steps) for l in range(48)}, 'unexpected route coverage'
    args.out.mkdir(parents=True,exist_ok=True)
    write(args.out/'ops.csv',ops,FIELDS);write(args.out/'deps.csv',deps,['src','dst']);write(args.out/'address_manifest.csv',addresses,list(addresses[0]))
    write(args.out/'modes.csv',[dict(mode=m,local_bytes_per_cycle=l,global_bytes_per_cycle=g) for m,l,g in [('FULL_LOCAL',1536,0),('LOCAL_BIAS',1024,512),('GLOBAL_BIAS',512,1024),('FULL_GLOBAL',0,1536)]],['mode','local_bytes_per_cycle','global_bytes_per_cycle'])
    limitations=['diagnostic reproduction; not formal Sem-MoE/HiBand SOTA result','microbatch page-replacement order is a fixed deterministic schedule, not an optimized online policy','aggregated ring collective proxy, not chunk-accurate overlap','initial HB pages deterministically resident; initialization excluded and not called cold-start','ideal W4 storage with BF16-derived routes; quantization metadata unresolved','fixed 4096-byte stratified Ramulator sample per memory operation; sampling convergence beyond 16 transactions is not yet verified','host memory service and staging SRAM bandwidth not yet modeled','embedding and elementwise/vector execution omitted from diagnostic graph']
    if args.partition_capacity_mib!=512:limitations.append(f'expanded-capacity overlay: {args.partition_capacity_mib} MiB per partition; not frozen v3.6 capacity')
    if not profile:limitations.append('analytical peak-MAC compute proxy, not profiled operator timing')
    else:limitations+=profile['assumptions']
    result=dict(status='DIAGNOSTIC_GRAPH_READY',operations=len(ops),dependencies=len(deps),context=args.context,batch=args.batch,steps=args.steps,microbatch_size=micro,microbatches=len(groups),cohort_policy=args.cohort_policy,cohort_repeat=args.cohort_repeat,partition_capacity_mib=args.partition_capacity_mib,capacity_class=('frozen_v3_6' if args.partition_capacity_mib==512 else 'expanded_capacity_overlay'),compute_timing=('scalesim_shape_profile' if profile else 'analytical_proxy'),request_ids=selected,inference_request_id_map=request_owner,bank_contention_owner_valid=(micro==1),scheme=('hiband_' if args.hiband else '')+('sem_moe' if placement else 'baseline_ep'),budget=b,initial_host_bytes=initial_host,hits=hits,misses=misses,evictions=evictions,page_operations=dma_events,limitations=limitations)
    (args.out/'graph_manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('page_operations','limitations')},indent=2))
if __name__=='__main__':main()
