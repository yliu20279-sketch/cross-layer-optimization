import os
os.environ['OMP_NUM_THREADS']='4';os.environ['MKL_NUM_THREADS']='4'
import pathlib,json,hashlib,numpy as np,torch
R=pathlib.Path(__file__).resolve().parent;G=R.parent/'lingbot_step3_capture_20261028_v1';P=R.parent/'lingbot_step4_bitexact_20261029_v4';torch.set_num_threads(4);checks=[];rounds=[]
def ck(n,b):checks.append(dict(name=n,passed=bool(b)));assert b,n
for case in sorted(R.glob('case*')):
 if not case.is_dir():continue
 sent={};received={};elements=0
 for rank in range(16):
  D=case/('N%02d'%rank);s=json.loads((D/'PASS.json').read_text());ck('worker',s['state']=='PASS_FRESH_TP_EP_CONTINUOUS_DOMAIN' and not s['CUDA_initialized']);ev=json.loads((D/'EVENTS.json').read_text());ck('worker_checks',all(x['passed'] for x in json.loads((D/'CHECKS.json').read_text())));prev=0
  for e in ev:
   ck('clock',e['done']>=e['start']>=prev);prev=e['done']
   if e['kind']=='send':sent[(rank,e['peer'],e['label'])]=e
   if e['kind']=='recv':received[(e['peer'],rank,e['label'])]=e
   if e['kind']=='HB':ck('HB_bounds',0<=e['addr'] and e['addr']+e['bytes']<=512*2**20)
  tiles=json.loads((D/'TILES.json').read_text())
  for branch,S in [('cond',49883),('uncond',48986)]:
   tr=[v for v in tiles if v['branch']==branch];ck('coverage',len(tr)==(S+63)//64 and all(v['begin']==i*64 and v['end']==min((i+1)*64,S) for i,v in enumerate(tr)))
   for stage in ['attention_output','ffn_input','ffn_output','post_ffn_norm','block_output']:
    a=np.load(D/(branch+'_'+stage+'.npy'),mmap_mode='r');g=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_'+stage+'.pt'),weights_only=True)[0,rank::16].float().numpy();ck(branch+stage,np.array_equal(a.view(np.uint32),g.view(np.uint32)));elements+=a.size
   a=np.load(D/(branch+'_core.npy'),mmap_mode='r');g=torch.load(P/'external_attention_attempt1'/(branch+'_core.pt'),weights_only=True)[0,:,rank].float().numpy();ck(branch+'_head_core',np.array_equal(a.view(np.uint32),g.view(np.uint32)));elements+=a.size
 ck('paired_messages',sent.keys()==received.keys())
 for k,a in sent.items():b=received[k];ck('payload',a['bytes']==b['bytes'] and a['sha256']==b['sha256'] and b['done']>=a['done'])
 ck('phase2',(case/'PHASE2_PASS.json').exists());rounds.append(dict(case=case.name,checked_BF16_elements=elements,logical_messages=len(sent),transport_bytes=sum(e['bytes'] for e in sent.values()),PopNet_records=json.loads((case/'PHASE2_PASS.json').read_text())['records']))
ck('two_rounds',len(rounds)==2)
r=dict(state='PASS_LIMITED_NEW_KV_TP_EP_CONTINUOUS_PAYLOAD',checks=checks,check_count=len(checks),rounds=rounds,target_GPU_count=0,whole_step5=False,continuous_full_layer_timing=False,limits=['new K/V/Q projections, fresh full attention/O/router/expert execution in one domain','old K/V/routes used only for strict comparisons, no intermediate checkpoint input','CPU software payload math, generic vector proxies and DMA SRAM staging','no complete host/PCIe or per-op memory/ISA costs']);(R/'INDEPENDENT_AUDIT.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='checks'}))
