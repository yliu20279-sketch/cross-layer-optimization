import subprocess,json
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;old=B/'swe_qwen3_legosim_16_layers_20261030_v3/worker.py';text=old.read_text()
prefix=text[:text.index('from full_adapter import FullAdapter,UnifiedKV')]
prefix=prefix.replace("D=R/('case'+os.environ['SWE_RUN_ROUND'])","D=R/'oracle_cpu'")
custom=r'''
sys.path.insert(0,str(B/'swe_qwen3_step3_four_gates_20261028_v1'))
from generated_adapter_v2 import GeneratedAdapter
class FullAdapter(GeneratedAdapter):
 def __init__(self,codec,out,state):super().__init__(codec,B/'swe_qwen3_step3_four_gates_20261028_v1/libsource_gemm_v2.so');self.phase=None;self.layer=0;self.out=out;self.raw_oracle=[]
 def receive_input(self,shape,phase):self.phase=phase;return fixtures[phase]['decoder_input'].clone()
 def send_result(self,x):pass
 def raw(self,x,w):
  y=super().raw(x,w);self.raw_oracle.append(dict(sequence=len(self.raw_oracle)+1,phase=self.phase,layer=self.layer,M=x.numel()//x.shape[-1],N=w.shape[0],K=x.shape[-1],input_sha256=hashlib.sha256(blob(x)).hexdigest(),weight_sha256=hashlib.sha256(blob(w)).hexdigest(),output_sha256=hashlib.sha256(blob(y)).hexdigest()));return y
 def finish(self,cache):dump(self.out/'RAW_MATRIX_ORACLE.json',self.raw_oracle);return dict(state='CPU_ONLY_MATRIX_ORACLE',calls=len(self.raw_oracle),target_native_runs=0,GPU_runs=0)
class UnifiedKV(AppendOnlyKV):
 def __init__(self,a):super().__init__();self.events=[]
'''
rest=text[text.index('a=FullAdapter'):];rest=rest.replace('target_native_runs=1','target_native_runs=0')
(R/'cpu_oracle.py').write_text(prefix+custom+'\n'+rest)
PY=B/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
with (R/'CPU_ORACLE.log').open('w') as f:p=subprocess.Popen(['/usr/bin/timeout','1800',str(PY),str(R/'cpu_oracle.py')],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'CPU_ORACLE_PID.json').write_text(json.dumps(dict(pid=p.pid,bound_seconds=1800,source_worker=str(old),GPU_runs=0)));print(p.pid)
