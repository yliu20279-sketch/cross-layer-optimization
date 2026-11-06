from pathlib import Path
p=Path('tools/reference_layer_cpu.py')
s=p.read_text().replace("out=run/'pinned_cpu_reference'","out=run/'k64_cpu_reference'")
i=s.index('captured={}')
s=s[:i]+"""def k64_linear(module, activation, tp=1):
    x=activation.detach().numpy().astype(np.float32)
    weights=module.weight.detach().numpy().astype(np.float32)
    count=x.shape[-1]
    parts=[]
    for xpart,wpart in zip(np.split(x,tp,axis=-1),np.split(weights,tp,axis=-1)):
        full=np.zeros((*x.shape[:-1],weights.shape[0]),np.float32)
        for start in range(0,count//tp,64):
            dot=np.zeros_like(full)
            for k in range(start,min(start+64,count//tp)):
                dot+=xpart[...,k,None]*wpart[:,k]
            full+=dot
        parts.append(full.astype(np.float16) if tp>1 else full)
    value=parts[0].astype(np.float32)
    for part in parts[1:]:
        value+=part.astype(np.float32)
    if module.bias is not None:
        value+=module.bias.detach().numpy().astype(np.float32)
    return torch.from_numpy(value.astype(np.float16))

def replace_linear(module, tp):
    module.forward=lambda activation:k64_linear(module,activation,tp)

for name, module in layer.named_modules():
    if isinstance(module,torch.nn.Linear):
        replace_linear(module,4 if name=='self_attn.o_proj' else 1)
"""+s[i:]
s=s.replace("'status':'COMPARED_NO_NUMERICAL_PROMOTION'","'status':'K64_LINEAR_REFERENCE_DIAGNOSTIC_ONLY'")
Path('tools/reference_k64_cpu.py').write_text(s)
