"""Pinned Torch2.6 CUDA unsorted TopK / FP32 Reduce.cuh host realization.

No recorded IDs, weights or row indices are accepted. Domain: finite FP32
sigmoid scores E128/group4/choose2/k8. Not a generic CUDA API tie guarantee.
"""
import torch


def threshold_gather(values,k):
    if values.device.type!='cpu' or values.dtype!=torch.float32 or values.ndim!=2:raise TypeError('host FP32 matrix required')
    if bool(torch.isnan(values).any()) or bool(torch.isposinf(values).any()):raise ValueError('finite or masked -inf only')
    boundary=values.topk(k,dim=-1,sorted=False).values.amin(-1,keepdim=True)
    # E128 and E4 each fit one CUDA gather iteration. Strict winners are
    # emitted in lane/expert order, then boundary equals in lane order.
    e=torch.arange(values.shape[1]).expand_as(values)
    priority=torch.where(values>boundary,e,torch.where(values==boundary,e+values.shape[1],e+2*values.shape[1]))
    return priority.argsort(-1,stable=True)[:,:k]


def sum8_cuda(x):
    if x.dtype!=torch.float32 or x.ndim!=2 or x.shape[1]!=8:raise TypeError('FP32 [N,8]')
    # Reduce.cuh block_width8, input vectorization disabled for dim0<=128;
    # warp shfl_down offsets ascend 1,2,4. Operations are separately FP32.
    a=x[:,0::2]+x[:,1::2]
    b=a[:,0::2]+a[:,1::2]
    return (b[:,0]+b[:,1]).unsqueeze(-1)


def bf16_rne(x):
    if x.device.type!='cpu' or x.dtype!=torch.float32 or not bool(torch.isfinite(x).all()):raise TypeError('finite FP32 payload required')
    u=x.contiguous().view(torch.int32).to(torch.int64)&0xffffffff
    rounded=((u+0x7fff+((u>>16)&1))>>16)&0xffff
    return rounded.to(torch.uint16).view(torch.bfloat16)


def select(scores,bias,return_stages=False):
    if scores.device.type!='cpu' or scores.dtype!=torch.float32 or bias.device.type!='cpu' or bias.dtype!=torch.float32:raise TypeError('host FP32 score/bias')
    if scores.ndim!=2 or scores.shape[1]!=128 or bias.shape!=(128,) or not bool(torch.isfinite(scores).all()) or not bool(torch.isfinite(bias).all()) or bool((scores<0).any()):raise ValueError('finite E128 sigmoid contract')
    choice=scores+bias
    gs=choice.reshape(-1,4,32).topk(2,dim=-1).values.sum(-1)
    gi=threshold_gather(gs,2)
    mask=torch.zeros_like(gs,dtype=torch.bool).scatter_(1,gi,True).unsqueeze(-1).expand(-1,4,32).reshape(-1,128)
    ids=threshold_gather(choice.masked_fill(~mask,float('-inf')),8)
    selected=scores.gather(1,ids)
    denominator=sum8_cuda(selected)+1e-20
    normalized=selected/denominator
    scaled=normalized*2.5
    weight=bf16_rne(scaled)
    if return_stages:return ids,weight,choice,dict(group_scores=gs,group_ids=gi,selected_scores=selected,denominator=denominator,normalized=normalized,scaled=scaled)
    return ids,weight,choice
