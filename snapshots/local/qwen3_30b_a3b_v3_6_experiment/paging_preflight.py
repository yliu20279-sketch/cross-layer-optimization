"""Capacity and LRU demand audit; NOT a latency simulator."""
import argparse,csv,gzip,json
from collections import OrderedDict,defaultdict
from pathlib import Path

PART=512*2**20; HOST=8*2**30; PAGE=3*2048*768//2
TOTAL_W4=30532331520//2
PINNED=(2*151936*2048+48*(2048*4096+2*2048*512+4096*2048+2048*128+32*128+4*128+2*2048)+2048)//2

def budget(context,batch,part=PART,host=HOST):
    kv=48*(context+16)*batch*2*4*128*2
    base=(PINNED+15)//16+(kv+15)//16+32*2**20
    slots=min(384,max(0,(part-base)//PAGE))
    return dict(context=context,batch=batch,kv_bytes=kv,pinned_W4_bytes=PINNED,expert_page_bytes=PAGE,cache_slots_per_partition=slots,partition_peak_bytes=base+slots*PAGE,HB_capacity_bytes=16*part,host_capacity_bytes=host,total_W4_bytes=TOTAL_W4,combined_minimum_bytes=TOTAL_W4+kv+16*32*2**20,combined_capacity_possible=TOTAL_W4+kv+16*32*2**20<=16*part+host,full_host_backing_fits=TOTAL_W4<=host)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--trace',type=Path); ap.add_argument('--out',type=Path,required=True); args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    budgets=[budget(c,b) for c in (128,512,2048) for b in (1,2,4,8,16)]
    audit={'status':'CAPACITY_AUDIT_ONLY','budgets':budgets,'limitations':['W4 is ideal packed storage, not a quantized model execution','Full host backing exceeds frozen host DRAM; exclusive tiering or explicit storage service is required','LRU access counts do not establish page transfer time or Bank penalty']}
    if args.trace:
        waves=defaultdict(set)
        with gzip.open(args.trace,'rt',newline='') as f:
            for r in csv.DictReader(f): waves[int(r['position']),int(r['layer'])].add(int(r['expert']))
        slots=budget(128,1)['cache_slots_per_partition']; caches=[OrderedDict() for _ in range(16)]; hits=misses=evictions=0
        for (_,layer),experts in sorted(waves.items()):
            for expert in sorted(experts):
                rank=expert%16; key=(layer,expert); cache=caches[rank]
                if key in cache: hits+=1; cache.move_to_end(key)
                else:
                    misses+=1
                    if len(cache)==slots: cache.popitem(last=False); evictions+=1
                    cache[key]=True
        audit['smoke_LRU_demand']={'hits':hits,'misses':misses,'evictions':evictions,'demand_H2D_bytes':misses*PAGE,'placement':'round-robin EP16 diagnostic only, not Sem-MoE','initial_cache':'cold','steps':len({p for p,l in waves})}
    (args.out/'paging_preflight.json').write_text(json.dumps(audit,indent=2)+'\n'); print(json.dumps(audit,indent=2))
if __name__=='__main__': main()
