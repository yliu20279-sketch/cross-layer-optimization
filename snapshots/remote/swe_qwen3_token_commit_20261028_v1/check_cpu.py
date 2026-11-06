from common import *
D=R/'cpu_attempt1';D.mkdir(exist_ok=False)
for n,h in json.loads((R/'CPU_FREEZE.json').read_text()).items():assert hashfile(R/n)==h
rows,frames=selection();table=layout();cache={};results=[];outs={};weighted={};merged=torch.zeros(2048,dtype=torch.bfloat16)
for r,frame in zip(rows,frames):
 w,bindings=weights(r['expert'],table,cache);x=bf(frame[128:]);ref=reference(x,w);diff={}
 g=bf(rb(tree(x,w['gate_proj'])).tobytes());u=bf(rb(tree(x,w['up_proj'])).tobytes())
 a=g.float().numpy()
 with np.errstate(over='ignore'):s=bf(rb(a/(np.float32(1)+np.exp(-a,dtype=np.float32))).tobytes())
 p=bf(rb(s.float().numpy()*u.float().numpy()).tobytes());d=bf(rb(tree(p,w['down_proj'])).tobytes())
 for name,v in [('gate',g),('up',u),('silu',s),('product',p),('down',d)]:diff[name]=int((v.view(torch.uint16)!=ref[name].view(torch.uint16)).sum())
 weight=bf(struct.pack('<H',r['weight_bits']))[0];weighted[r['expert']]=ref['down']*weight;outs[r['expert']]=ref['down'];results.append(dict(**r,differences=diff,weights=bindings))
order=sorted(weighted);prefixes=[]
for e in order:
 merged=merged.clone().index_add_(0,torch.tensor([0]),weighted[e].reshape(1,-1)) if merged.ndim==2 else (merged.reshape(1,-1).clone().index_add_(0,torch.tensor([0]),weighted[e].reshape(1,-1))).reshape(-1)
 prefixes.append(sha(blob(merged)))
slot_order=torch.zeros_like(merged)
for r in rows:slot_order=(slot_order.float()+weighted[r['expert']].float()).bfloat16()
status=dict(state='PASS_LIMITED_FIXED_TOKEN_CPU' if not any(any(v['differences'].values()) for v in results) else 'FAIL_FIXED_TOKEN_CPU',rows=results,source_order=order,source_prefix_sha256=prefixes,slot_order_different=int((slot_order.view(torch.uint16)!=merged.view(torch.uint16)).sum()),final_sha256=sha(blob(merged)),scope='M1 recorded dispatch only; batch and softmax differences retained; no GPU/SWE')
(D/'reference_final_BF16.bin').write_bytes(blob(merged));dump(D/'RESULTS.json',status);print(json.dumps({k:v for k,v in status.items() if k!='rows'}))
