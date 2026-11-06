import json,hashlib,ctypes as C,csv,re,collections,math,subprocess,tarfile
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;B=R.parent
def j(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for n,h in j(R/'FREEZE.json').items():assert sha(R/n)==h
for n,h in j(R/'EXTERNAL_DEPENDENCIES.json').items():assert sha(Path(n))==h
v=j(R/'CASES.json')[0];plan=(R/'data/plan.txt').read_text().splitlines()[0].split();_,_,_,shard,offset,wb,xp,gp=plan
x=np.fromfile(xp,dtype='<u2')
with open(shard,'rb') as f:f.seek(int(offset));w=np.frombuffer(f.read(int(wb)),dtype='<u2').copy()
assert hashlib.sha256(w.tobytes()).hexdigest()==v['weight_sha256']
assert hashlib.sha256(x.tobytes()).hexdigest()==v['input_sha256']
lib=C.CDLL(str(B/'swe_qwen3_step3_four_gates_20261028_v1/libsource_gemm_v2.so'));lib.source_gemm.argtypes=[C.c_void_p]*3+[C.c_int]*3
reference=np.empty(768,dtype='<f4');assert lib.source_gemm(x.ctypes.data,w.ctypes.data,reference.ctypes.data,1,768,2048)==0
results=[]
for iteration in [1,2]:
 D=R/('case%d'%iteration);N=D/'N00';cpu=j(D/'CPU_PASS.json');low=j(N/'LOWERING.json');actual=j(N/'RESULT.json')
 assert cpu['host_mapped_bytes']==61066575648 and cpu['decoded_elements']==1574912 and cpu['encoded_elements']==768
 assert (D/'CPU_BF16.bin').read_bytes()==Path(gp).read_bytes()
 assert (D/'CPU_RAW_FP32.bin').read_bytes()==reference.tobytes()==(N/'actual_fp32.bin').read_bytes()
 assert (D/'CPU_EXPANDED_X.bin').read_bytes()==(x.astype('<u4')<<16).tobytes()
 assert (D/'CPU_EXPANDED_W.bin').read_bytes()==(w.astype('<u4')<<16).tobytes()
 assert actual['expanded_weight_sha256']==sha(D/'CPU_EXPANDED_W.bin') and actual['expanded_input_sha256']==sha(D/'CPU_EXPANDED_X.bin')
 assert actual['metadata_ready']<=low['begin']<=low['complete']<=actual['compute_done']<=actual['returned']
 assert (low['mul_ops'],low['add_ops'],low['reduce_ops'],low['native_compute_events'],low['weight_versions'])==(1572864,1573632,48384,202752,12)
 assert low['compute_cycles']==202752 and low['bank_service_cycles']>0
 assert all(v>0 for v in low['read_beats']+low['write_beats'])
 rows=list(csv.DictReader((N/'SRAM_ROWS.csv').open()));assert len(rows)==768
 for i,v in enumerate(rows):
  assert int(v['row'])==i and int(v['weight_version'])==i//64+1 and int(v['start'])<=int(v['weight_last_reader'])<=int(v['done'])
  if i:assert int(rows[i-1]['done'])<=int(v['start'])
 assert j(D/'PHASE2_PASS.json')['state']=='PASS_LIMITED_CODEC_GATE_SRAM_REPLAY'
 bench=[list(map(int,s.split())) for s in (D/'bench.txt').read_text().splitlines()];delay=[list(map(int,s.split())) for s in (D/'delayInfo.txt').read_text().splitlines()]
 assert collections.Counter((v[0],v[2],v[3],v[5]) for v in bench)==collections.Counter(tuple(v[:4]) for v in delay)
 fb=list(csv.DictReader((D/('noc_feedback_round%d.csv'%iteration)).open()));assert len(fb)==len(bench) and all(int(v['profile_applied'])==iteration-1 for v in fb)
 clock=list(csv.DictReader((R/'run1'/('clock_round%d.csv'%iteration)).open()));transport=(D/'transport_bench.txt').read_text().splitlines();assert len(clock)==2*len(transport)
 by=collections.defaultdict(list);rates=collections.defaultdict(list)
 for v in clock:
  key=(int(v['src']),int(v['dst']),int(v['descriptor']));rate=float(v['clock_ratio']);ns=float(v['global_ns']);assert round(ns*rate)==int(float(v['native_ticks']))
  assert rate in ([1,2.5] if 48 in key[:2] else [1]);by[key].append(ns);rates[key].append(rate)
 domains=list(csv.DictReader((D/('domain_service_round%d.csv'%iteration)).open()));groups=collections.defaultdict(list)
 for v in domains:groups[(int(v['src']),int(v['dst']),int(v['descriptor']))].append(v)
 for key,vs in groups.items():
  assert len(by[key])==2*len(vs)
  for i,v in enumerate(vs):assert float(v['ready'])==math.ceil(max(by[key][2*i:2*i+2])) and sorted(rates[key][2*i:2*i+2])==([1,2.5] if 48 in key[:2] else [1,1])
 results.append(dict(round=iteration,strict_FP32_elements=768,strict_BF16_elements=768,CPU_decode_elements=1574912,CPU_encode_elements=768,primitive_events=low['native_compute_events'],primitive_cycles=low['compute_cycles'],SRAM_bank_service_cycles=low['bank_service_cycles'],SRAM_read_beats=low['read_beats'],SRAM_write_beats=low['write_beats'],horizontal_records=len(bench),clock_observations=len(clock)))
statuses=list(map(int,re.findall(r'terminate with status = (\d+)',(R/'RUN.log').read_text())));assert len(statuses)==10 and all(v==0 for v in statuses)
assert j(R/'RUN_EXIT.json')['returncode']==0
out=dict(state='PASS_LIMITED_ACTUAL_CPU_CODEC_FP32_GATE_SRAM_TWO_ROUND',rounds=results,original_BF16=True,host_GiB=128,HB_GiB=8,active_HB_MiB=512,target_GPU=0,SRAM_ports_mapping='research overlay not canonical specification',cache_maintenance_timing_certified=False,full_layers_opcode_costs_complete=False,full_steps_1_7=False)
(R/'INDEPENDENT_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out),flush=True)
