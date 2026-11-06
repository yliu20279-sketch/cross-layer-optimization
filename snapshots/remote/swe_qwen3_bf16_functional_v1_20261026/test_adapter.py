"""CPU synthetic unit/subchain acceptance against pinned source functions.
No checkpoint, GPU, model generation, task execution or target timing.
"""
import ast
import copy
import hashlib
import json
import platform
from pathlib import Path
import sys
from types import SimpleNamespace
import traceback
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from bf16_adapter import BF16Adapter, NativeCodec, AppendOnlyKV

ROOT=Path(__file__).resolve().parent
SOURCE_HASH='3af43d01f9f902c8009b6dd7d7b8b563561b53dd0aa54175f585ae90d049fdb8'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_source(path):
    assert sha(path)==SOURCE_HASH,'Source identity changed'
    source=Path(path).read_text(); tree=ast.parse(source)
    names={'rotate_half','apply_rotary_pos_emb','repeat_kv','eager_attention_forward',
           'Qwen3MoeAttention','Qwen3MoeMLP','Qwen3MoeSparseMoeBlock','Qwen3MoeRMSNorm','Qwen3MoeRotaryEmbedding'}
    picked=[copy.deepcopy(n) for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names]
    hashes={n.name:hashlib.sha256(ast.dump(n,include_attributes=False).encode()).hexdigest() for n in picked}
    # Bodies unchanged. Source decorators concern autograd/dynamic RoPE;
    # tests are inference-only, default RoPE, CPU, not dynamic scaling.
    for node in picked:
        for n in ast.walk(node):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):n.decorator_list=[]
    def rope_default(config,device=None):
        inv=1.0/(config.rope_theta**(torch.arange(0,config.head_dim,2,device=device).float()/config.head_dim))
        return inv,1.0
    env=dict(torch=torch,nn=nn,F=F,ACT2FN={'silu':F.silu},
             ROPE_INIT_FUNCTIONS={'default':rope_default},ALL_ATTENTION_FUNCTIONS={},
             logger=SimpleNamespace(warning_once=lambda *args:None))
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)]+picked,type_ignores=[])
    ast.fix_missing_locations(module);exec(compile(module,str(path),'exec'),env)
    # Derive router-only reference by retaining the original forward prefix,
    # before any full expert table/output allocation. No rewritten math body.
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Qwen3MoeSparseMoeBlock')
    forward=copy.deepcopy(next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='forward'))
    prefix=[]
    for statement in forward.body:
        if isinstance(statement,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='final_hidden_states' for t in statement.targets):break
        prefix.append(statement)
    forward.name='source_router_prefix';forward.decorator_list=[]
    forward.body=prefix+[ast.Return(value=ast.Tuple(elts=[ast.Name(id=n,ctx=ast.Load()) for n in ['router_logits','routing_weights','selected_experts']],ctx=ast.Load()))]
    m=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),forward],type_ignores=[])
    ast.fix_missing_locations(m);exec(compile(m,str(path),'exec'),env)
    return env,hashes

def config(real=False):
    return SimpleNamespace(hidden_size=2048 if real else 32,
        num_attention_heads=32 if real else 4,num_key_value_heads=4 if real else 2,
        head_dim=128 if real else 8,num_experts=128 if real else 16,num_experts_per_tok=8,
        intermediate_size=6144 if real else 96,moe_intermediate_size=768 if real else 24,
        hidden_act='silu',norm_topk_prob=True,rms_norm_eps=1e-6,attention_bias=False,
        attention_dropout=0.0,sliding_window=None,use_sliding_window=False,max_window_layers=48,
        _attn_implementation='eager',rope_scaling=None,rope_theta=1000000.0,max_position_embeddings=40960)

def freeze(module):
    return module.to(torch.bfloat16).eval().requires_grad_(False)

def finite_equal(a,b):
    return bool(torch.equal(a,b) or (a.shape==b.shape and a.dtype==b.dtype and torch.all((a==b)|(torch.isnan(a)&torch.isnan(b))).item()))

def main():
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--source',required=True);ap.add_argument('--codec',required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
    out=Path(args.out);out.mkdir(exist_ok=False)
    torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(20261026)
    env,source_hashes=load_source(args.source)
    a=BF16Adapter(NativeCodec(args.codec)); checks=[]
    def equal(name,x,y,**meta):
        ok=x.shape==y.shape and x.dtype==y.dtype and finite_equal(x,y)
        err=(x.float()-y.float()).abs(); finite=err[torch.isfinite(err)]
        checks.append(dict(name=name,pass_=ok,shape=list(x.shape),dtype=str(x.dtype),
                           max_abs=float(finite.max()) if finite.numel() else None,**meta))
        if not ok:raise AssertionError(name)
    def predicate(name,ok,**meta):
        checks.append(dict(name=name,pass_=bool(ok),**meta));assert ok,name
    def rejects(name,fn,exception):
        try:fn()
        except exception:predicate(name,True);return
        predicate(name,False)
    def random(shape,scale=1):return (torch.randn(shape)*scale).to(torch.bfloat16)
    try:
      with torch.inference_mode():
        # Actual NPUSim codec versus torch boundary conversion, independent
        # APIs. NaN payload is deliberately not required to be bit-identical.
        raw=np.random.default_rng(20261026).integers(0,2**32,16384,dtype=np.uint32)
        raw=np.concatenate([raw,np.array([0,0x80000000,0x3f808000,0x3f818000,0x7f800000,0xff800000,1,0x7fffff],dtype=np.uint32)])
        x=torch.from_numpy(raw.view(np.float32).copy())
        equal('native_codec_random_fp32_to_bf16',a.cast(x,torch.bfloat16),x.to(torch.bfloat16))
        allbits=torch.from_numpy(np.arange(65536,dtype=np.uint16)).view(torch.bfloat16)
        decoded=a.cast(allbits,torch.float32)
        equal('native_codec_all_bf16_decode',decoded,allbits.float())
        finite=torch.isfinite(allbits)
        equal('native_codec_finite_payload_roundtrip',a.cast(decoded[finite],torch.bfloat16),allbits[finite])
        predicate('bf16_large_value_preserved',torch.isfinite(a.cast(torch.tensor([1.e10]),torch.bfloat16)).all())
        rejects('reject_FP16_input_model_boundary',lambda:a.cast(torch.tensor([1.],dtype=torch.float16),torch.bfloat16),TypeError)
        # The earlier audit's RMSNorm regression, plus random full-head and
        # full-hidden dimensions; source method is the unmodified oracle.
        previous=json.loads((ROOT/'PREVIOUS_CPU_PROBE_RESULT.json').read_text())['rmsnorm_first_counterexample']
        x=torch.tensor([previous['x']],dtype=torch.bfloat16);w=torch.tensor(previous['weight'],dtype=torch.bfloat16)
        ref=freeze(env['Qwen3MoeRMSNorm'](8));ref.weight.copy_(w)
        equal('rmsnorm_previous_cast_before_scale_counterexample',a.rmsnorm(x,w),ref(x))
        for dim in [8,128,2048]:
            x=random((2,3,dim));w=random((dim,));ref=freeze(env['Qwen3MoeRMSNorm'](dim));ref.weight.copy_(w)
            equal('rmsnorm_shared_scale_'+str(dim),a.rmsnorm(x,w),ref(x))
        # Regression: keep router FP32 probabilities, not the BF16 premature
        # rounding produced by the previous generic runtime.
        logits=torch.tensor([[1,2,3]],dtype=torch.bfloat16)
        probs=a.softmax_fp32(logits);equal('router_softmax_fp32_regression',probs,F.softmax(logits,dim=-1,dtype=torch.float32))
        predicate('router_softmax_not_early_bf16',not torch.equal(probs,probs.to(torch.bfloat16).float()))
        for tied in [False,True]:
            x=random((1,7,2048));gate=freeze(nn.Linear(2048,128,bias=False))
            if tied:gate.weight.zero_()
            obj=SimpleNamespace(gate=gate,top_k=8,norm_topk_prob=True)
            rl,rw,ri=env['source_router_prefix'](obj,x)
            actual=a.route(x,gate.weight,8)
            suffix='_ties_cpu_backend_only' if tied else '_real_dimensions'
            equal('router_logits'+suffix,actual['logits'],rl)
            equal('router_final_weights'+suffix,actual['weights'],rw)
            predicate('router_ids'+suffix,torch.equal(actual['selected'],ri),tie_policy='current_CPU_backend; not a GPU guarantee')
            predicate('router_weight_sum_bf16_budget'+suffix,torch.max(torch.abs(actual['weights'].float().sum(-1)-1)).item()<=0.0078125,
                      note='post-BF16 representation budget only; equality to source above remains exact')
        # Shared source MLP with full Qwen expert H/I, not a full expert bank.
        cfg=config(True);expert=freeze(env['Qwen3MoeMLP'](cfg,intermediate_size=768));x=random((3,2048),.2)
        equal('single_expert_real_2048_768',a.expert(x,expert.gate_proj.weight,expert.up_proj.weight,expert.down_proj.weight),expert(x))
        # Metadata: 513 must not be rounded to 512, negative/scalar gather,
        # additive duplicate scatter and source-order index_add.
        table=random((1024,8));ids=torch.tensor([513,-1,0],dtype=torch.int64)
        equal('gather_integer513_negative_indices',a.gather(table,ids),table[ids])
        equal('gather_scalar_shape',a.gather(table,torch.tensor(513)),table[513])
        rejects('gather_out_of_range',lambda:a.gather(table,torch.tensor([1024])),IndexError)
        rejects('gather_no_bf16_indices',lambda:a.gather(table,torch.tensor([513.],dtype=torch.bfloat16)),TypeError)
        data=torch.zeros((4,3),dtype=torch.bfloat16);ix=torch.tensor([1,1,3]);updates=random((3,3))
        equal('index_add_duplicate_source_order',a.index_add(data,ix,updates),data.clone().index_add_(0,ix,updates))
        scatter_ix=torch.tensor([[0,1,1],[2,2,0]]);scatter_up=random((2,3));base=torch.zeros((2,3),dtype=torch.bfloat16)
        equal('scatter_elements_add_duplicate',a.scatter_elements(base,scatter_ix,scatter_up,axis=1),base.scatter_add(1,scatter_ix,scatter_up))
        rejects('scatter_duplicate_replace_not_silently_certified',lambda:a.scatter_elements(base,scatter_ix,scatter_up,1,'none'),NotImplementedError)
        # Real RoPE head width; reference retains original forward body, only
        # supplies explicit standard-default FP32 inv_freq initializer.
        rope=env['Qwen3MoeRotaryEmbedding'](config(True));positions=torch.tensor([[0,1,513,4095]],dtype=torch.int64)
        dummy=torch.zeros((1,4,2048),dtype=torch.bfloat16)
        rc,rs=rope(dummy,positions);ac,ass=a.rotary_tables(positions,rope.inv_freq)
        equal('rope_fp32_constants_cos',ac,rc);equal('rope_fp32_constants_sin',ass,rs)
        q=random((1,32,4,128));k=random((1,4,4,128));rq,rk=env['apply_rotary_pos_emb'](q,k,rc,rs);aq,ak=a.apply_rotary(q,k,ac,ass)
        equal('apply_rope_q_real_heads',aq,rq);equal('apply_rope_k_real_heads',ak,rk)
        # Eager attention prefill -> cached decode. Reference owns a separate
        # torch-cat cache, not the adapter's state, to check ordering/isolation.
        class SourceCache:
            def __init__(self):self.data={}
            def update(self,k,v,layer,cache_kwargs):
                if layer in self.data:
                    pk,pv=self.data[layer];k=torch.cat((pk,k),-2);v=torch.cat((pv,v),-2)
                self.data[layer]=(k,v);return k,v
        cfg=config(True);attn=freeze(env['Qwen3MoeAttention'](cfg,0));source_cache=SourceCache();cache=AppendOnlyKV()
        weights=(attn.q_proj.weight,attn.k_proj.weight,attn.v_proj.weight,attn.o_proj.weight,attn.q_norm.weight,attn.k_norm.weight)
        for past,t in [(0,3),(3,1),(4,1)]:
            x=random((1,t,2048),.1);pos=torch.arange(past,past+t,dtype=torch.int64);cs,ss=rope(x,pos[None,:])
            query_pos=pos[:,None];key_pos=torch.arange(past+t)[None,:]
            mask=torch.where(key_pos<=query_pos,0.,torch.finfo(torch.bfloat16).min).to(torch.bfloat16)[None,None,:,:]
            expected,ep=attn(x,(cs,ss),mask,past_key_value=source_cache,cache_position=pos)
            actual,aprob=a.attention(x,weights,32,4,128,pos,cs,ss,mask,cache,'A',0)
            equal(f'eager_gqa_real_geometry_P{past}_T{t}',actual,expected)
            equal(f'eager_probabilities_P{past}_T{t}',aprob,ep)
            predicate(f'kv_length_P{past}_T{t}',cache.length('A',0)==past+t)
        predicate('KV_session_isolation',cache.length('B',0)==0)
        predicate('KV_layer_isolation',cache.length('A',1)==0)
        keys=random((1,4,1,128));values=random((1,4,1,128))
        rejects('KV_retry_not_double_append',lambda:cache.append('A',0,keys,values,torch.tensor([4])),ValueError)
        cache.append('B',0,keys,values,torch.tensor([0]));predicate('KV_other_session_unchanged',cache.length('A',0)==5)
        # Tiny MoE composition uses 16 experts/top8, no original checkpoint or
        # full 128-expert layer. All source bodies remain unchanged.
        cfg=config(False);moe=freeze(env['Qwen3MoeSparseMoeBlock'](cfg));x=random((1,5,32),.1)
        ew=[(e.gate_proj.weight,e.up_proj.weight,e.down_proj.weight) for e in moe.experts]
        expected,logits=moe(x);actual,routes=a.moe(x,moe.gate.weight,ew,8)
        equal('tiny_moe_16experts_top8_composition',actual,expected)
        equal('tiny_moe_router_logits',routes['logits'],logits)
        predicate('tiny_moe_assignment_conservation',sum(routes['counts'])==40)
        # Nonfinite behavior is checked as classification, not NaN payload.
        x=torch.tensor([[float('inf'),1.,-float('inf')]],dtype=torch.float32)
        equal('softmax_nonfinite_classification',a.softmax_fp32(x),F.softmax(x,-1,dtype=torch.float32))
        predicate('no_GPU_initialized',not torch.cuda.is_initialized())
        predicate('no_FP16_events',all(e['dtype']!='torch.float16' for e in a.events))
        predicate('all_events_untimed_CPU',all(e['functional_device']=='CPU' and e['timing']=='UNMODELED' for e in a.events))
      state='PASS_LIMITED_CPU_SYNTHETIC_SOURCE_SEMANTICS'
    except Exception:
      state='FAIL_RETAINED';(out/'failure.txt').write_text(traceback.format_exc())
    report=dict(state=state,scope='CPU synthetic operators/subchains only; not original weights, full layer/model, GPU, NPU or timing',
                checks=checks,check_count=len(checks),failed=sum(not c['pass_'] for c in checks),event_count=len(a.events),
                runtime=dict(python=sys.version,torch=torch.__version__,numpy=np.__version__,platform=platform.platform(),threads=torch.get_num_threads(),
                             cuda_initialized=torch.cuda.is_initialized(),mkldnn_enabled=torch.backends.mkldnn.enabled),
                source_sha256=sha(args.source),source_AST_hashes=source_hashes,
                codec_sha256=sha(args.codec),adapter_sha256=sha(ROOT/'bf16_adapter.py'),
                contract_sha256=sha(ROOT/'NUMERIC_CONTRACT.md'),test_sha256=sha(__file__),
                limits=['same CPU backend, not independent GEMM kernel proof','TopK ties not portable across backend','default RoPE only','append-only dynamic cache only',
                        'real fixtures and actual GPU kernel contract not yet verified','BF16 target timing remains blocked'])
    (out/'RESULTS.json').write_text(json.dumps(report,indent=2))
    (out/'FUNCTIONAL_EVENTS.json').write_text(json.dumps(a.events,indent=2))
    print(json.dumps({k:report[k] for k in ['state','check_count','failed','event_count','runtime']},indent=2))
    if state.startswith('FAIL'):print((out/'failure.txt').read_text());sys.exit(1)

if __name__=='__main__':main()
