"""Source-grounded symbolic graphs and proposed mapping, no model execution."""
import csv
import hashlib
import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent

def write(name, value):
    (ROOT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def table(name, rows):
    with (ROOT / name).open('w', newline='', encoding='utf-8-sig') as f:
        fields=list(dict.fromkeys(k for row in rows for k in row))
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k,v in row.items()})

audit = json.loads((ROOT/'source/MODEL_HEADER_AUDIT.json').read_text(encoding='utf-8-sig'))
c = audit['config']
H,Q,KV,D,L,E,K,I,V = [c[k] for k in ['hidden_size','num_attention_heads','num_key_value_heads','head_dim','num_hidden_layers','num_experts','num_experts_per_tok','moe_intermediate_size','vocab_size']]
assert (H,Q,KV,D,L,E,K,I,V)==(2048,32,4,128,48,128,8,768,151936)
UNITS = {
 'CPU':'Host CPU / external container; target CPU/OS timing unresolved',
 'MAC':'NPU array candidate: FP16 MAC + FP32 accumulate; BF16 unresolved',
 'VECTOR':'NPU FP32 vector/reduce software lowering candidate; transcendental/TopK latency unresolved',
 'HB':'CHi HB-DRAM + Ni SRAM lifetime; Ramulator callback required',
 'NOC':'4x4 mesh / PopNet completion + reduction arithmetic where needed',
 'HOSTLINK':'CPU gateway / PCIe DMA callback; no CPU execution hidden in NPU',
}

OPS = [
 ('attn_norm','RMSNorm before attention','[T,2048]','VECTOR','all N0..15','[2048] replicated','O(T*H)','source:372'),
 ('q','Q projection','[T,32,128]','MAC','TP16: 2 Q heads/rank','Wq[4096,2048] column shards','T*2048*4096 MAC','source:150,184'),
 ('k','K projection','[T,4,128] logical; four physical copies','MAC','KV head r//4 per rank','Wk[512,2048]; 4x KV-head replication','T*2048*512 logical MAC; physical 4x','source:153,185'),
 ('v','V projection','[T,4,128] logical; four physical copies','MAC','KV head r//4 per rank','Wv[512,2048]; 4x KV-head replication','T*2048*512 logical MAC; physical 4x','source:156,186'),
 ('qnorm','Q per-head RMSNorm','[T,32,128]','VECTOR','local Q heads','shared learned vector[128], replicated ranks','reduce last dimension 128','source:162'),
 ('knorm','K per-head RMSNorm','[T,4,128]','VECTOR','local KV copy','shared learned vector[128], replicated ranks','reduce last dimension 128','source:163'),
 ('qrope','RoPE on Q','[T,32,128]','VECTOR','local Q heads','cos/sin from invocation-global position table','rotate/multiply/add; no MAC throughput claim','source:attention forward'),
 ('krope','RoPE on K','[T,4,128]','VECTOR','local KV copy','same global position table','rotate/multiply/add','source:attention forward'),
 ('kvwrite','Append current K/V','[2,T,4,128] logical','HB','CHr: replicated local KV head','2-byte BF16 storage; physical KV 4x','32 B transactions only after address allocation','source:past_key_value.update'),
 ('kvread','Read needed K/V / tile view','[2,P+T,4,128] logical','HB','Ni<->CHi one port','read past state; cache/read reuse policy TBD','logical volume not actual DRAM traffic','source:cache + attention'),
 ('qk','Tiled QK transpose / GQA','[32,T,P+T] logical only','MAC','2 Q heads per rank; local KV copy','no materialized full score matrix assumed','32*128*A MAC, A=T*P+T*(T+1)/2 useful causal pairs','source:eager/SDPA attention'),
 ('softmax','Scale + causal mask + stable softmax','score/probability tiles','VECTOR','local attention tiles','FP32 max/sum/exp software; algorithm TBD','tile reductions, masked entries and padding cost TBD','source:eager/SDPA attention'),
 ('av','Probability times V','[T,32,128]','MAC','local attention heads','tiled V reuse','32*128*A MAC','source:eager/SDPA attention'),
 ('o','Output projection partial','[T,2048] partial/rank','MAC','row parallel TP16','Wo[2048,4096] input shards','T*4096*2048 MAC','source:159,219'),
 ('attn_reduce','Sum TP output partials','[T,2048] replicated result','NOC','all16 collective; algorithm TBD','link callbacks + FP32 reduce at nodes','network bytes depend on collective; not assumed zero','proposed target lowering'),
 ('attn_res','Attention residual add','[T,2048]','VECTOR','all16 replicated hidden','preserve input until join','T*2048 additions logical; mapping replication explicit','source:attention residual'),
 ('moe_norm','RMSNorm before MoE','[T,2048]','VECTOR','all16 hidden replicas','[2048] vector replicated','O(T*H)','source:389'),
 ('router','Router linear logits','[T,128]','MAC','N0 once per logical token','Wrouter[128,2048] on CH0','T*2048*128 MAC','source:247,257'),
 ('route_softmax','Router FP32 softmax','[T,128]','VECTOR','N0','FP32 logits normalization','exp/reduce/div software','source:259'),
 ('top8','Top8 + renormalize + dtype cast','IDs[T,8], weights[T,8]','VECTOR','N0','sum over selected8; cast to hidden dtype','actual dispatch output must be captured','source:260-264'),
 ('route_meta','Route IDs/weights to token origin','IDs/weights only','NOC','N0 -> token origin o(t)','origin=t mod16 proposed, not Sem-MoE policy','metadata bytes/routing TBD; local route possible','proposed lowering'),
 ('dispatch','Pack + dispatch only once per logical assignment','sum_e m_e = 8*T','NOC','origin -> expert owner p_l(e)','no 16x duplicate dispatch despite replicated hidden','BF16 token payload <= 8*T*2048*2; exclude local + coalescing; physical traffic TBD','source:expert_mask/where; proposed lowering'),
 ('expert_weights','Ensure active expert weights resident','3*2048*768 per expert','HB','CH[p_l(e)]; inactive experts not executed','active expert full bytes=9437184; tiles if not resident','cache hit or fetch/evict/commit subgraph; storage service unresolved','source:MLP weights; proposed memory gate'),
 ('gate','Expert gate projection','[m_e,768]','MAC','owner p_l(e), e loop if m_e>0','Wgate[768,2048]','m_e*2048*768 MAC','source:229,235'),
 ('up','Expert up projection','[m_e,768]','MAC','owner p_l(e), e loop','Wup[768,2048]','m_e*2048*768 MAC','source:MLP'),
 ('silu','Expert gate SiLU','[m_e,768]','VECTOR','expert owner','software sigmoid/exp cost TBD','m_e*768 activations','source:235'),
 ('multiply','SiLU(gate) times up','[m_e,768]','VECTOR','expert owner','retain up tile until gate activation ready','m_e*768 multiplies','source:235'),
 ('down','Expert down projection','[m_e,2048]','MAC','expert owner','Wdown[2048,768]','m_e*768*2048 MAC','source:235'),
 ('weight','Multiply output by final route weight','[m_e,2048]','VECTOR','expert owner','BF16 source arithmetic; target dtype unresolved','m_e*2048 multiplies','source:283'),
 ('return','Return expert outputs','sum_e [m_e,2048]','NOC','owner -> original token origin','response callback before join','local traffic not counted as inter-router bytes','source:expert outputs; proposed lowering'),
 ('combine','Scatter/index_add selected experts','[T,2048] origin-owned tokens','VECTOR','one origin per token','8 contributions/token; order and accumulation dtype must match contract','no arbitrary reduction-order equivalence','source:287'),
 ('hidden_sync','Collect token partitions for TP next layer','[T,2048] replicated','NOC','token origins -> all16','allgather/broadcast candidate, count traffic','not free; may optimize only with new mapping contract','proposed lowering'),
 ('moe_res','MoE residual add','[T,2048]','VECTOR','all16 after sync','join attention-residual with combined output','T*2048 logical adds','source:decoder residual'),
]

def make_graph(phase):
    nodes=[]; edges=[]
    def node(i,op,unit,shape,layer=-1,**extra):
        nodes.append(dict(id=i,op=op,unit=unit,shape=shape,layer=layer,evidence='SOURCE_GROUNDED_SYMBOLIC_NOT_EXECUTED',**extra));return i
    def edge(a,b,kind='data',tensor=''):
        edges.append(dict(src=a,dst=b,kind=kind,tensor=tensor,completion='producer complete before consumer; target callback for memory/network'))
    node('token_ids','Tokenizer output / actual token IDs','CPU','[T]')
    node('ingress','Input IDs and position transfer','HOSTLINK','[T]');edge('token_ids','ingress')
    node('embed','Vocab-sharded embedding lookup','HB','[T,2048] partial/rank');edge('ingress','embed')
    node('embed_sync','Embedding partial sum/broadcast','NOC','[T,2048] replicated');edge('embed','embed_sync')
    node('position','Global RoPE cos/sin once per forward','VECTOR','[T,128]');edge('ingress','position')
    node('position_sync','RoPE table multicast from N0','NOC','cos/sin[T,128]');edge('position','position_sync')
    previous='embed_sync'
    for l in range(L):
        ids={r[0]:f'L{l:02d}.{r[0]}' for r in OPS}
        for key,name,shape,unit,place,weight,work,src in OPS:
            node(ids[key],name,unit,shape,l,placement=place,weights=weight,work=work,source=src,
                 expert_loop=('e in [0,127], execute only if m_e>0' if key in ['expert_weights','gate','up','silu','multiply','down','weight','return'] else None))
        links=[('attn_norm','q'),('attn_norm','k'),('attn_norm','v'),('q','qnorm'),('k','knorm'),('qnorm','qrope'),('knorm','krope'),('krope','kvwrite'),('v','kvwrite'),('kvwrite','kvread'),('qrope','qk'),('kvread','qk'),('qk','softmax'),('softmax','av'),('kvread','av'),('av','o'),('o','attn_reduce'),('attn_reduce','attn_res'),('attn_res','moe_norm'),('moe_norm','router'),('router','route_softmax'),('route_softmax','top8'),('top8','route_meta'),('route_meta','dispatch'),('moe_norm','dispatch'),('dispatch','expert_weights'),('dispatch','gate'),('dispatch','up'),('expert_weights','gate'),('expert_weights','up'),('expert_weights','down'),('gate','silu'),('silu','multiply'),('up','multiply'),('multiply','down'),('down','weight'),('top8','weight'),('weight','return'),('return','combine'),('combine','hidden_sync'),('hidden_sync','moe_res'),('attn_res','moe_res')]
        edge(previous,ids['attn_norm']);edge(previous,ids['attn_res'],tensor='residual skip')
        edge('position_sync',ids['qrope']);edge('position_sync',ids['krope'])
        for a,b in links:edge(ids[a],ids[b])
        previous=ids['moe_res']
    node('finalnorm','Final RMSNorm','VECTOR','[T,2048]');edge(previous,'finalnorm')
    node('head_select','Select positions for logits','VECTOR','[J,2048], J determined by logits_to_keep');edge('finalnorm','head_select')
    node('lmhead','Vocab-parallel LM head','MAC','[J,151936], shard9496/rank',work='J*2048*151936 MAC',weight='[151936,2048] untied');edge('head_select','lmhead')
    node('logits_transfer','Gather logits or exact distributed selection','HOSTLINK','[J,151936] or validated candidates');edge('lmhead','logits_transfer')
    node('sample','Generation policy / EOS / stop','CPU','selected token IDs; algorithm TBD');edge('logits_transfer','sample')
    return dict(phase=phase,query_tokens=('T symbolic' if phase=='prefill' else 'T=1 normal autoregressive forward'),past_tokens='P symbolic; cache persistence must be observed',
                causal_pairs='A=T*P+T*(T+1)/2 useful pairs; actual tiled masked work can exceed this',
                logits_positions='J policy-dependent, not silently fixed to all or last',nodes=nodes,edges=edges,
                optional_diagnostics='output_router_logits=True may compute aux load-balancing statistics even without labels; hook overhead separate; no training/loss main path')

def validate_graph(g):
    ids={n['id'] for n in g['nodes']}; assert len(ids)==len(g['nodes'])
    indeg={i:0 for i in ids}; follow={i:[] for i in ids}
    for e in g['edges']:
        assert e['src'] in ids and e['dst'] in ids
        indeg[e['dst']]+=1;follow[e['src']].append(e['dst'])
    pending=[i for i in ids if not indeg[i]];seen=[]
    while pending:
        i=pending.pop();seen.append(i)
        for j in follow[i]:
            indeg[j]-=1
            if not indeg[j]:pending.append(j)
    assert len(seen)==len(ids),'Cycle'
    assert sum(n['op']=='Expert gate projection' for n in g['nodes'])==48
    return dict(nodes=len(ids),edges=len(g['edges']),acyclic=True,layers=48,execution='NOT_RUN')

def main():
    table('OPERATOR_INVENTORY.csv',[dict(key=k,operator=n,output_shape=s,unit=u,mapping=m,weight=w,work_formula=f,source=src) for k,n,s,u,m,w,f,src in OPS])
    checks={}
    for phase in ['prefill','decode']:
        g=make_graph(phase);write(phase+'_graph.json',g);checks[phase]=validate_graph(g)
        table(phase+'_nodes.csv',g['nodes']);table(phase+'_edges.csv',g['edges'])
    task_nodes=[('task','Load issue + repo/base commit','CPU'),('prompt','History + chat template + tokenizer','CPU'),('prefill','Uncached prefill / recomputation','NPU symbolic'),('head','LM head + sample first output token','CPU/NPU proposed'),('decode','Decode recurrent forward + KV state','NPU symbolic'),('parse','Parse generated action / format checks','CPU'),('tool','Read/search/edit/test command in container','External CPU/container'),('feedback','Observation + stdout/stderr/exit','CPU'),('finish','Final patch + harness evaluation','External CPU/container'),('limits','Timeout / format error / failure exit','CPU')]
    task_edges=[dict(src=a,dst=b,kind=k) for a,b,k in [('task','prompt','data'),('prompt','prefill','data'),('prefill','head','data'),('head','decode','conditional more output'),('decode','decode','next generated token; recurrent template'),('head','parse','complete message'),('decode','parse','complete message'),('parse','tool','valid nonterminal command'),('tool','feedback','actual process completion'),('feedback','prompt','next turn; conditional loop'),('parse','feedback','format error; no tool executed'),('parse','finish','submit command'),('parse','limits','budget/invalid output'),('tool','limits','timeout/fatal failure')]]
    write('task_control_graph.json',dict(nodes=[dict(id=i,op=n,unit=u) for i,n,u in task_nodes],edges=task_edges,nature='CONTROL_FLOW_TEMPLATE_WITH_LOOPS_NOT_EXECUTABLE_DAG',unrolling='Each observed turn/token gets unique ID; only finite observed unrolling may be DAG-audited',warning='A read->edit->test sequence is goal, not guaranteed actions in every task'))
    params=2*V*H+H+L*(H*Q*D+2*H*KV*D+Q*D*H+2*D+2*H+H*E+E*3*H*I)
    assert params==audit['parameter_elements']
    expert=3*H*I; unique_bytes=params*2; expert_bytes=L*E*expert*2
    # Proposed TP16 replication: K/V 4x, norms (q/k/input/post + final) 16x. Router on N0 once.
    kv_projection_extra=L*(4-1)*2*H*KV*D*2
    norms_extra=(L*(2*D+2*H)+H)*(16-1)*2
    physical_weights=unique_bytes+kv_projection_extra+norms_extra
    pinned=[(2*V*H*2)//16 + L*((H*Q*D+Q*D*H)*2//16 + 2*H*D*2 + (2*D+2*H)*2) + H*2 + (L*H*E*2 if r==0 else 0) for r in range(16)]
    assert sum(pinned)+expert_bytes==physical_weights
    ranks=[dict(rank=r,npu=f'N{r}',partition=f'CH{r}',query_heads=[2*r,2*r+1],kv_head=r//4,
                kv_replication_group=list(range((r//4)*4,(r//4)*4+4)),experts=list(range(r,E,16)),
                vocabulary_range=[r*(V//16),(r+1)*(V//16)],expert_bytes_all_layers=48*8*expert*2,
                pinned_nonexpert_weight_bytes=pinned[r],full_model_static_resident=False) for r in range(16)]
    write('MAPPING.json',dict(status='PROPOSED_STRUCTURAL_MAPPING_NOT_EXECUTED',attention='TP16 with fourfold KV-head replication',moe='EP16; baseline p_l(e)=e mod16; Sem-MoE p_l(e) must be frozen from profile',
         token_origin='o(t)=t mod16 baseline structural choice; dispatch once, not once per hidden replica',router='N0 per layer per logical token; count metadata traffic',ranks=ranks,
         bf16_support='UNVERIFIED; FP16 MAC spec does not prove BF16',units=UNITS,
         memory='HB weight/KV backing; SRAM tiles; active expert residency gate; host/gateway/storage unresolved',
         hiband='phase/mode/scope separate; no overlap assumed; one vertical interface per Ni/CHi',
         physical_addresses='UNALLOCATED; no executable Ramulator/NPUSim IR claimed',
         kv_cache_policy='proposed replicated KV; actual functional GPU cache behavior must be measured'))
    write('CAPACITY.json',dict(parameter_elements=params,unique_weight_payload_bytes=unique_bytes,weight_shard_file_bytes=61066575648,
         model_repository_bytes=61084187391,experts_total_bytes=expert_bytes,expert_one_bytes=expert*2,
         experts_per_rank_all_layers_bytes=expert_bytes//16,qk_norm_vectors_each=128,
         old_mapping_formula_parameters=30532331520,old_mapping_overcount_elements=30532331520-params,
         proposed_kv_projection_replica_extra_bytes=kv_projection_extra,proposed_norm_replica_extra_bytes=norms_extra,
         proposed_physical_weight_payload_bytes=physical_weights,
         pinned_nonexpert_per_rank_bytes=pinned,
         example_expert_cache_budget=[dict(context=n,rank=r,pinned_bytes=pinned[r],kv_bytes=n*48*2*128*2,reserve_bytes=32*2**20,
              whole_expert_slots=max(0,(512*2**20-pinned[r]-n*48*2*128*2-32*2**20)//(expert*2)),
              base_fits=pinned[r]+n*48*2*128*2+32*2**20<=512*2**20,
              evidence='analytical candidate; one session, nonexpert pinned, 32MiB runtime reserve is unvalidated assumption') for n in [512,4096,16384] for r in [0,1]],
         unique_kv_bytes_per_cached_token=48*2*4*128*2,proposed_kv_bytes_per_cached_token=48*2*4*128*2*4,
         proposed_kv_per_rank_bytes_per_cached_token=48*2*128*2,
         kv_examples=[dict(context=n,sessions=1,per_rank_bytes=n*48*2*128*2,global_bytes=n*48*2*4*128*2*4,evidence='analytical example, not measured workload') for n in [512,4096]],
         target_hb_total_bytes=8*2**30,target_host_dram_bytes=8*2**30,target_sram_per_npu_bytes=4*2**20,
         static_fit=False,even_unique_payload_fits_hb_plus_host=False,
         blocker='61 GB unique BF16 payload > 8 GiB HB + 8 GiB target host; external storage or explicit host-capacity amendment required; actual server RAM is not target host',
         unresolved=['per-rank resident nonexpert/paged-expert schedule','KV growth/session policy','peak SRAM tiling and runtime buffers','address allocation and 32B transactions','BF16 arithmetic','host/PCIe/storage service']))
    tiled=dict(tile_m=64,tile_n=64,tile_k=64,input_2byte_bytes=64*64*2,weight_2byte_bytes=64*64*2,acc_fp32_bytes=64*64*4,
               status='illustrative per-GEMM tile components only, not SRAM peak proof',requires='buffer lifetimes, double buffering, routing, KV, vector workspace and bank arbitration')
    write('TILING_CANDIDATE.json',tiled)
    write('VALIDATION.json',dict(status='PASS_STRUCTURAL_ONLY',graphs=checks,parameter_count_matches_all_shard_headers=True,
         kv_head_mapping_complete=sorted(set(x['kv_head'] for x in ranks))==list(range(4)),query_head_partition_complete=sorted(h for x in ranks for h in x['query_heads'])==list(range(32)),
         expert_partition_complete=sorted(e for x in ranks for e in x['experts'])==list(range(128)),
         dynamic_routes='UNKNOWN_NOT_FABRICATED',numerics='NOT_RUN',npu_noc_dram_execution='NOT_RUN'))
    sourcepaths=[ROOT/'source/modeling_qwen3_moe.py',ROOT/'source/configuration_qwen3_moe.py',ROOT/'source/MODEL_HEADER_AUDIT.json',
                 PROJECT/'mini_swe_qwen3_preflight_20261026_v1/official_snapshot/src/minisweagent/agents/default.py',
                 PROJECT/'whisper_operator_inventory/target_architecture_v3_6/target_architecture_v3_6.yaml',
                 PROJECT/'qwen3_30b_a3b_v3_5_mapping/build.py']
    write('SOURCE_MANIFEST.json',[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sourcepaths])
    print(json.dumps(dict(status='PASS_STRUCTURAL_ONLY',graphs=checks,parameters=params,unique_bytes=unique_bytes),indent=2))

if __name__=='__main__':main()
