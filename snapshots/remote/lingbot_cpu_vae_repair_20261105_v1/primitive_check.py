import torch,ctypes,subprocess,json
from pathlib import Path
R=Path(__file__).resolve().parent
subprocess.run(['g++','-O3','-shared','-fPIC',str(R/'primitive_cpu.cpp'),'-o',str(R/'primitive_cpu.so')],check=True)
l=ctypes.CDLL(str(R/'primitive_cpu.so'));l.primitive.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int];p=torch.load(R/'TF32_PRIMITIVE.pt',weights_only=True);y=torch.empty_like(p['GPU']);l.primitive(p['a'].data_ptr(),p['b'].data_ptr(),y.data_ptr(),y.numel());r=dict(diff=int((y.view(torch.int32)!=p['GPU'].view(torch.int32)).sum()),max_abs=float((y-p['GPU']).abs().max()),first=list(zip(y.tolist()[:4],p['GPU'].tolist()[:4])));print(r);(R/'TF32_PRIMITIVE_CHECK.json').write_text(json.dumps(r,indent=2))
