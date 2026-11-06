"""Independent installed Transformers CPU layer comparison; no promotion.

Loads ONLY the selected layer's real decoded/BF16 parameters. Never constructs
the full language model, invokes CUDA, changes target outputs, or fits tests.
"""
from pathlib import Path
import argparse
import hashlib
import inspect
import json
import sys
import time
import numpy as np
import torch
import transformers
from transformers.cache_utils import DynamicCache
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.artifacts import TargetArtifactStore
from core.common import require,file_hash

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--model',required=True,choices=['qwen15','qwen3'])
parser.add_argument('--run-tag',default='layer01')
args=parser.parse_args()
torch.set_num_threads(1);torch.set_num_interop_threads(1)
available=next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
require(available>=4*1024**3,'insufficient spare memory for one-layer CPU reference')
run=ROOT/'runs'/(args.model+'_'+args.run_tag)
require((run/'RESULT.json').is_file(),'native layer receipt required first')
out=run/'independent_cpu_reference';out.mkdir(exist_ok=False)
if args.model=='qwen15':
    from transformers.models.qwen2_moe.modeling_qwen2_moe import Qwen2MoeConfig as Config,Qwen2MoeDecoderLayer as Layer,Qwen2MoeRotaryEmbedding as Rotary
    from transformers.models.qwen2_moe.modeling_qwen2_moe import Qwen2MoeSparseMoeBlock as MoE
    dtype=torch.float16;manifest=list(json.loads((ROOT/'contracts/qwen15_tensor_inventory.json').read_text())['objects'].values())
else:
    from transformers.models.qwen3_moe.modeling_qwen3_moe import Qwen3MoeConfig as Config,Qwen3MoeDecoderLayer as Layer,Qwen3MoeRotaryEmbedding as Rotary
    from transformers.models.qwen3_moe.modeling_qwen3_moe import Qwen3MoeSparseMoeBlock as MoE
    dtype=torch.bfloat16;manifest=json.loads((ROOT/'contracts/qwen3_target_manifest.json').read_text())
storage='F16' if dtype==torch.float16 else 'BF16'
store=TargetArtifactStore(manifest,storage)
config=Config(**json.loads((ROOT/('upstream/'+args.model+'_config.json')).read_text()))
config._attn_implementation='eager'
with torch.device('meta'):layer=Layer(config,layer_idx=0)
state={}
for key in layer.state_dict():
    name='model.layers.0.'+key;obj=store.objects[name]
    raw=store.read(name,0,obj['bytes'])
    tensor=torch.from_numpy(np.frombuffer(raw,dtype='<u2').copy()).view(dtype).reshape(obj['shape'])
    if obj['layout']=='input_major':tensor=tensor.T.contiguous()
    state[key]=tensor
layer.load_state_dict(state,strict=True,assign=True);layer.eval();del state
rotary=Rotary(config=config)
cache=DynamicCache();router=[]
layer.mlp.gate.register_forward_hook(lambda module,inputs,output:router.append(output.detach().clone()))
source=Path(inspect.getfile(Layer))
(out/'MOE_FORWARD_SOURCE.txt').write_text(inspect.getsource(MoE.forward))
(out/'LAYER_FORWARD_SOURCE.txt').write_text(inspect.getsource(Layer.forward))
native=json.loads((run/'RESULT.json').read_text());phases=[]
def decode(raw):return torch.from_numpy(np.frombuffer(raw,dtype='<u2').copy()).view(dtype)
def compare(actual,expected):
    actual=actual.reshape(-1);expected=expected.reshape(-1)
    require(actual.shape==expected.shape,'reference shape differs')
    diff=(actual.float()-expected.float()).abs()
    return {'elements':actual.numel(),'different_storage_bits':int((actual.view(torch.int16)!=expected.view(torch.int16)).sum()),
            'maxabs':float(diff.max()),'meanabs':float(diff.mean()),'finite':bool(torch.isfinite(actual).all() and torch.isfinite(expected).all())}
with torch.inference_mode():
    for index,phase in enumerate(['prefill','decode']):
        hidden=decode((run/(phase+'_input.bin')).read_bytes()).reshape(1,1,config.hidden_size)
        positions=torch.tensor([[index]],dtype=torch.long);cache_pos=positions.flatten()
        cos,sin=rotary(hidden,positions)
        mask=torch.zeros((1,1,1,index+1),dtype=dtype)
        reference=layer(hidden,attention_mask=mask,position_ids=positions,past_key_value=cache,
                        use_cache=True,cache_position=cache_pos,position_embeddings=(cos,sin))[0]
        target=decode((run/(phase+'_output.bin')).read_bytes())
        (out/(phase+'_output.bin')).write_bytes(reference.contiguous().view(torch.uint16).numpy().tobytes())
        logits=router[-1].reshape(-1)
        probs=torch.softmax(logits,dim=-1,dtype=torch.float32)
        values,selected=torch.topk(probs,config.num_experts_per_tok)
        if config.norm_topk_prob:values=values/values.sum()
        values=values.to(dtype)
        route=native['phases'][index]['routes'][0]
        kv=[]
        for entry in json.loads((run/(phase+'_KV_PAYLOADS.json')).read_text()):
            heads=config.num_attention_heads;kv_heads=config.num_key_value_heads;tp=native['TP'];per=heads//tp
            begin=(entry['rank']*per)//(heads//kv_heads);end=((entry['rank']*per+per-1)//(heads//kv_heads))+1
            ref=(cache.key_cache[0] if entry['member']=='k' else cache.value_cache[0])[0,begin:end].transpose(0,1).contiguous()
            observed=decode((run/entry['file']).read_bytes()).reshape(ref.shape)
            kv.append({'rank':entry['rank'],'member':entry['member'],**compare(observed,ref)})
        phases.append({'phase':phase,**compare(target,reference),
            'target_selected':route['selected'],'reference_selected':selected.tolist(),
            'selected_set_equal':set(route['selected'])==set(selected.tolist()),
            'target_selected_mass':sum(route['weights']),'reference_selected_mass':float(values.float().sum()),
            'KV':kv})
receipt={'status':'COMPARED_NO_NUMERICAL_PROMOTION','scope':'independent installed eager CPU decoder layer, not a GPU/full model',
    'model':args.model,'torch_version':torch.__version__,'transformers_version':transformers.__version__,
    'implementation_file':str(source),'implementation_sha256':file_hash(source),'norm_topk_prob':config.norm_topk_prob,
    'reference_expert_accumulation':'ascending expert id via index_add, as captured source',
    'target_expert_accumulation':json.loads((run/'PROTOCOL.json').read_text()).get('expert_accumulation','TopK slot order in frozen layer01 candidate'),
    'phases':phases,'target_outputs_modified':False,'reference_layer_calls':2,'complete_model_forwards':0,'GPU_runs':0,
    'formal_performance_runs':0,'original_model_bit_exact_verified':False}
(out/'COMPARISON.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps({'model':args.model,'status':receipt['status'],'phases':[{k:v for k,v in p.items() if k!='KV'} for p in phases]}))
