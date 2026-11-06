import json,hashlib,shutil,subprocess,ast
from pathlib import Path
B=Path('/mnt/sda1/h3240101068')
V=B/'swe_qwen3_lifetime_owned_20261103_v8_ackfix'
C=B/'swe_qwen3_lifetime_owned_20261102_v8'
R=B/'swe_qwen3_lifetime_owned_20261105_v8_phasefix'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8388608):h.update(b)
 return h.hexdigest()
def j(p):return json.loads(p.read_text())
def put(p,x):p.write_text(json.dumps(x,indent=2))
R.mkdir()
original=j(V/'FREEZE.json')
for n,h in original.items():
 assert sha(V/n)==h,n
 if n=='WORKER_FREEZE.json':continue
 (R/n).parent.mkdir(parents=True,exist_ok=True)
 shutil.copy2(V/n,R/n)
for n in ['EXP16_ALL_FP32.bin','SILU_ALL_BF16.bin','oracle_cpu']:
 (R/n).symlink_to((V/n).resolve())
for n in ['replay_backend.py','control_replay.py','libcpu_probe.so']:
 shutil.copy2(C/n,R/n)
for n in ['unified_full.yml','CPU_BUILD_COMMAND.json','BRIDGE_BUILD_COMMAND.json']:
 p=R/n;p.write_text(p.read_text().replace(str(V),str(R)))
p=R/'replay_backend.py'
s=p.read_text();needle="self.phase=phase;old="
assert s.count(needle)==1
p.write_text(s.replace(needle,"self.phase=phase;self.layer=0;old="))
p=R/'lifetime_adapter.py'
s=p.read_text();needle="('finite_DAG_contract_mismatch',i,label)"
assert s.count(needle)==1
s=s.replace(needle,"('finite_DAG_contract_mismatch',i,dict(label=label,shape=list(t.shape),dtype=str(t.dtype),phase=self.phase,layer=self.layer),plan)")
p.write_text(s)
# Regenerate the finite plan from the source DAG and its two CPU-return readers.
source=B/'swe_qwen3_alias_cache_20261101_v4/control_replay_v2'
nodes=j(source/'NODES.json');files=j(source/'FILES.json');extra=set()
for phase in ['prefill','decode']:
 target=next(v for v in files if v['phase']==phase and v['layer']==1 and v['stage']=='output')
 extra.add(max(n['id'] for n in nodes if n['phase']==phase and n['layer']==1 and n['sha256']==target['sha256']))
plan=[dict(id=n['id'],label=n['label'],shape=n['shape'],dtype=n['dtype'],phase=n['phase'],layer=0 if n['label']=='actual_CPU_input' else n['layer'],readers=len(n['readers'])+int(n['id'] in extra)) for n in nodes]
old=j(V/'LIFETIME_PLAN.json')
assert len(plan)==len(old)==3920
diff=[dict(id=i,before=a,after=b) for i,(a,b) in enumerate(zip(old,plan)) if a!=b]
assert len(diff)==1 and diff[0]['id']==3133
assert {k for k in old[3133] if old[3133][k]!=plan[3133][k]}=={'layer'}
put(R/'LIFETIME_PLAN.json',plan)
put(R/'PLAN_DIFF.json',dict(state='PASS_3920_PLAN_DIFF',differences=diff,source=str(source),extra_CPU_return_reader_nodes=sorted(extra)))
put(R/'LIFETIME_FREEZE.json',dict(plan_sha256=sha(R/'LIFETIME_PLAN.json')))
# Run actual receive_input methods with a minimal transport/publish boundary.
class FakeTensor:
 dtype='torch.bfloat16'
 def view(self,*a):return self
 def reshape(self,shape):self.shape=list(shape);return self
class FakeTorch:
 bfloat16='torch.bfloat16'
 @staticmethod
 def from_numpy(raw):return FakeTensor()
class FakeRaw:
 class Pointer: data=1
 ctypes=Pointer();nbytes=4096
class FakeNP:
 @staticmethod
 def empty(*a,**k):return FakeRaw()
 @staticmethod
 def prod(shape):
  import math
  return math.prod(shape)
 @staticmethod
 def fromfile(*a,**k):return FakeRaw()
class FakeAdapter:
 def __init__(self):self.phase='prefill';self.layer=1;self.um=self;self.calls=0
 def um_recv(self,*a):self.calls+=1;return 0
 def ck(self,rc):assert rc==0
 def publish(self,label,t):return dict(label=label,shape=t.shape,dtype=str(t.dtype),phase=self.phase,layer=self.layer)
out=[]
for name in ['base_adapter.py','replay_backend.py']:
 tree=ast.parse((R/name).read_text())
 method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='receive_input')
 ns=dict(np=FakeNP,torch=FakeTorch,B=B)
 exec(compile(ast.Module(body=[method],type_ignores=[]),name,'exec'),ns)
 for phase,shape in [('prefill',[1,19,2048]),('decode',[1,1,2048])]:
  a=FakeAdapter();actual=ns['receive_input'](a,shape,phase)
  expected=dict(label='actual_CPU_input',shape=shape,dtype='torch.bfloat16',phase=phase,layer=0)
  assert actual==expected,(name,actual)
  out.append(dict(method=name,actual=actual))
put(R/'PHASE_SWITCH_REGRESSION.json',dict(state='PASS_REAL_METHOD_METADATA_WITH_TRANSPORT_DOUBLE',cases=out))
for p in R.glob('*.py'):compile(p.read_text(),str(p),'exec')
print('PREPARED_PHASEFIX_CPU_NOT_RUN',flush=True)

