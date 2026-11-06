import torch,ctypes,json
from pathlib import Path
R=Path(__file__).resolve().parent;p=torch.load(R/'SDPA_INPUT.pt',weights_only=True);ref=torch.load(R/'OBSERVER_OUTPUT.pt',weights_only=True)['QK'];q=p['q'][0,0,:8].contiguous();k=p['k'].contiguous();y=torch.empty_like(ref);rows=[]
for library,fn in [('sdpa_candidate.so','scores'),('sdpa_tf32.so','score_tf')]:
 l=ctypes.CDLL(str(R/library));f=getattr(l,fn);f.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int]*3;f(q.data_ptr(),k.data_ptr(),y.data_ptr(),8,k.shape[-2],384);y=y*(1/(384**.5));rows.append(dict(method=fn,diff=int((y.view(torch.int32)!=ref.view(torch.int32)).sum()),max_abs=float((y-ref).abs().max())));torch.save(y,R/(fn+'_QK.pt'))
print(rows);(R/'QK_AUDIT.json').write_text(json.dumps(rows,indent=2))
