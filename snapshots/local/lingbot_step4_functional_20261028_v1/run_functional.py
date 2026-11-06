import os
os.environ['CUDA_VISIBLE_DEVICES']=''
os.environ['OMP_NUM_THREADS']='8'
os.environ['MKL_NUM_THREADS']='8'
import sys,pathlib,json,hashlib,time,traceback,resource,collections,inspect
import numpy as np
import torch
import torch.nn.functional as F
from safetensors import safe_open
import host_adapter as A

P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_functional_20261028_v1')
G=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step3_capture_20261028_v1')
ASSET=pathlib.Path('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe')
torch.set_num_threads(8);torch.set_grad_enabled(False)
sys.path.insert(0,str(ASSET/'source'))
from lingbot_video.transformer_lingbot_video import LingBotVideoBlock,apply_rotary_emb
os.environ['LINGBOT_MOE_RESTORE_BACKEND']='chunked_scatter'
os.environ['LINGBOT_MOE_RESTORE_CHUNK_SIZE']='128'
os.environ['LINGBOT_MOE_EXPERT_BACKEND']='grouped_mm'

def sha(x):return hashlib.sha256(x).hexdigest()
def raw(x):return x.detach().contiguous().view(torch.uint8).numpy().tobytes()
def write(n,x):(P/n).write_text(json.dumps(x,indent=2),encoding='utf8')
def log(x):print(time.strftime('%H:%M:%S'),x,flush=True)
def save(n,x):
    q=P/'outputs'/(n+'.pt');q.parent.mkdir(exist_ok=True);torch.save(x.contiguous(),q)
    return str(q.relative_to(P))
metrics=[];samples=[];artifacts=[]
def compare(name,candidate,reference,scope,save_full=False,reference_file=None,indices=None):
    assert candidate.shape==reference.shape and candidate.dtype==reference.dtype,(name,candidate.shape,reference.shape,candidate.dtype,reference.dtype)
    c=candidate.float();r=reference.float();d=(c-r).abs();bit=(candidate.contiguous().view(torch.uint8)!=reference.contiguous().view(torch.uint8)).reshape(-1,candidate.element_size()).any(-1)
    entry=dict(name=name,scope=scope,shape=list(candidate.shape),dtype=str(candidate.dtype),elements=candidate.numel(),bitwise_mismatches=int(bit.sum()),numerical_mismatches=int((candidate!=reference).sum()),max_abs=float(d.max()) if d.numel() else 0,rmse=float(torch.sqrt((d*d).mean())) if d.numel() else 0,candidate_raw_sha256=sha(raw(candidate)),reference_raw_sha256=sha(raw(reference)),finite=bool(torch.isfinite(c).all() and torch.isfinite(r).all()),pass_bitwise=not bool(bit.any()),promotion_tolerance=None)
    if save_full:
        entry['candidate_file']=save(name,candidate);entry['reference_original']=reference_file
    if indices is not None and candidate.ndim>=2:
        axis=1 if candidate.ndim==3 else 0
        cs=candidate.index_select(axis,indices);rs=reference.index_select(axis,indices)
    else:cs=candidate;rs=reference
    # Review pair is compact; full comparisons remain separately identified.
    if cs.numel()<=4_000_000:
        cf=save('review_'+name+'_candidate',cs);rf=save('review_'+name+'_reference',rs)
        samples.append(dict(name=name,candidate=cf,reference=rf,full_comparison_scope=scope,indices=None if indices is None else indices.tolist()))
    metrics.append(entry);log(name+' '+json.dumps({k:entry[k] for k in ['bitwise_mismatches','max_abs','rmse']}))
    return entry

def route_compare(name,ids,weights,actual_ids,actual_weights):
    same_set=(ids.sort(-1).values==actual_ids.sort(-1).values).all(-1)
    same_slots=(ids==actual_ids).all(-1)
    # Weights compare by ID when sets equal; slot order remains a separate gate.
    sorted_ids,ord1=ids.sort(-1);_,ord2=actual_ids.sort(-1)
    aligned=weights.gather(1,ord1);other=actual_weights.gather(1,ord2)
    row=dict(name=name,rows=len(ids),set_mismatch_rows=int((~same_set).sum()),slot_mismatch_rows=int((~same_slots).sum()),aligned_weight_bit_mismatch_elements_on_equal_sets=int((aligned[same_set].view(torch.int16)!=other[same_set].view(torch.int16)).sum()),same_set_rows=int(same_set.sum()),not_injected=True)
    route_diagnostics.append(row);save(name+'_ids',ids);save(name+'_weights',weights);log(json.dumps(row))

start=time.time()
try:
    assert os.environ['CUDA_VISIBLE_DEVICES']==''
    assert not torch.cuda.is_initialized()
    freeze=json.loads((P/'FREEZE.json').read_text())
    assert all(sha((P/n).read_bytes())==v for n,v in freeze['files'].items())
    refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references']
    state={};weight_bindings=[]
    for file in sorted({r['canonical_file'] for r in refs}):
        expected=next(r['file_sha256_expected'] for r in refs if r['canonical_file']==file)
        with open(file,'rb') as f:
            h=hashlib.file_digest(f,'sha256').hexdigest()
        assert h==expected
        with safe_open(file,framework='pt',device='cpu') as f:
            for r in refs:
                if r['canonical_file']==file:
                    x=f.get_tensor(r['name']);state[r['name'][len('blocks.0.'):]]=x
                    weight_bindings.append(dict(name=r['name'],shape=list(x.shape),dtype=str(x.dtype),raw_sha256=sha(raw(x)),canonical_file=file,shard_sha256=h))
    write('WEIGHT_BINDINGS.json',weight_bindings)
    config=json.loads((ASSET/'model/transformer/config.json').read_text())
    cfg={k:v for k,v in config.items() if k in inspect.signature(LingBotVideoBlock).parameters};cfg['layer_idx']=0
    with torch.device('meta'):source=LingBotVideoBlock(**cfg)
    source.load_state_dict(state,assign=True);source.eval()
    fixture_manifest=json.loads((G/'FIXTURE_MANIFEST.json').read_text());fixture_by_name={r['file']:r for r in fixture_manifest}
    used={};route_diagnostics=[];branch_summaries=[]
    def fixture(branch,label):
        rel='fixtures/full_on_s00_'+branch+'_L00_'+label+'.pt';q=G/rel
        assert sha(q.read_bytes())==fixture_by_name[rel]['file_sha256']
        used[rel]=fixture_by_name[rel]['file_sha256']
        return torch.load(q,map_location='cpu',weights_only=True)
    routes=[json.loads(s) for s in (G/'ROUTES.jsonl').read_text().splitlines()]
    for branch in ['cond','uncond']:
        log('BEGIN '+branch)
        x=fixture(branch,'block_input');S=x.shape[1];idx=torch.tensor(list(range(32))+list(range(S-32,S)),dtype=torch.int64)
        temb=fixture(branch,'temb6_constant_row');freq=fixture(branch,'rotary')
        mod=A.modulation(temb,state['scale_shift_table'])
        msa_shift,msa_scale,msa_gate,mlp_shift,mlp_scale,mlp_gate=mod
        attn_gold=fixture(branch,'attention_output');pa_gold=fixture(branch,'post_attention_norm')
        pa=A.rms(attn_gold,state['norm_post_attn.weight'])
        compare(branch+'_post_attention_norm_GPU',pa,pa_gold,'full_sequence_isolated_Golden_input',True,'fixtures/full_on_s00_'+branch+'_L00_post_attention_norm.pt',idx)
        compare(branch+'_post_attention_norm_CPU',pa,source.norm_post_attn(attn_gold),'source_CPU_self_consistency',indices=idx)
        # Isolate residual/norm2/mod using original saved post-attention norm.
        mid=x+(msa_gate*pa_gold).to(x.dtype)
        ffn_gold=fixture(branch,'ffn_input')
        ffn_isolated=(A.rms(mid,state['norm2.weight'])*mlp_scale+mlp_shift).to(torch.bfloat16)
        compare(branch+'_residual_norm2_mod_GPU',ffn_isolated,ffn_gold,'full_sequence_Golden_postnorm_injected_boundary',True,'fixtures/full_on_s00_'+branch+'_L00_ffn_input.pt',idx)
        source_mod=(temb+source.scale_shift_table).chunk(6,-1)
        source_ffn=(source.norm2(mid)*(1+source_mod[4])+source_mod[3]).to(torch.bfloat16)
        compare(branch+'_residual_norm2_mod_CPU',ffn_isolated,source_ffn,'source_CPU_self_consistency',indices=idx)
        # Full real router input. No captured IDs passed into router().
        rr=next(r for r in routes if r['run']=='full_on' and r['step']==0 and r['branch']==branch and r['layer']==0)
        assert sha((G/rr['file']).read_bytes())==rr['file_sha256'];used[rr['file']]=rr['file_sha256']
        with np.load(G/rr['file'],allow_pickle=False) as z:
            actual_ids=torch.from_numpy(z['expert_ids'].astype(np.int64));actual_weights=torch.from_numpy(z['dispatch_weight_bits'].copy()).view(torch.bfloat16)
        ids,weights,logits,scores,choice=A.router(ffn_gold.reshape(S,2048),state['ffn.router.weight'],state['ffn.router.e_score_correction_bias'])
        for label,value in [('router_logits',logits),('router_scores',scores),('router_choice',choice)]:
            gold=fixture(branch,label)
            compare(branch+'_'+label+'_GPU',value,gold,'full_sequence_isolated_actual_FFN_input',True,'fixtures/full_on_s00_'+branch+'_L00_'+label+'.pt',idx)
        source_router=source.ffn.router(ffn_gold.reshape(S,2048))
        compare(branch+'_router_logits_CPU',logits,source_router[2],'source_CPU_FP32_linear',indices=idx)
        route_compare(branch+'_free_router',ids,weights,actual_ids,actual_weights)
        captured_scores=fixture(branch,'router_scores')
        ci,cw,cc=A.select(captured_scores,state['ffn.router.e_score_correction_bias'])
        route_compare(branch+'_captured_scores_CPU_selection',ci,cw,actual_ids,actual_weights)
        # Group/tie and selection differences are measured, never replaced.
        xi=ffn_gold[0,idx];sw=lambda n:state['ffn.shared_experts.'+n+'.weight']
        shared=A.mlp(xi,sw('gate_proj'),sw('up_proj'),sw('down_proj'))
        compare(branch+'_shared_GPU',shared,fixture(branch,'shared_output')[0,idx],'64_rows_actual_FFN_input')
        compare(branch+'_shared_CPU',shared,source.ffn.shared_experts(xi),'source_CPU_BF16_linear_reference')
        w1,w3,w2=(state['ffn.experts.'+n] for n in ['w1','w3','w2'])
        free_routed,free_slots=A.replay(xi,ids[idx],weights[idx],w1,w3,w2)
        replay_routed,replay_slots=A.replay(xi,actual_ids[idx],actual_weights[idx],w1,w3,w2)
        gold_ffn_out=fixture(branch,'ffn_output')[0,idx]
        free_ffn=(free_routed+shared).to(torch.bfloat16);replay_ffn=(replay_routed+shared).to(torch.bfloat16)
        compare(branch+'_free_router_MoE_GPU',free_ffn,gold_ffn_out,'64_rows_free_router_no_ID_injection')
        compare(branch+'_recorded_route_MoE_GPU',replay_ffn,gold_ffn_out,'DIAGNOSTIC_recorded_route_replay_NOT_router_PASS')
        source_moe=source.ffn(xi.unsqueeze(0))[0]
        compare(branch+'_free_router_MoE_CPU',free_ffn,source_moe,'source_CPU_BF16_expert_and_router_reference')
        # FP32 weighted slot restore is distinct from BF16 expert sums.
        source_restore=source.ffn._restore_tokens(free_slots,torch.arange(len(xi)*8),weights[idx].reshape(-1),len(xi),8)
        compare(branch+'_slot_restore_CPU',free_routed,source_restore,'same_expert_outputs_source_unsorted_restore')
        post_ffn=A.rms(fixture(branch,'ffn_output'),state['norm_post_ffn.weight'])
        compare(branch+'_post_ffn_norm_GPU',post_ffn,fixture(branch,'post_ffn_norm'),'full_sequence_isolated_Golden_FFN_output',True,'fixtures/full_on_s00_'+branch+'_L00_post_ffn_norm.pt',idx)
        block_isolated=x[:,idx]+(msa_gate*pa_gold[:,idx]).to(x.dtype)
        block_isolated=block_isolated+(mlp_gate*fixture(branch,'post_ffn_norm')[:,idx]).to(x.dtype)
        compare(branch+'_residual_commit_GPU',block_isolated,fixture(branch,'block_output')[:,idx],'64_rows_Golden_postnorm_boundaries')
        log('FULL_CONTEXT_ATTENTION '+branch)
        attn,(q,k,v,preout)=A.attention_selected(x,idx,freq,state,mod)
        compare(branch+'_attention_GPU',attn,attn_gold[:,idx],'64_query_rows_ALL_'+str(S)+'_context_rows')
        # Independent CPU SDPA op only, shares adapter-generated QKV (explicit).
        sdpa=F.scaled_dot_product_attention(q.transpose(1,2),k.transpose(1,2),v.transpose(1,2),dropout_p=0,is_causal=False).transpose(1,2).to(torch.bfloat16)
        compare(branch+'_attention_core_CPU_SDPA',preout,sdpa,'same_QKV_CPU_SDPA_vs_FP32_materialized_softmax')
        for h in [0,15]:
            rq=apply_rotary_emb(source.attn.norm_q(A.linear((A.rms(x[:,idx],state['norm1.weight'])*msa_scale+msa_shift).to(torch.bfloat16),state['attn.to_q.weight']).reshape(1,len(idx),16,128)),freq[:,idx])
            compare(branch+'_RoPE_CPU_head'+str(h),q[:,:,h],rq[:,:,h],'source_complex64_RoPE_same_Q_norm_input')
        # Chained candidate block for selected Q rows, K/V retain original full context.
        chain_mid=x[:,idx]+(msa_gate*A.rms(attn,state['norm_post_attn.weight'])).to(x.dtype)
        chain_in=(A.rms(chain_mid,state['norm2.weight'])*mlp_scale+mlp_shift).to(torch.bfloat16)
        ti,tw,*_=A.router(chain_in[0],state['ffn.router.weight'],state['ffn.router.e_score_correction_bias'])
        tr,_=A.replay(chain_in[0],ti,tw,w1,w3,w2)
        ts=A.mlp(chain_in[0],sw('gate_proj'),sw('up_proj'),sw('down_proj'))
        tout=(tr+ts).to(torch.bfloat16).unsqueeze(0)
        block=chain_mid+(mlp_gate*A.rms(tout,state['norm_post_ffn.weight'])).to(x.dtype)
        compare(branch+'_chained_block_GPU',block,fixture(branch,'block_output')[:,idx],'64_output_rows_full_context_attention_free_router_NO_Golden_internal_injection')
        save(branch+'_selected_global_rows',idx)
        branch_summaries.append(dict(branch=branch,sequence_tokens=S,selected_rows=idx.tolist(),attention_context_tokens=S,weight_dtype_preserved=True))
        write('METRICS.json',metrics);write('ROUTE_DIAGNOSTICS.json',route_diagnostics);write('REVIEW_PAIRS.json',samples)
        del x,attn_gold,pa_gold,pa,mid,ffn_gold,ffn_isolated,source_ffn,source_router,logits,scores,choice,captured_scores,post_ffn,q,k,v,preout,sdpa
        import gc;gc.collect()
    # Real negative controls, not just declarations.
    negatives=[]
    def rejects(name,fn):
        try:fn();rejected=False
        except (TypeError,ValueError,RuntimeError):rejected=True
        negatives.append(dict(name=name,rejected=rejected));assert rejected,name
    rejects('FP16_model_replacement',lambda:A.linear(xi.half(),sw('gate_proj').half()))
    rejects('nonCPU_tensor',lambda:A.cpu(torch.empty(1,device='meta')))
    rejects('wrong_weight_dtype',lambda:A.linear(xi,sw('gate_proj').float()))
    bad=actual_ids[idx].clone();bad[0,0]=128
    rejects('expert_out_of_range',lambda:A.replay(xi,bad,actual_weights[idx],w1,w3,w2))
    bad=actual_ids[idx].clone();bad[0,1]=bad[0,0]
    rejects('duplicate_expert',lambda:A.replay(xi,bad,actual_weights[idx],w1,w3,w2))
    rejects('missing_slot',lambda:A.replay(xi,actual_ids[idx,:7],actual_weights[idx,:7],w1,w3,w2))
    corrupt=actual_weights[idx].clone();corrupt.view(torch.int16)[0,0]^=1
    negatives.append(dict(name='weight_bit_corruption',rejected=sha(raw(corrupt))!=sha(raw(actual_weights[idx]))))
    negatives.append(dict(name='wrong_RoPE_position',rejected=not torch.equal(A.rope(torch.ones(1,2,1,128,dtype=torch.bfloat16),freq[:,:2]),A.rope(torch.ones(1,2,1,128,dtype=torch.bfloat16),freq[:,1:3]))))
    # Source slot-order vs expert-order accumulation difference measured on real slot outputs.
    weighted=replay_slots.reshape(len(xi),8,2048).float()*actual_weights[idx].unsqueeze(-1)
    sorted_slot=actual_ids[idx].argsort(-1)
    wrong=weighted.gather(1,sorted_slot.unsqueeze(-1).expand(-1,-1,2048)).sum(1).to(torch.bfloat16)
    compare('expert_order_commit_negative_diagnostic',wrong,replay_routed,'real_slot_outputs_expert_order_alternative_not_used')
    assert all(n['rejected'] for n in negatives)
    write('NEGATIVE_CONTROLS.json',negatives);write('METRICS.json',metrics);write('REVIEW_PAIRS.json',samples);write('INPUT_BINDINGS.json',used)
    result=dict(status='PARTIAL_DIT_HOST_FUNCTIONAL_ADAPTER_NOT_TARGET_NUMERICAL_PASS',target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized(),target_simulator_runs=0,physical_NPU_runs=0,host_GiB=128,HB_GiB=8,precision='original BF16/FP32',refiner=False,comparisons=len(metrics),bitwise_pass=sum(m['pass_bitwise'] for m in metrics),bitwise_fail=sum(not m['pass_bitwise'] for m in metrics),negative_controls=negatives,branches=branch_summaries,wall_seconds=time.time()-start,maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,notes=['CPU host fallback only; no actual HB/SRAM/NoC service','selected query rows have ALL context; not entire layer output','recorded route replay is diagnostic only','source CPU agreement is not independent target/GPU equivalence','no target cycles or strategy gains'])
    write('FINAL_RESULT.json',result);log(json.dumps(result))
except BaseException:
    write('FAILURE.json',dict(traceback=traceback.format_exc(),time=time.time(),CUDA_initialized=torch.cuda.is_initialized()))
    traceback.print_exc();sys.exit(1)
