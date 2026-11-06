import os
os.environ['OMP_NUM_THREADS']='4';os.environ['MKL_NUM_THREADS']='4'
import torch
torch.set_num_threads(4);torch.set_num_interop_threads(1)
import pathlib,json,hashlib,numpy as np,torch
R=pathlib.Path(__file__).resolve().parent;G=R.parent/'lingbot_step3_capture_20261028_v1';checks=[]
def ck(n,b):checks.append(dict(name=n,passed=bool(b)));assert b,n
allround=[]
for case in sorted(R.glob('case*')):
 if not case.is_dir():continue
 sent={};received={};total=0
 for rank in range(16):
  D=case/('N%02d'%rank);s=json.loads((D/'PASS.json').read_text());ck('worker_pass',s['state']=='PASS_SELECTED_CONNECTED_TP_EP_CPU_PAYLOAD_NATIVE_GATE' and not s['CUDA_initialized']);workerchecks=json.loads((D/'CHECKS.json').read_text());ck('worker_checks',all(v['passed'] for v in workerchecks));events=json.loads((D/'EVENTS.json').read_text());prev=0
  for e in events:
   ck('event_clock',e['done']>=e['start']>=prev);prev=e['done']
   if e['kind']=='send':sent[(rank,e['peer'],e['label'])]=e
   if e['kind']=='recv':received[(e['peer'],rank,e['label'])]=e
   if e['kind']=='HB':ck('HB_bound',0<=e['addr'] and e['addr']+e['bytes']<=512*2**20)
  for branch,S in [('cond',49883),('uncond',48986)]:
   idx=np.r_[0:32,S-32:S];local=idx[idx%16==rank];receipt=json.loads((D/(branch+'_PASS.json')).read_text());ck('indices',receipt['query_indices']==local.tolist())
   for name in ['ffn_input','ffn_output','post_ffn_norm','block_output']:
    actual=np.load(D/(branch+'_'+name+'.npy'));gold=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_'+name+'.pt'),weights_only=True)[0,local].float().numpy();ck(branch+name,np.array_equal(actual.view(np.uint32),gold.view(np.uint32)));total+=actual.size
 ck('send_receive_sets',sent.keys()==received.keys())
 for k,a in sent.items():
  b=received[k];ck('payload_SHA',a['sha256']==b['sha256'] and a['bytes']==b['bytes']);ck('arrival_causality',b['done']>=a['start'])
 ck('phase2_pass',(case/'PHASE2_PASS.json').exists());allround.append(dict(case=case.name,checked_elements=total,logical_messages=len(sent),transport_bytes=sum(e['bytes'] for e in sent.values()),PopNet_records=json.loads((case/'PHASE2_PASS.json').read_text())['records']))
ck('two_rounds',len(allround)==2)
r=dict(state='PASS_LIMITED_DUALCFG_SELECTED_CONNECTED_TP_EP_TWO_ROUNDS',checks=checks,check_count=len(checks),rounds=allround,target_GPU_count=0,host_GiB=128,HB_GiB=8,whole_step5=False,limits=['64 queries per branch, full real K/V','CPU payload math with generic vector proxies','previous autonomous full-batch route counts bound as workload prerequisite','no Sniper host/PCIe costs','actual HB/SRAM staging audited separately; per-operator SRAM Bank cost and complete target layer remain incomplete']);(R/'INDEPENDENT_AUDIT.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='checks'}))
