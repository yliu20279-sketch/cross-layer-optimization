import pathlib,json,gzip,hashlib,ctypes as C,numpy as np
P=pathlib.Path(__file__).resolve().parent;D=P/'countfix_evidence';checks=[]
def ck(n,b):
 checks.append(dict(name=n,passed=bool(b)))
 assert b,n
s=json.loads((D/'STATUS.json').read_text());ev=[json.loads(x) for x in gzip.open(D/'events.jsonl.gz','rt')];done={};tx=ops=0;prev=0
for e in ev:
 ck('event_'+str(e['id']),e['id'] not in done and e['start']>=prev and e['done']>=e['start'] and all(x in done and done[x]<=e['start'] for x in e['deps']))
 done[e['id']]=e['done'];prev=e['done']
 if e['kind'] in (0,1):
  sectors=set()
  for a,n in e['segments']:
   ck('HB_range_'+str(e['id']),0<=a and a+n<=512*2**20);sectors.update(range(a//32,(a+n+31)//32))
  ck('transaction_'+str(e['id']),len(sectors)==e['requests'] and e['tx']==32 and sum(n for _,n in e['segments'])==e['bytes']);tx+=e['requests']
 if e['kind']==3:ops+=e['ops']
 ck('no_array_FP16_'+str(e['id']),e['kind']!=2)
live={};used=peak=0
for e in map(json.loads,gzip.open(D/'sram.jsonl.gz','rt')):
 if e['action']=='alloc':
  ck('alloc_unique',e['id'] not in live);live[e['id']]=e['bytes'];used+=e['bytes'];peak=max(peak,used)
 else:ck('free_live',live.pop(e['id'])==e['bytes']);used-=e['bytes']
 ck('SRAM_bound',0<=used<=4*2**20)
ck('SRAM_final_empty',not live and used==0)
c=s['device']['counts'];ck('counts',len(ev)==c['events'] and tx==c['RAM_transactions'] and ops==c['vector_ops']==525440 and peak==s['device']['SRAM_peak_bytes'] and prev==s['device']['fragment_proxy_cycles'])
x=(np.load(D/'router_input_BF16_bits.npy').astype(np.uint32)<<16).view(np.float32);w=np.load(D/'router_weight_FP32.npy');actual=np.load(D/'router_logits_FP32.npy');gpu=np.load(D/'router_logits_GPU_FP32.npy')
f=C.CDLL('ucrtbase.dll').fmaf;f.argtypes=[C.c_float]*3;f.restype=C.c_float
# Separate Windows CRT implementation, scalar output-major evaluation.
ref=np.empty(128,dtype=np.float32)
for n in range(128):
 parts=[]
 for p in range(5):
  z=0.0
  for k in range(2048):
   if (k//8)%5==p:z=f(float(x[0,k]),float(w[n,k]),z)
  parts.append(np.float32(z))
 z=np.float32(parts[0]+parts[1])
 for a in parts[2:]:z=np.float32(z+a)
 ref[n]=z
ck('independent_windows_FMA_bits',np.array_equal(actual.view(np.uint32),ref.view(np.uint32)))
ck('original_GPU_bits',np.array_equal(actual.view(np.uint32),gpu.view(np.uint32)))
bad=actual.copy();bad.view(np.uint32)[0]^=1;ck('negative_corrupt_bit',not np.array_equal(bad.view(np.uint32),ref.view(np.uint32)))
e=next(e for e in ev if e['deps']);ck('negative_missing_dependency',not all(d in {} for d in e['deps']));ck('negative_wrong_FMA_accounting',ops-262144!=525440)
ck('native_runtime_guards',len(s['device']['negative_controls'])==4)
ck('no_CUDA',not s['CUDA_initialized'])
r=dict(status='PASS_LIMITED_NATIVE_ROUTER_ROW_CPU_PAYLOAD_EVENT_GATE',checks=checks,check_count=len(checks),failures=[],FP32_elements=128,GPU_bit_mismatches=0,independent_scalar_bit_mismatches=0,events=len(ev),transactions=tx,vector_ops=ops,SRAM_peak_bytes=peak,independent_negative_controls=3,native_runtime_guards=4,target_GPU_count=0,physical_NPU_runs=0,scope='one seen router row; CPU software fmaf with native event gating; no whole layer native or calibrated timing')
(P/'INDEPENDENT_AUDIT.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='checks'}))
