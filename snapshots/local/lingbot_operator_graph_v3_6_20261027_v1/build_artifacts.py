"""Static source-bound graphs; never imports torch or executes model weights."""
from pathlib import Path
import json, csv, math, hashlib, collections, html, textwrap, ast
from PIL import Image, ImageDraw, ImageFont

P = Path(__file__).resolve().parent
SRC = P / 'source'
H, I, E, K, D, NH = 2048, 768, 128, 8, 48, 16
config=json.loads((P.parent/'lingbot_ti2v_feasibility_20261026_v1/sources/config.json').read_text(encoding='utf8'))
assert (config['hidden_size'],config['moe_intermediate_size'],config['num_experts'],config['num_experts_per_tok'],config['depth'],config['num_attention_heads'])==(H,I,E,K,D,NH)

def dump(name, obj):
    (P/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf8')

def csvout(name, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with (P/name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)

def anchor(file, needle):
    lines = (SRC/file).read_text(encoding='utf8').splitlines()
    return {'file': 'source/'+file, 'line': next(i+1 for i,s in enumerate(lines) if needle in s)}

T = 'lingbot_video/transformer_lingbot_video.py'
PI = 'lingbot_video/pipeline_lingbot_video_i2v.py'
PB = 'lingbot_video/pipeline_lingbot_video.py'
nodes, edges, inventory = [], [], []

def node(ident, op, shape, dtype, target, source, scope='SOURCE_SEMANTICS_TEMPLATE', **extra):
    r = dict(id=ident, op=op, shape=shape, dtype=dtype, target_candidate=target,
             evidence_scope=scope, source=source, **extra)
    nodes.append(r); return ident

def edge(a,b,kind='data_completion'):
    edges.append(dict(src=a,dst=b,kind=kind))

def chain(prefix, rows, source, start=None):
    prev=start; ids=[]
    for key,op,shape,dtype,target in rows:
        ident=node(prefix+key,op,shape,dtype,target,source)
        if prev: edge(prev,ident)
        prev=ident; ids.append(ident)
    return prev, ids

# One 48-block DiT call. S includes video AND condition text, not just video.
pre = [
 ('latent','input latent','[B,16,Tz,Hz,Wz]','FP32','HB / gateway'),
 ('patch','patchify / permutation','[B,Nv,64]','FP32 -> linear dtype','vector / DMA'),
 ('patch_gemm','patch projection + bias','64 -> 2048','BF16 bulk','matrix candidate'),
 ('text','RMSNorm -> Linear -> SiLU -> Linear','[B,L,2560] -> [B,L,2048]','BF16 + FP32 norm','matrix + vector'),
 ('joint','concatenate video then text / packed interleave','[B,S,2048]','BF16','HB / DMA'),
 ('positions','3D position IDs and complex RoPE table','[S,3] / [S,64] complex','int / FP64 table preparation -> FP32 complex','host table + vector'),
 ('time','sin/cos timestep projection -> FP32 time MLP','[B,256] -> [B,2048]','FP32','vector + FP32 software matrix'),
 ('temb6','token-level SiLU -> Linear 2048 to 12288','[B*S,6*2048]','FP32','matrix/vector; tile or prove broadcast equivalent'),
 ('cp_boundary','optional CP split joint/rope/temb6','sequence shards or unchanged','mixed','source CP; target contract separate'),
]
for key,op,shape,dt,tar in pre:
    node('pre.'+key,op,shape,dt,tar,anchor(T,'def forward(\n') if False else anchor(T,'# patchify:'))
for a,b in [('latent','patch'),('patch','patch_gemm'),('patch_gemm','joint'),('text','joint'),('joint','positions'),('time','temb6'),('joint','temb6'),('joint','cp_boundary'),('positions','cp_boundary'),('temb6','cp_boundary')]:edge('pre.'+a,'pre.'+b)

# Source block branches are explicit; experts remain a conditional macro until routes exist.
previous='pre.cp_boundary'
for layer in range(D):
    pf=f'L{layer:02d}.'; source=anchor(T,'class LingBotVideoBlock')
    specs=[
      ('mod','add learned scale_shift_table; split 6; tanh two gates','[B*S,6H]','FP32','vector'),
      ('norm1','RMSNorm before attention','[B,S,H]','FP32 accumulation -> input dtype','vector/reduce'),
      ('affine1','multiply (1+scale_msa), add shift_msa, cast','[B,S,H]','FP32 -> BF16','vector/codec'),
      ('q','Q projection','[B,S,16,128]','BF16','matrix'),
      ('k','K projection','[B,S,16,128]','BF16','matrix'),
      ('v','V projection','[B,S,16,128]','BF16','matrix'),
      ('qn','per-head Q RMSNorm','[B,S,16,128]','FP32 accumulation -> BF16','vector/reduce'),
      ('kn','per-head K RMSNorm','[B,S,16,128]','FP32 accumulation -> BF16','vector/reduce'),
      ('qr','complex RoPE Q','3 axes dims 32/48/48','FP32 complex -> BF16','vector/host table'),
      ('kr','complex RoPE K','3 axes dims 32/48/48','FP32 complex -> BF16','vector/host table'),
      ('qk','noncausal tiled joint QK; packed samples isolated','logical [B,16,S,S]','BF16 inputs / calibrated accumulation TBD','matrix; never full score HB allocation'),
      ('softmax','scale + validity mask + stable softmax','tile row state; no autoregressive mask','FP32 reduction / exp TBD','vector/reduce'),
      ('av','tiled attention AV','[B,S,16,128]','BF16 output boundary','matrix'),
      ('out','attention output projection + bias','H -> H','BF16','matrix'),
      ('postattn','post-attention RMSNorm','[B,S,H]','FP32 accumulation -> input dtype','vector/reduce'),
      ('gateattn','multiply tanh gate, cast to residual dtype','[B,S,H]','FP32 -> residual dtype','vector'),
      ('resattn','add attention residual','[B,S,H]','residual dtype','vector'),
      ('norm2','pre-FFN RMSNorm','[B,S,H]','FP32 accumulation -> input dtype','vector/reduce'),
      ('affine2','multiply (1+scale_mlp), add shift_mlp, cast','[B,S,H]','FP32 -> BF16','vector/codec'),
      ('router','router F.linear on FP32 tokens and weights','[B*S,2048] x [2048,128]','FP32','FP32 software MAC candidate; not FP16 rate'),
      ('sigmoid','bias-free sigmoid scores','[B*S,128]','FP32','vector exp/reciprocal'),
      ('choicebias','add expert correction bias for choice only','[B*S,128]','FP32','vector'),
      ('groupscore','top2 within each 32-expert group then sum','[B*S,4]','FP32/index','selection/reduce'),
      ('groupselect','select 2 groups; mask other groups','[B*S,128]','FP32/index','selection/vector'),
      ('top8','unsorted Top8 expert indices','[B*S,8]','index','selection; record actual returned slots'),
      ('gather','gather uncorrected sigmoid scores at indices','[B*S,8]','FP32','gather'),
      ('weight','normalize + 1e-20; scale2.5; cast','[B*S,8]','FP32 -> BF16','vector/reduce'),
      ('padweight','if semantic padding: mask then renormalize +1e-9, scale2.5','[B*S,8]','source BF16 operation boundaries','vector/reduce'),
      ('pack','nonzero slots; stable expert sort; counts and inverse permutation','sum m_e = effective nonzero slots','int + BF16','DMA/vector; EP is candidate only'),
      ('expertpad','grouped_mm align8; min8 slots even empty experts','mhat_e=8*ceil(max(m_e,8)/8)','BF16 zeros + indices','source extra padded arithmetic'),
      ('expert_gate','routed w1 batched expert GEMM','[mhat_e,H] x [H,768]','BF16','matrix candidate / HB weight-ready'),
      ('expert_up','routed w3 batched expert GEMM','[mhat_e,H] x [H,768]','BF16','matrix candidate / HB weight-ready'),
      ('expert_silu','SiLU gate output','[mhat_e,768]','BF16 boundary','vector'),
      ('expert_mul','multiply SiLU(gate) by up','[mhat_e,768]','BF16','vector'),
      ('expert_down','routed w2 GEMM','[mhat_e,768] x [768,H]','BF16','matrix candidate'),
      ('unpad','remove grouped padding; restore packed assignment order','[sum m_e,H]','BF16','DMA/vector'),
      ('restore','restore original token and unsorted Top8 slot axes','logical [B*S,8,H]','BF16 expert output','DMA/vector; stream to avoid materialization'),
      ('weighted','FP32 product and sum over original slot axis; cast','[B*S,H]','FP32 -> BF16','vector/reduce; no arbitrary rank order'),
      ('shared_gate','shared gate GEMM, one shared expert','[B*S,H] x [H,768]','BF16','matrix; independent of routed Top8'),
      ('shared_up','shared up GEMM','[B*S,H] x [H,768]','BF16','matrix'),
      ('shared_silu','shared SiLU','[B*S,768]','BF16','vector'),
      ('shared_mul','shared gate/up product','[B*S,768]','BF16','vector'),
      ('shared_down','shared down GEMM','[B*S,768] x [768,H]','BF16','matrix'),
      ('sum','add routed and shared outputs','[B,S,H]','BF16','vector'),
      ('postffn','post-FFN RMSNorm','[B,S,H]','FP32 accumulation -> input dtype','vector/reduce'),
      ('gateffn','multiply tanh gate; cast to residual dtype','[B,S,H]','FP32 -> residual dtype','vector'),
      ('resffn','add FFN residual','[B,S,H]','residual dtype','vector'),
    ]
    for key,op,shape,dt,tar in specs:
        if key in {'q','k','v','qn','kn','qr','kr','qk','softmax','av','out'}:
            bound=anchor(T,'class LingBotVideoAttention')
        elif key in {'router','sigmoid','choicebias','groupscore','groupselect','top8','gather','weight'}:
            bound=anchor(T,'class LingBotVideoRouter')
        elif key in {'padweight','sum'}:
            bound=anchor(T,'def forward(self, hidden_states: torch.Tensor, padding_mask:')
        elif key in {'pack','expertpad','expert_gate','expert_up','expert_silu','expert_mul','expert_down','unpad','restore','weighted'}:
            bound=anchor(T,'class LingBotVideoSparseMoeBlock')
        elif key.startswith('shared_'):
            bound=anchor(T,'class LingBotVideoMLP')
        else:bound=source
        node(pf+key,op,shape,dt,tar,bound,layer=layer)
        if layer==0: inventory.append(dict(operator=key,semantics=op,shape=shape,dtype=dt,target_candidate=tar,repeat='48 blocks / each DiT call',source_file=bound['file'],source_line=bound['line']))
    def ed(a,b):edge(pf+a,pf+b)
    edge(previous,pf+'norm1'); edge(previous,pf+'resattn');edge('pre.cp_boundary',pf+'mod')
    for a,b in [('mod','affine1'),('mod','gateattn'),('mod','affine2'),('mod','gateffn'),('norm1','affine1'),('affine1','q'),('affine1','k'),('affine1','v'),('q','qn'),('k','kn'),('qn','qr'),('kn','kr'),('qr','qk'),('kr','qk'),('qk','softmax'),('softmax','av'),('v','av'),('av','out'),('out','postattn'),('postattn','gateattn'),('gateattn','resattn'),('resattn','norm2'),('norm2','affine2'),('affine2','router'),('router','sigmoid'),('sigmoid','choicebias'),('choicebias','groupscore'),('groupscore','groupselect'),('groupselect','top8'),('top8','gather'),('sigmoid','gather'),('gather','weight'),('weight','padweight'),('padweight','pack'),('affine2','pack'),('pack','expertpad'),('expertpad','expert_gate'),('expertpad','expert_up'),('expert_gate','expert_silu'),('expert_silu','expert_mul'),('expert_up','expert_mul'),('expert_mul','expert_down'),('expert_down','unpad'),('unpad','restore'),('pack','restore'),('restore','weighted'),('padweight','weighted'),('affine2','shared_gate'),('affine2','shared_up'),('shared_gate','shared_silu'),('shared_silu','shared_mul'),('shared_up','shared_mul'),('shared_mul','shared_down'),('shared_down','sum'),('weighted','sum'),('sum','postffn'),('postffn','gateffn'),('gateffn','resffn'),('resattn','resffn')]:ed(a,b)
    previous=pf+'resffn'
post=[('final_mod','SiLU + final time affine projection','H -> 2H','FP32','matrix/vector'),('ln','final LayerNorm; NOT RMSNorm','[B,S,H]','source mixed precision','vector/reduce'),('affine','apply final scale/shift','[B,S,H]','FP32 -> proj dtype','vector'),('proj','output projection before discarding text tokens','H -> 64 for ALL joint tokens','BF16','matrix'),('select','CP gather/unpad then select video tokens','[B,Nv,64]','BF16','NoC candidate / DMA'),('unpatch','unpatchify to predicted latent field','[B,16,Tz,Hz,Wz]','BF16 -> pipeline FP32','DMA/vector')]
for key,op,shape,dt,tar in post:node('post.'+key,op,shape,dt,tar,anchor(T,'final_mod ='))
edge(previous,'post.ln');edge('pre.cp_boundary','post.final_mod');edge('post.final_mod','post.affine');edge('post.ln','post.affine')
for a,b in [('affine','proj'),('proj','select'),('select','unpatch')]:edge('post.'+a,'post.'+b)

def audit_graph(ns,es):
    ids={x['id'] for x in ns}; assert len(ids)==len(ns)
    adj=collections.defaultdict(list);ind={x:0 for x in ids}
    for e in es:
        assert e['src'] in ids and e['dst'] in ids
        adj[e['src']].append(e['dst']);ind[e['dst']]+=1
    todo=[x for x in ids if not ind[x]];n=0
    while todo:
        a=todo.pop();n+=1
        for b in adj[a]:
            ind[b]-=1
            if not ind[b]:todo.append(b)
    assert n==len(ns);return dict(nodes=n,edges=len(es),acyclic=True)

audit = audit_graph(nodes,edges)
dump('DIT_FORWARD_48.json',dict(kind='SYMBOLIC_SOURCE_DAG_NOT_EXECUTED',S='Nv + branch-specific L; CP padding separate',expert_loop='conditional macro, not 128 executed nodes',nodes=nodes,edges=edges))
csvout('DIT_NODES.csv',[dict(**{k:v for k,v in x.items() if k!='source'},source_file=x['source']['file'],source_line=x['source']['line']) for x in nodes]);csvout('DIT_EDGES.csv',edges)

# Finite source-request template. Macro calls refer to the full forward graph above.
rn=[];re=[]
def rnadd(i,op):rn.append(dict(id=i,op=op,scope='REQUEST_TEMPLATE_NOT_TRACE'))
def readd(a,b,kind='data_completion'):re.append(dict(src=a,dst=b,kind=kind))
for i,op in [('input','image + official JSON; no rewriter/refiner'),('preprocess','crop/normalize image; VLM resize'),('vlm_pos','Qwen3-VL image + positive text encoding'),('vlm_neg','Qwen3-VL image + negative text encoding'),('vae_enc','image VAE encode/sample/latent scale'),('noise','seeded latent RNG'),('init','initial image-latent overwrite'),('schedule','FlowUniPC timestep schedule')]:rnadd(i,op)
for a,b in [('input','preprocess'),('preprocess','vlm_pos'),('vlm_pos','vlm_neg'),('preprocess','vae_enc'),('vae_enc','init'),('noise','init'),('init','schedule')]:readd(a,b)
readd('vlm_neg','vae_enc','source_sequential_setup_order')
last='schedule'
for step in range(40):
    pf=f'S{step:02d}.'
    for i,op in [('cond','48-block conditional DiT macro'),('uncond','48-block unconditional DiT macro'),('cfg','FP32 uncond + g*(cond-uncond)'),('scheduler','FlowUniPC state/history + latent update'),('inpaint','overwrite conditioned initial latent slices')]:rnadd(pf+i,op)
    readd(last,pf+'cond');readd('vlm_pos',pf+'cond');readd(last,pf+'uncond');readd('vlm_neg',pf+'uncond');readd(pf+'cond',pf+'uncond','source_sequential_cfg_order')
    readd(pf+'cond',pf+'cfg');readd(pf+'uncond',pf+'cfg');readd(pf+'cfg',pf+'scheduler');readd(last,pf+'scheduler');readd(pf+'scheduler',pf+'inpaint');readd('vae_enc',pf+'inpaint');last=pf+'inpaint'
for i,op in [('vae_decode','inverse latent scaling + Wan temporal-cache VAE decode'),('post','clamp/normalize/video encoding and file output')]:rnadd(i,op)
readd(last,'vae_decode');readd('vae_decode','post')
ra=audit_graph(rn,re);dump('REQUEST_40STEP_TEMPLATE.json',dict(kind='FINITE_TEMPLATE_NOT_MEASURED_TRACE',steps=40,cfg='sequential two-branch, guidance3',dit_macro_reference='DIT_FORWARD_48.json',nodes=rn,edges=re))

# Header accounting, not inferred from model names or rounded parameter counts.
header=json.loads((P/'MODEL_HEADER_AUDIT.json').read_text(encoding='utf8'))
tensor_by_name={r['name']:r for r in header['parts']['transformer']}
for layer in range(48):
    for suffix,shape,dt in [('attn.to_q.weight',[2048,2048],'BF16'),('attn.to_k.weight',[2048,2048],'BF16'),('attn.to_v.weight',[2048,2048],'BF16'),('attn.norm_q.weight',[128],'F32'),('ffn.router.weight',[128,2048],'F32'),('ffn.experts.w1',[128,768,2048],'BF16'),('ffn.experts.w2',[128,2048,768],'BF16'),('ffn.experts.w3',[128,768,2048],'BF16'),('ffn.shared_experts.gate_proj.weight',[768,2048],'BF16'),('scale_shift_table',[1,12288],'F32')]:
        entry=tensor_by_name[f'blocks.{layer}.{suffix}'];assert entry['shape']==shape and entry['dtype']==dt
capacity=dict(header_summary=header['summary'],HB_bytes=8*2**30,HB_per_rank_bytes=512*2**20,
  SRAM_per_rank_bytes=4*2**20,source_frame_case=dict(frames=121,height=480,width=832,latent=[1,16,31,60,104],video_tokens=48360,text_tokens='L_cond and L_uncond measured later'),
  routed_expert_bytes=3*H*I*2,shared_expert_bytes=3*H*I*2,
  routed_all_layers_bytes=D*E*3*H*I*2,all_layer_EP16_routed_bytes_per_rank=D*8*3*H*I*2,
  single_layer_EP16_routed_bytes_per_rank=8*3*H*I*2,
  example_video_only_hidden_BF16_bytes=48360*H*2,
  example_video_only_temb6_FP32_bytes=48360*6*H*4,
  example_video_only_attention_scores_FP32_bytes=16*48360**2*4,
  example_compact_routes_uint16_BF16_bytes_lower_bound=40*2*48*48360*8*4,
  example_full_router_FP32_array_bytes_lower_bound=40*2*48*48360*128*4,
  source_default_restore_unsorted_BF16_bytes_lower_bound=48360*K*H*2,
  source_default_restore_unsorted_FP32_cast_bytes_lower_bound=48360*K*H*4,
  recommended_host_backing_candidate_bytes=128*2**30,
  host_overlay_status='PROPOSAL_NOT_SELECTED_OR_EXECUTED; original host8GiB unchanged',
  HB_fit=False,whole_model_residency='BLOCKED_ON_CANONICAL_HOST8_HB8',peak_liveness='UNPROVEN',
  mac_per_block='4*S*H^2 + 2*S^2*H + S*H*128 + 3*H*I*(sum mhat_e + Nshared); effective sum m_e <= 8*Nvalid; grouped padded sum mhat_e separately',
  throughput='No BF16 or FP32 matrix rate inferred from FP16 specification')
dump('CAPACITY.json',capacity)

# Conditioning stages have their own operator families, not MoE experts.
condition=[
 ('vlm_image','patch Conv3d 3->1024, temporal2/spatial16; positional interpolation + 2D RoPE','BF16','matrix Conv lowering + vector','Qwen3VL vision',24),
 ('vlm_vision_block','LayerNorm -> QKV MHA -> O/residual -> LayerNorm -> FC1/GELU/FC2/residual','BF16/mixed norms','TP/sequence candidate','no expert routing',24),
 ('vlm_merger','main merger and deepstack mergers at vision blocks5/11/17','BF16','vector + matrix','4-patch merge to2560',4),
 ('vlm_embedding','text embedding lookup + image feature scatter + mRoPE ids','BF16/int','HB/DMA + vector','Qwen3VL text core, no LM head',1),
 ('vlm_text_block','RMSNorm -> GQA QKV/QKnorm/mRoPE -> causal attention -> O/residual -> RMSNorm -> dense SwiGLU/residual','BF16/mixed norms','TP candidate, KV behaviour must be observed','36 layers H2560,32Q/8KV heads128,I9728',36),
 ('vlm_deepstack','inject 3 merged visual features into first 3 text layers at image positions','BF16','vector/scatter','not final-three/vision-layer indices in text',3),
 ('vlm_output','final norm, hidden-state selection, prefix crop, mask crop; batch1 right-padding removal','BF16','vector/DMA','conditioning embeddings not generated text',1),
 ('vae_encode','causal Conv3d -> 4 resolution stages/residual convs -> mid attention/residual -> norm/SiLU/conv -> quant Conv -> Gaussian sample','FP32 weights; image encode CUDA BF16 autocast in pipeline','FP32 Conv software/vector candidate; host/GPU alternative scope','cond image encode only',1),
 ('vae_residual','RMS normalize -> SiLU -> causalConv3d -> norm/SiLU/dropout(eval) -> causalConv3d + shortcut','FP32/source autocast boundaries','conv tiling; temporal halo/cache completion','encode/decode macro template','dynamic'),
 ('vae_mid_attention','per-frame spatial QKV Conv2d -> SDPA -> output Conv2d + residual','FP32/mixed kernel','attention/vector + Conv','mid block exists despite attn_scales=[]','dynamic'),
 ('vae_decode','post_quant Conv -> causal Conv -> mid block -> 4 up stages/residual/resample -> norm/SiLU/outputConv; temporal feature cache','FP32 default decode','tiled Conv/vector or external reference scope','stage channels from source/config; first chunk differs',1),
 ('scheduler','FlowUniPC multistep predictor/corrector, history shift, scalar solves and latent affine; conditioned-slice overwrite','FP32 latent; source scalar precision retained','host initially, explicit gateway cost','not one independent Euler add per step',40),
]
condrows=[dict(operator=a,semantics=b,dtype=c,target_candidate=d,scope=e,repeat=f) for a,b,c,d,e,f in condition]
inventory+=condrows;csvout('OPERATOR_INVENTORY.csv',inventory)
dump('CONDITIONING_SCOPE.json',dict(kind='SOURCE_AND_DEPENDENCY_BOUND_MACRO_DECOMPOSITION_NOT_RUNTIME_KERNEL_TRACE',operators=condrows,
  vlm_reference='source/modeling_qwen3_vl_v5_8_1.py',vae_reference='source/autoencoder_kl_wan_v0_39_0.py',
  remaining='per-tile shapes, backend fusion, temporal/cache schedule and full conditioning device lowering require captured fixture; no claim of complete target execution'))

mapping=dict(status='PROPOSED_NOT_EXECUTED',canonical_architecture='../whisper_operator_inventory/target_architecture_v3_6/target_architecture_v3_6.yaml',
  hardware=dict(NPUs=16,mesh='4x4 + gateway',HB_GiB=8,CH_MiB=512,SRAM_MiB_per_NPU=4,SRAM_banks=8,logical_projected_DRAM_banks=4,decoded_DRAM_banks=16,transaction_B=32,HB_GBps_per_pair=25.6),
  reference_contract='TP16 attention + EP16 routed experts, sequential CFG; alternative CP/DP separate',
  attention=dict(type='MHA not GQA in DiT',head_owner='head h -> N_h, all 16 heads partitioned once',qkv_columns_per_rank=128,
    hidden='replicated/tiled Sx2048 after collective; footprint and liveness need proof',O='row shard partial -> sum collective, bias exactly once after sum',norm='FP32 RMS source boundary, Q/K scale [128] shared across heads',
    communication='QKV weights TP shards; O partial allreduce via reduce-scatter/allgather lowering; cannot add source CP all-to-alls simultaneously'),
  expert=dict(owner='p_l(e)=e mod16 baseline; 8 experts per rank/layer',token_origin='o(t)=global joint-token index mod16',
    router='one FP32 decision per token at unique origin; replicated 1MiB router weight/rank candidate',dispatch='send unique assignment only after actual route known; local assignment has no NoC payload',
    combine='return owner output to token origin, restore actual Top8 slot order, FP32 multiply/sum then BF16 cast',shared='replicate 9MiB shared weights per rank/layer; execute each token only at unique origin, not16 times',
    next_layer='allgather combined joint hidden for TP attention; no allgather before completion',source_EP=False),
  source_CP=dict(type='Ulysses-style sequence/head all-to-all; 3 QKV exchanges plus1 output exchange',candidate_degree='4 or16 head divisors with explicit sequence padding; not selected',
    relation_to_TP='alternative mutually exclusive contraction, not extra traffic added to TP16'),
  source_DP=dict(type='whole independent image/prompt samples only',limitation='cannot rebatch arbitrary video tokens as independent attention sequences; total token budget and output identity preserved'),
  memory=dict(host_backing='capacity overlay candidate128GiB; not authorized/selected here',read_only_weights=True,dirty_weight_eviction_D2H=False,
    completion='host read -> PCIe/gateway -> HB install -> validity -> SRAM DMA -> compute; no offline additive latency',weights='whole model is not resident in8GiBHB; per-layer paging and tile reuse mandatory'),
  precision=dict(BF16='not certified by FP16 array',FP32_router='vector/software MAC or separately calibrated path',special_functions='exp/sigmoid/tanh/rsqrt/complexRoPE/TopK/scatter require semantics and timing gates'),
  HiBand=dict(type='independent reference integration, not author artifact reproduction',phases='local/global bytes classify; static baseline first; dynamic drain/setup/switch buffers on completion paths',
    scope='partition modes and HB/NoC arbitration; not bandwidth*4 logical banks'),
  SemMoE=dict(type='port model/data co-scheduling contract; existing alternating co-clustering is approximate',
    profile_key='sample/scene + step band + CFG branch + layer + joint token type/position embedding; unseen content correspondence unproven',
    causality='freeze placement and predictor before heldout; current realized router output usable after router only; future steps unknown',
    gate='no affinity predictor quality -> no online Sem-MoE gain claim; oracle separate'))
dump('MAPPING.json',mapping)

# Symbolic completion graph for one TP16/EP16 target block.
# Communication count variables are not instantiated without real routes.
mn=[];me=[]
def madd(i,op,rank=None,**kw):mn.append(dict(id=i,op=op,rank=rank,scope='TARGET_CANDIDATE_NOT_EXECUTED',**kw))
def med(a,b):me.append(dict(src=a,dst=b,kind='completion_gate'))
for ident,op in [('input','joint input / temb6 ready'),('o_reduce','O partial reduce-scatter + allgather completion'),('next_hidden','combined token hidden allgather completion')]:madd(ident,op)
for rank in range(16):
    pf=f'N{rank:02d}.'
    for i,op in [('weight','host read -> PCIe/gateway -> CH install validity'),('sram','CH read -> SRAM tile ready'),('norm','FP32 norm/affine + QK norm/RoPE'),('attn','one head noncausal tiled QK/softmax/AV'),('o','O row partial no bias'),('ffn','O bias once -> postnorm/gate/residual -> norm/affine'),('origin','select unique token origins t mod16'),('router','FP32 router/group-limited Top8'),('expert_ready','tokens from all origins + owned expert weight tiles ready'),('expert','8 owned experts conditional GEMMs; padding arithmetic separate'),('shared','shared expert for own origin tokens only'),('combine','collect original Top8 slots -> FP32 weighted sum -> shared add'),('residual','postFFN RMSNorm/gate/residual on own origin tokens')]:madd(pf+i,op,rank=rank,CH=f'CH{rank}',transaction_B=32)
    for a,b in [('weight','sram'),('sram','attn'),('norm','attn'),('attn','o'),('ffn','origin'),('origin','router'),('router','shared'),('expert_ready','expert'),('shared','combine'),('combine','residual')]:med(pf+a,pf+b)
    med('input',pf+'norm');med(pf+'o','o_reduce');med('o_reduce',pf+'ffn');med(pf+'sram',pf+'expert_ready');med(pf+'residual','next_hidden')
for origin in range(16):
    for owner in range(16):
        prefix=f'flow.{origin:02d}.{owner:02d}.'
        for key,op in [('dispatch','local bypass' if origin==owner else 'conditional routed token transfer'),('return','local bypass' if origin==owner else 'conditional expert output return')]:
            madd(prefix+key,op,src_rank=origin if key=='dispatch' else owner,dst_rank=owner if key=='dispatch' else origin,
                 enable=f'n[{origin},{owner}] > 0',payload_bytes='0 NoC' if origin==owner else f'n[{origin},{owner}]*2048*2 plus metadata',
                 metadata='sample,step,branch,layer,global-token,actual-slot,expert; count and weight dtype explicitly costed')
        med(f'N{origin:02d}.router',prefix+'dispatch');med(prefix+'dispatch',f'N{owner:02d}.expert_ready');med(f'N{owner:02d}.expert',prefix+'return');med(prefix+'return',f'N{origin:02d}.combine')
ma=audit_graph(mn,me)
dump('TARGET_LAYER_COMPLETION_GRAPH.json',dict(kind='SYMBOLIC_TP16_EP16_COMPLETION_TEMPLATE',n_assignments='n[origin,owner] derived only after actual route release; disabled edges produce no packets',nodes=mn,edges=me))
dump('COMMUNICATION_LEDGER.json',dict(kind='SYMBOLIC_NOT_MEASURED',flows=[x for x in mn if x['id'].startswith('flow.')],
     logical_assignment_total='sum n[o,r] = number of nonzero effective route slots; <=8*Nvalid (BF16 zero weights possible)',
     remote_dispatch='sum_{o!=r} n[o,r]*H*2 bytes plus route/identity metadata',remote_return='same output-width bytes; no metadata-free oracle',
     padding='grouped GEMM dummy slots create arithmetic but no semantic EP messages; source CP dummy sample separately bound',
     TP_collectives='O partial reduction plus hidden sync; buffer dtype and exact ring/tree schedules TBD',
     exclusive='do not also charge source Ulysses4-all-to-all under TP16',
     completion='Ramulator final transaction and PopNet final receive callbacks; injection is not completion'))
audit.update(request_template=ra,layer_count=D,operators_per_layer=len(specs),routes_measured=False,model_runs=0,target_runs=0,
  target_layer_completion_graph=ma,
  conditioning='macros with primitive families, not hidden kernel expansion',capacity_blocked=True,
  header_tensor_bytes=sum(x['tensor_bytes'] for x in header['summary'].values()))
dump('STRUCTURAL_AUDIT.json',audit)

# Native SVG plus Pillow previews, using the same box definitions.
FONT='C:/Windows/Fonts/msyh.ttc'
def figure(name,title,subtitle,boxes,arrows,w=1500,h=1000):
    colors={'source':('#eaf3ff','#306498'),'candidate':('#fff1d8','#987023'),'blocked':('#ffe9e9','#a94a4a'),'host':('#eef1f5','#637084')}
    im=Image.new('RGB',(w,h),'#ffffff');dr=ImageDraw.Draw(im)
    fnt=lambda n:ImageFont.truetype(FONT,n)
    dr.text((36,22),title,font=fnt(28),fill='#172b40');dr.text((36,64),subtitle,font=fnt(17),fill='#42586d')
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#60768b"/></marker></defs><rect width="100%" height="100%" fill="white"/>',f'<g font-family="Microsoft YaHei,Segoe UI,sans-serif"><text x="36" y="46" font-size="28" fill="#172b40">{html.escape(title)}</text><text x="36" y="87" font-size="17" fill="#42586d">{html.escape(subtitle)}</text>']
    lookup={x[0]:x for x in boxes}
    for a,b in arrows:
        aa,bb=lookup[a],lookup[b];_,x,y,bw,bh,_,_=aa;_,xx,yy,ww,hh,_,_=bb
        if yy>=y+bh:pts=[(x+bw/2,y+bh),(xx+ww/2,yy)]
        elif xx>=x+bw:pts=[(x+bw,y+bh/2),(xx,yy+hh/2)]
        else:pts=[(x+bw/2,y+bh),(xx+ww/2,yy)]
        dr.line(pts,fill='#60768b',width=3)
        px,py=pts[-1];dx,dy=px-pts[0][0],py-pts[0][1];ln=max(1,math.hypot(dx,dy));ux,uy=dx/ln,dy/ln
        dr.polygon([(px,py),(px-11*ux+5*uy,py-11*uy-5*ux),(px-11*ux-5*uy,py-11*uy+5*ux)],fill='#60768b')
        svg.append(f'<path d="M {pts[0][0]} {pts[0][1]} L {px} {py}" stroke="#60768b" stroke-width="2" fill="none" marker-end="url(#arrow)"/>')
    for key,x,y,bw,bh,lines,kind in boxes:
        bg,stroke=colors[kind];dr.rounded_rectangle((x,y,x+bw,y+bh),radius=10,fill=bg,outline=stroke,width=2)
        svg.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="10" fill="{bg}" stroke="{stroke}" stroke-width="2"/>')
        assert 15+len(lines)*26<=bh, key
        for j,line in enumerate(lines):
            font=fnt(18 if j else 20);assert dr.textbbox((0,0),line,font=font)[2]<=bw-24,(name,key,line)
            dr.text((x+12,y+12+j*26),line,font=font,fill='#19354c')
            svg.append(f'<text x="{x+12}" y="{y+32+j*26}" font-size="{20 if j==0 else 18}" fill="#19354c">{html.escape(line)}</text>')
    footer='蓝：源码语义  橙：候选映射  红：阻断  灰：外部/host边界；均非执行结果'
    dr.text((36,h-36),footer,font=fnt(17),fill='#42586d');svg.append(f'<text x="36" y="{h-18}" font-size="17" fill="#42586d">{footer}</text></g></svg>')
    (P/(name+'.svg')).write_text(''.join(svg),encoding='utf8');im.save(P/(name+'.png'))

figure('01_pipeline','基础 TI2V：请求与40步去噪任务图','固定 example_4 / 480×832 / 121帧 / seed42 / CFG3；结构模板，未运行',[
 ('in',480,120,540,78,['首帧图像 + 结构化 JSON','读取、resize/crop、processor/tokenize'],'host'),
 ('vlm',50,245,600,104,['Qwen3-VL 条件编码（正 / 负分支）','视觉24层 + 文本36层 + DeepStack注入','输出 embeddings/mask；不执行 LM head'],'source'),
 ('ve',850,245,600,104,['Wan VAE 图像编码 / RNG','Gaussian sample → cond_latent FP32','随机视频 latent → 首帧条件覆写'],'source'),
 ('step',430,400,640,78,['每个去噪步 s（40步顺序依赖）','释放 latent_s；time schedule/history 就绪'],'source'),
 ('cond',50,525,600,104,['条件分支 DiT forward','视频 + 条件文本联合序列 → 48个MoE block','patch/text/time embed → final projection'],'source'),
 ('un',850,525,600,104,['无条件分支 DiT forward','负条件编码仍包含首帧图像','参考路径顺序执行；CFG batch/并行另立合同'],'source'),
 ('cfg',430,680,640,104,['CFG → FlowUniPC → inpainting','uncond + 3 × (cond − uncond)','更新 latent/history 后才能进入 s+1'],'source'),
 ('dec',430,830,640,78,['最终 VAE decode → 视频写出','FP32 latent inverse scale；时序 cache/分块'],'source'),
 ],[('in','vlm'),('in','ve'),('vlm','step'),('ve','step'),('step','cond'),('step','un'),('cond','un'),('cond','cfg'),('un','cfg'),('cfg','dec')],h=1000)

figure('02_dit_block','DiT 单个 block：attention、调制与残差','48层共享同一模板；joint token = 视频 + 条件文本；final LayerNorm位于48层之后',[
 ('input',450,115,600,78,['输入 joint hidden + token-level temb6','learned shift/scale + tanh gates（FP32）'],'source'),
 ('n1',50,240,650,104,['Attention 前半链','RMSNorm → scale/shift → BF16 cast','Q / K / V projections（16头×128）'],'source'),
 ('n2',800,240,650,104,['FFN 前半链（等待 attention residual）','RMSNorm → scale/shift → BF16 cast','router 与 shared expert 共用输入'],'source'),
 ('att',50,400,650,130,['联合非因果 Attention','Q/K RMSNorm → 3D complex RoPE','tiled QK → mask/softmax → AV → O','TP16 或源 CP 为互斥候选，不叠加流量'],'source'),
 ('moe',800,400,650,130,['Routed MoE + shared expert','FP32 router → group choice → Top8','稳定 pack / grouped pad / expert GEMM','FP32 slot顺序加权 + shared（I=768）'],'source'),
 ('r1',50,590,650,104,['Attention 残差','norm_post_attn → tanh gate → cast','x + gated attention；完成后进入FFN'],'source'),
 ('r2',800,590,650,104,['FFN 残差','norm_post_ffn → tanh gate → cast','x + gated FFN → 下一 block'],'source'),
 ('last',450,775,600,104,['48层之后的输出头','final time modulation + LayerNorm + affine','proj ALL joint tokens → select视频 → unpatch'],'source'),
 ],[('input','n1'),('input','n2'),('n1','att'),('att','r1'),('r1','n2'),('n2','moe'),('moe','r2'),('r2','last')],h=980)

figure('03_moe','真实 MoE 语义：选择分数与加权分数分开','Source grouped_mm为本地专家计算；跨NPU dispatch/combine是后续候选lowering',[
 ('r',400,115,700,104,['FP32 router logits → sigmoid scores','选择时加入 correction bias','4组×32专家：组内Top2求和 → 选2组'],'source'),
 ('sel',400,265,700,104,['被选组内 unsorted Top8','实际权重 gather 无偏置 scores → normalize ×2.5','cast；如有语义mask再屏蔽 / normalize ×2.5'],'source'),
 ('pack',40,425,700,104,['routed path：稳定排序与 expert counts','去除 zero-weight assignment；保留 token/slot身份','grouped_mm 对齐8，空专家也有 padding算术'],'source'),
 ('shr',900,425,560,104,['shared path：独立1个共享专家','gate/up → SiLU× → down（I=768）','对全部 hidden 执行；不是第9个路由选择'],'source'),
 ('exp',40,580,700,104,['每专家 w1 / w3 → SiLU× → w2','BF16边界；去除grouped padding','目标owner必须先等token + 权重页完成'],'source'),
 ('ret',40,735,700,104,['恢复原 token × unsorted Top8 slot','FP32 multiply + 原slot轴sum → cast BF16','任意rank归约顺序不可直接视为等价'],'source'),
 ('sum',900,735,560,104,['routed + shared','norm_post_ffn / gate / residual','语义padding与实际dummy算术分别记账'],'source'),
 ],[('r','sel'),('sel','pack'),('pack','exp'),('exp','ret'),('ret','sum'),('shr','sum')],h=950)

figure('04_mapping','V3.6 候选映射与存储门槛','16 NPU / 8 GiB HB（每CH512MiB）/ 4MiB SRAM；非已执行方案',[
 ('host',35,120,460,130,['Host / 后备存储','原host8GiB容不下全模型','host128GiB仅建议overlay','PCIe/gateway成本必须进入DAG'],'blocked'),
 ('mesh',565,120,885,130,['16 NPU 4×4 Mesh + gateway','Ni 与 CHi 整体25.6 GB/s；规范32B事务','4逻辑Bank ≠ 16 decoded DRAM Bank ≠ 8 SRAM Bank','HB总8GiB；不可说每NPU8GiB'],'candidate'),
 ('att',35,330,675,130,['Attention-TP16 候选','每rank1个MHA头；QKV列分片 / O行分片','O partial → 完成驱动求和，bias仅一次','tiled noncausal attention；不重复加入CP通信'],'candidate'),
 ('ep',790,330,660,130,['EP16 routed专家候选','p_l(e)=e mod16，每层每rank8专家','unique token origin → dispatch → owner → return','按源Top8 slot恢复；shared仅在origin执行'],'candidate'),
 ('hb',35,540,675,130,['权重页 / SRAM tile 生命周期','host read → PCIe → HB install → SRAM DMA','每expert9MiB > 4MiB SRAM，需要分块','跨48层每rank routed3.375GiB > CH512MiB'],'blocked'),
 ('net',790,540,660,130,['HiBand + Sem-MoE 分别验收','固定模式基线 → 动态drain/setup/switch','布局/profile先冻；真实router后才允许本步dispatch','未来去噪路由不可偷看；shared不算routed命中'],'candidate'),
 ('gate',300,755,900,104,['数值 / 容量 / 因果门未通过前，不运行收益矩阵','BF16与FP32矩阵不能套FP16吞吐；特殊函数、TopK、scatter另核','先真实fixture → 单片段 → 单层 → 相邻步 → 四组公平对照'],'blocked'),
 ],[('host','mesh'),('mesh','att'),('mesh','ep'),('att','hb'),('ep','net'),('hb','gate'),('net','gate')],h=980)

titles=[('01_pipeline','TI2V任务图'),('02_dit_block','DiT单层拆分'),('03_moe','MoE路由与合并'),('04_mapping','V3.6候选映射')]
buttons=''.join(f'<button onclick="show({i})">{t}</button>' for i,(_,t) in enumerate(titles))
panels=''.join(f'<section id="p{i}" style="display:{"block" if i==0 else "none"}"><img src="{n}.svg" alt="{t}"/><p><a href="{n}.png">PNG</a> · <a href="{n}.svg">SVG</a></p></section>' for i,(n,t) in enumerate(titles))
(P/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>LingBot TI2V结构图</title><style>body{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:24px;color:#19354c}button{padding:10px;margin:5px;border:1px solid #9bb3c9;background:#edf5fc;cursor:pointer}img{width:100%;max-width:1500px}p{max-width:1100px;line-height:1.7}</style><h1>LingBot TI2V：算子、任务图与目标映射</h1><p>结构交付，模型与模拟器运行均0。蓝色为源码语义；橙色为候选映射；红色为阻断。原精度不改，不含refiner。</p>'+buttons+panels+'<p><a href="REPORT.md">报告</a> · <a href="EXPERIMENT_PLAN.md">后续实验计划</a> · <a href="OPERATOR_INVENTORY.csv">算子清单</a> · <a href="CAPACITY.json">容量账本</a> · <a href="DIT_FORWARD_48.json">48层DAG</a></p><script>function show(i){for(let j=0;j<4;j++)document.getElementById("p"+j).style.display=j===i?"block":"none"}</script>',encoding='utf8')

sources=[]
for f in sorted(SRC.rglob('*')):
    if f.is_file():sources.append(dict(path=str(f.relative_to(P)).replace('\\','/'),bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()))
dump('SOURCE_MANIFEST.json',sources)
print(json.dumps(dict(dit=audit,request=ra,capacity=capacity),ensure_ascii=False))
