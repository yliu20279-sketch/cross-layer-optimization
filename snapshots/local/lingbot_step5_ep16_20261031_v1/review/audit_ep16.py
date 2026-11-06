import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='4'
import pathlib,json,hashlib,numpy as np,torch,time
R=pathlib.Path(__file__).resolve().parent;P=R.parent/'lingbot_step4_bitexact_20261029_v4';F=P/'full_layer_stagewise_v1';G=R.parent/'lingbot_step3_capture_20261028_v1';checks=[];torch.set_num_threads(4)
def ck(n,b):checks.append(dict(name=n,passed=bool(b)));assert b,n
def sha(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
r=json.loads((R/'FUNCTIONAL_RESULT.json').read_text());ck('functional',r['status']=='PASS_LIMITED_EP16_FULL_ROUTE_SERIALIZATION_FFN_RESTORE' and all(x['passed'] for x in r['checks']));msgs=json.loads((R/'MESSAGES.json').read_text());summary=[]
manifest=json.loads((G/'FIXTURE_MANIFEST.json').read_text())
for branch,S in [('cond',49883),('uncond',48986)]:
 D=F/branch;ids=np.load(D/'autonomous_ids.npy');weights=np.load(D/'autonomous_weights.npy');out=np.load(R/(branch+'_returned_slots.npy'),mmap_mode='r');original=np.load(D/'expert_slots_bf16.npy',mmap_mode='r');count=0
 for i in range(0,S*8,1024):ck('slot_bits_'+branch+'_'+str(i),np.array_equal(out[i:i+1024],original[i:i+1024]))
 for m in [m for m in msgs if m['branch']==branch]:
  token,slot=np.nonzero((ids==m['expert']) & ((np.arange(S)%16)[:,None]==m['origin']));ck('message_count',len(token)==m['assignments'] and m['owner']==m['expert']%16 and m['local']==(m['owner']==m['origin']) and m['dispatch_bytes']==m['return_bytes']==len(token)*4112);count+=len(token)
 ck('assignment_conservation_'+branch,count==S*8)
 rel='fixtures/full_on_s00_'+branch+'_L00_ffn_output.pt';meta=next(x for x in manifest if x['file']==rel);ck('gold_SHA_'+branch,sha(G/rel)==meta['file_sha256']);gold=torch.load(G/rel,weights_only=True)[0];shared=np.load(D/'shared_bf16.npy',mmap_mode='r');bad=0
 for i in range(0,S,64):
  j=min(i+64,S);v=(np.asarray(out[i*8:j*8]).astype(np.uint32)<<16).view(np.float32).reshape(j-i,8,2048);prod=torch.from_numpy(v)*torch.from_numpy(weights[i:j,:,None]);streams=[prod[:,k]+prod[:,k+4] for k in range(4)];z=streams[0]
  for k in range(1,4):z=z+streams[k]
  sf=torch.from_numpy((np.asarray(shared[i:j]).astype(np.uint32)<<16).view(np.float32));actual=(z.bfloat16().float()+sf).bfloat16();b=int(torch.count_nonzero(actual.view(torch.int16)!=gold[i:j].view(torch.int16)));bad+=b;ck('independent_torch_FFN_'+branch+'_'+str(i),b==0)
 summary.append(dict(branch=branch,rows=S,slot_elements=S*8*2048,FFN_elements=S*2048,bit_mismatches=bad))
records=json.loads((R/'NOC_RECORDS.json').read_text());delay=[list(map(int,l.split())) for l in (R/'delayInfo.txt').read_text().splitlines()];ck('noc_count',len(records)==len(delay)>0);remaining={(x['id']*500,x['src'],x['dst']):x for x in records}
for line in delay:
 key=tuple(line[:3]);ck('delay_record_identity',key in remaining);v=remaining.pop(key);ck('flits',line[5]==v['flits'] and v['payload_bytes']==4112);ck('nonnegative_delay',line[6]>=0)
ck('all_records_returned',not remaining)
r=dict(status='PASS_LIMITED_EP16_FULL_FUNCTIONAL_SELECTED_NOC_INDEPENDENT_AUDIT',check_count=len(checks),checks=checks,summary=summary,noc_records=len(records),failures=[],target_GPU_count=0,whole_step5=False,scope='full EP16 CPU serialization and same-input expert output restore; selected open-loop real-byte PopNet; no coupled target compute/NoC DAG')
(R/'INDEPENDENT_AUDIT.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='checks'}))
