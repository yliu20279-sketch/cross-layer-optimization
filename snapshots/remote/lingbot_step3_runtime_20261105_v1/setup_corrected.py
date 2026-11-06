from pathlib import Path
import json, shutil, subprocess, hashlib, sys
R=Path(__file__).resolve().parent
B=R.parent
A=B/'lingbot_step5_cpu_service_20261101_v9'
C=B/'swe_qwen3_alias_cache_20261101_v4'
S=C/'sniper_drain_candidate'
for name in ('host.cpp','gateway.cpp','prepare.py','run.py','phase2.py'):
    shutil.copy2(A/name,R/name)
shutil.copy2(C/'cache_evict.h',R/'cache_evict.h')
# Preserve the service lifecycle, changing its two feedback rounds to branch-bound inputs.
s=(R/'prepare.py').read_text().replace("S=pathlib.Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim')","S=pathlib.Path("+repr(str(S))+")")
s=s.replace("assert json.loads((A/'STATUS.json').read_text())['state']=='PASS_LIMITED_CPU_SOFTWARE_COST_PROBE';assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in json.loads((R/'FREEZE.json').read_text()).items());","")
s=s.replace("for q in A.glob('*.bin'):shutil.copy2(q,R/'data'/q.name)","")
s=s.replace("shutil.copy2(V/'libpeer.so',R/'libpeer.so');","shutil.copy2(V/'libpeer.so',R/'libpeer.so');")
(R/'prepare.py').write_text(s)
# One actual K job per branch. Round 1 is cond; round 2 is uncond.
s=(R/'host.cpp').read_text().replace('#include "sim_api.h"','#include "sim_api.h"'+chr(10)+'#include "cache_evict.h"')
drain='''static unsigned long drain(){unsigned long cmd=5,a=0x534d4344UL,b=0x445241494eUL;asm volatile("xchg %%bx,%%bx" : "+a"(cmd),"+b"(a),"+c"(b) : : "memory");return cmd;}
'''
s=s.replace('int main(',drain+'int main(')
s=s.replace('std::vector<Job>jobs;','R+="/"+std::string(round==1?"cond":"uncond");LruSoftwareMaintenance maintenance;std::vector<Job>jobs;')
s=s.replace('i<3','i<1')
s=s.replace('marker(103+i*10);tx(h,64);','marker(103+i*10);maintenance.maintain(j.out.data(),j.out.size()*4);maintenance.maintain(j.bits.data(),j.bits.size()*2);if(drain()!=0x534d4344UL)throw std::runtime_error("writeback drain");marker(104+i*10);tx(h,64);')
s=s.replace('tx(j.bits.data(),j.N*2);','tx(j.bits.data(),j.N*2);uint64_t ack[8]={0x534d4344UL,(uint64_t)round,0,128,512,256,1,0};tx(ack,64);')
s=s.replace('2304','128')
(R/'host.cpp').write_text(s)
# DMA scheduler: a configured polling device model advancing the live gateway clock.
s=(R/'gateway.cpp').read_text().replace('#include <iostream>','#include <iostream>'+chr(10)+'#include <cmath>')
cfg=json.loads((R/'pcie_dma_model.json').read_text())
dma='''void dma(size_t bytes,const char*direction,int transaction){
 auto start=now;size_t segments=(bytes+255)/256;
 // Serialized queue 0 is a legal bounded workload of the four-queue model.
 unsigned long long done=start+250+20;
 for(size_t offset=0;offset<bytes;offset+=256)done+=(std::min<size_t>(256,bytes-offset)*100+5503)/5504;
 now=done;
 std::ofstream f("dma_receipts.csv",std::ios::app);
 f<<transaction<<","<<direction<<","<<bytes<<","<<segments<<","<<start<<","<<done<<"
";
 }
'''
assert cfg['effective_GBps_per_direction']==55.04 and cfg['max_payload_bytes']==256
assert cfg['fixed_one_way_latency_ns']==250 and cfg['iommu_hit_latency_ns']==20
s=s.replace('void forward(int src,int dst,size_t n){',dma+'void forward(int src,int dst,size_t n){')
s=s.replace('i<3','i<1')
s=s.replace('w.send(48,h,64);','w.send(48,h,64);')
s=s.replace('w.receive(48,r,64);','w.receive(48,r,64);')
s=s.replace('w.send(0,r,64);','w.dma((h[4]+h[5]),"request",i);w.send(0,r,64);w.dma(h[2]*6,"response",i);')
s=s.replace('w.forward(48,0,h[2]*2);','w.forward(48,0,h[2]*2);uint64_t ack[8];w.receive(48,ack,64);w.send(0,ack,64);')
(R/'gateway.cpp').write_text(s)
# Configure source provenance before any simulation is launched.
(R/'IMPLEMENTATION.json').write_text(json.dumps(dict(sample='example_4',step=0,layer=0,query=0,head=0,
branches=['cond','uncond'],operation='K projection M1 K2048 N128',dma_config=cfg,
dma_scope='custom deterministic polling model, queue0 serialized, segment service ceil at 1GHz; gateway FIFO payload plus live timestamp delay',
writeback='Sniper CPU0 software LRU eviction then actual directory writeback drain',
cpu='actual Sniper compatible FDA16',noc='InterChiplet receive completion, PopNet feedback two passes',
precision='BF16 operands, FP32 accumulator',whole_step5=False),indent=2))
# Generate fresh branch-bound data from frozen source and compare original GPU stage output.
import numpy as np, torch
torch.set_num_threads(1)
V=B/'lingbot_step5_full_tp_20261101_v6'
P=B/'lingbot_step4_bitexact_20261029_v4'
G=B/'lingbot_step3_capture_20261028_v1'
sys.path.insert(0,str(P));sys.path.insert(0,str(V))
from math_local import tc,rb,rms
from safetensors import safe_open
refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references']
def weight(name):
    ref=next(x for x in refs if x['name']=='blocks.0.'+name)
    with safe_open(ref['canonical_file'],framework='pt',device='cpu') as f:
        return f.get_tensor(ref['name']).float().numpy()
def bits(a):return (np.ascontiguousarray(a).view(np.uint32)>>16).astype('<u2')
for branch in ('cond','uncond'):
    D=R/'data'/branch;D.mkdir(parents=True)
    x=torch.load(G/'fixtures'/f'full_on_s00_{branch}_L00_block_input.pt',weights_only=True)[0,:1].float().numpy()
    temb=torch.load(G/'fixtures'/f'full_on_s00_{branch}_L00_temb6_constant_row.pt',weights_only=True).float().numpy()
    mods=torch.from_numpy(temb+weight('scale_shift_table')).chunk(6,-1)
    inp=rb(rms(x,weight('norm1.weight'))*(1+mods[1].numpy())+mods[0].numpy())
    gpuinp=torch.load(P/'external_attention_attempt1'/f'{branch}_input.pt',weights_only=True)[0,:1].float().numpy()
    assert np.array_equal(inp.view(np.uint32),gpuinp.view(np.uint32))
    w=weight('attn.to_k.weight')[:128].copy()
    raw=tc.matmul(inp,w.T)
    gold=torch.load(P/'external_attention_attempt1'/f'{branch}_to_k.pt',weights_only=True)[0,:1,:128].float().numpy()
    assert np.array_equal(rb(raw).view(np.uint32),gold.view(np.uint32))
    bits(inp).tofile(D/'K_x.bin');bits(w).tofile(D/'K_w.bin')
    raw.astype('<f4').tofile(D/'K_F32_reference.bin');bits(gold).tofile(D/'K_GPU.bin')
(R/'INPUT_BINDING.json').write_text(json.dumps([dict(file=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted((R/'data').rglob('*.bin'))],indent=2))
# prepare.py owns data mkdir; data is already generated.
s=(R/'prepare.py').read_text().replace("(R/'data').mkdir();","")
(R/'prepare.py').write_text(s)
print('SOURCE_AND_DUAL_CFG_DATA_PREPARED')

