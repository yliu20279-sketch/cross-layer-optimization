import ctypes,hashlib,json,pathlib,subprocess,torch
R=pathlib.Path(__file__).resolve().parent;p=pathlib.Path(torch.__file__).parent/'lib/libtorch_cpu.so';lib=ctypes.CDLL(str(p))
symbols=subprocess.check_output(['nm','-D',str(p)],text=True);rows=[]
for line in symbols.splitlines():
 if 'bf16_gemv_trans_stub' not in line:continue
 name=line.split()[-1]
 if not any(t in name for t in ['AVX512','AVX2','DEFAULT']):continue
 value=ctypes.c_void_p.in_dll(lib,name).value;rows.append(dict(symbol=name,storage=line.split()[-2],pointer_is_null=value is None))
assert any('AVX512' in r['symbol'] and r['pointer_is_null'] for r in rows)
assert any('AVX2' in r['symbol'] and not r['pointer_is_null'] for r in rows)
h=hashlib.sha256()
with p.open('rb') as f:
 while v:=f.read(8*1024*1024):h.update(v)
out=dict(torch=torch.__version__,overall_cpu_capability=torch.backends.cpu.get_cpu_capability(),library=str(p),library_sha256=h.hexdigest(),BF16_GEMV_registrations=rows,interpretation='AVX512 registration is null; installed BF16 GEMV falls back to AVX2; batch matmul is a different path')
(R/'DISPATCH_INSPECTION.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
