"""CPU host fallback functional candidate. No target NPU/timing certification.

BF16 is retained at every source bulk boundary. Matrices decode to FP32 and
accumulate on host CPU; this is not native BF16 array execution. No Golden IDs
are accepted by the free router. Recorded IDs enter only explicit replay().
"""
import math
import torch
import torch.nn.functional as F


def cpu(*xs):
    for x in xs:
        if x.device.type != 'cpu' or x.requires_grad:
            raise ValueError('CPU inference tensors only')
        if x.dtype in (torch.float16, torch.float64):
            raise TypeError('No FP16 replacement or FP64 arithmetic')


def linear(x, w, bias=None, row_tile=256):
    cpu(x,w)
    if x.dtype != w.dtype or x.dtype not in (torch.bfloat16,torch.float32):
        raise TypeError('Original mixed linear operand dtype required')
    if bias is not None:
        cpu(bias)
        if bias.dtype != w.dtype:raise TypeError('bias dtype')
    shape=x.shape[:-1]+(w.shape[0],)
    flat=x.reshape(-1,x.shape[-1]);out=torch.empty((len(flat),w.shape[0]),dtype=x.dtype)
    wf=w.float();bf=None if bias is None else bias.float()
    for start in range(0,len(flat),row_tile):
        out[start:start+row_tile]=F.linear(flat[start:start+row_tile].float(),wf,bf).to(x.dtype)
    return out.reshape(shape)


def rms(x,w,eps=1e-6):
    cpu(x,w)
    if w.dtype!=torch.float32:raise TypeError('FP32 norm weight required')
    z=x.float();v=(z*z).mean(-1,keepdim=True)
    return (w*(z*torch.rsqrt(v+eps))).to(x.dtype)


def rope(x,freq):
    cpu(x,freq)
    if freq.dtype!=torch.complex64:raise TypeError('complex64 source phase')
    pair=x.float().reshape(*x.shape[:-1],-1,2)
    # Separate FP32 products, source complex multiply boundaries; not FP64 trig.
    a,b=pair[...,0],pair[...,1];c=freq.real.unsqueeze(2);s=freq.imag.unsqueeze(2)
    return torch.stack((a*c-b*s,a*s+b*c),dim=-1).flatten(-2).to(x.dtype)


def modulation(temb,table):
    cpu(temb,table)
    if temb.dtype!=torch.bfloat16 or table.dtype!=torch.float32:raise TypeError('temb/table source dtype')
    parts=(temb.float()+table).chunk(6,-1)
    a,b,c,d,e,f=parts
    return a,1.0+b,c.tanh(),d,1.0+e,f.tanh()


def select(scores,bias):
    cpu(scores,bias)
    if scores.dtype!=torch.float32 or bias.dtype!=torch.float32:raise TypeError('FP32 router')
    choice=scores+bias.unsqueeze(0)
    grouped=choice.reshape(-1,4,32)
    gs=grouped.topk(2,dim=-1).values.sum(-1)
    gi=gs.topk(2,dim=-1,sorted=False).indices
    mask=torch.zeros_like(gs,dtype=torch.bool).scatter_(1,gi,True)
    mask=mask.unsqueeze(-1).expand(-1,4,32).reshape(-1,128)
    ids=choice.masked_fill(~mask,float('-inf')).topk(8,dim=-1,sorted=False).indices
    weights=scores.gather(1,ids)
    weights=(weights/(weights.sum(-1,keepdim=True)+1e-20)*2.5).to(torch.bfloat16)
    return ids,weights,choice


def router(x,w,bias):
    cpu(x,w,bias)
    if x.dtype!=torch.bfloat16 or w.dtype!=torch.float32:raise TypeError('router input BF16 / weight FP32')
    logits=linear(x.float(),w)
    scores=torch.sigmoid(logits)
    ids,weights,choice=select(scores,bias)
    return ids,weights,logits,scores,choice


def mlp(x,w1,w3,w2):
    gate=linear(x,w1);up=linear(x,w3)
    activated=F.silu(gate.float()).to(torch.bfloat16)
    product=(activated.float()*up.float()).to(torch.bfloat16)
    return linear(product,w2)


def replay(x,ids,weights,w1,w3,w2):
    """Explicit route-known downstream diagnostic; never a free-router PASS."""
    cpu(x,ids,weights,w1,w3,w2)
    if ids.shape!=(len(x),8) or weights.shape!=ids.shape:raise ValueError('complete 8 slots required')
    if ids.dtype!=torch.int64 or ids.min()<0 or ids.max()>=128 or not bool((ids.sort(-1).values.diff(dim=-1)>0).all()):raise ValueError('invalid route')
    if weights.dtype!=torch.bfloat16 or not bool(torch.isfinite(weights).all()):raise TypeError('BF16 route weights')
    slots=torch.zeros((len(x)*8,x.shape[-1]),dtype=x.dtype)
    flat=ids.reshape(-1);active=torch.where(weights.reshape(-1)!=0)[0]
    order=active[torch.argsort(flat[active],stable=True)]
    for expert in range(128):
        positions=order[flat[order]==expert]
        if not len(positions):continue
        slots[positions]=mlp(x[positions//8],w1[expert],w3[expert],w2[expert])
    # Source restores actual unsorted Top8 slots then reduces FP32 over dim1.
    return (slots.reshape(len(x),8,-1).float()*weights.unsqueeze(-1)).sum(1).to(x.dtype),slots


def attention_selected(x,indices,freq,state,mod,row_tile=256):
    """All full-context K/V, selected Q rows; never truncate conditioning/context.

    Host softmax FP32, BF16 boundary before output projection. Source Flash
    recurrence/rounding is NOT assumed equal to this materialized CPU softmax.
    """
    shift,scale=mod[:2]
    attn_in=(rms(x,state['norm1.weight'])*scale+shift).to(torch.bfloat16)
    q=linear(attn_in[:,indices],state['attn.to_q.weight'])
    k=linear(attn_in,state['attn.to_k.weight'],row_tile=row_tile)
    v=linear(attn_in,state['attn.to_v.weight'],row_tile=row_tile)
    q=q.reshape(1,len(indices),16,128);k=k.reshape(1,x.shape[1],16,128)
    q=rope(rms(q,state['attn.norm_q.weight']),freq[:,indices])
    k=rope(rms(k,state['attn.norm_k.weight']),freq)
    v=v.reshape(1,x.shape[1],16,128)
    out=torch.empty_like(q)
    for head in range(16):
        scores=(q[0,:,head].float()@k[0,:,head].float().T)*(1/math.sqrt(128))
        probs=torch.softmax(scores,dim=-1)
        out[0,:,head]=(probs@v[0,:,head].float()).to(torch.bfloat16)
    result=linear(out.reshape(1,len(indices),2048),state['attn.to_out.weight'],state.get('attn.to_out.bias'))
    return result,(q,k,v,out)
