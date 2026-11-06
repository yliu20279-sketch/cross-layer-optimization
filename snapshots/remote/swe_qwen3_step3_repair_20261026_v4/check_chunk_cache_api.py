"""Small synthetic CPU API check, not original-checkpoint evidence."""
import json
from pathlib import Path
import torch
from transformers import Qwen3MoeConfig,Qwen3MoeForCausalLM
torch.set_num_threads(1);torch.manual_seed(20261026)
config=Qwen3MoeConfig(vocab_size=128,hidden_size=32,intermediate_size=64,moe_intermediate_size=32,num_hidden_layers=2,num_attention_heads=2,num_key_value_heads=1,head_dim=16,num_experts=4,num_experts_per_tok=2,max_position_embeddings=128,bos_token_id=1,eos_token_id=2,pad_token_id=0,attn_implementation='eager')
model=Qwen3MoeForCausalLM(config).to(torch.bfloat16).eval()
records=[]
with torch.inference_mode():
    for length in [17,32,33]:
        ids=torch.randint(3,128,(1,length))
        full=model.generate(input_ids=ids,attention_mask=torch.ones_like(ids),max_new_tokens=5,do_sample=False,use_cache=True,logits_to_keep=1)
        cache=None
        for begin in range(0,length-1,8):
            end=min(begin+8,length-1)
            out=model(input_ids=ids[:,begin:end],attention_mask=torch.ones((1,end),dtype=torch.long),past_key_values=cache,use_cache=True,logits_to_keep=1,return_dict=True)
            cache=out.past_key_values
        assert cache.get_seq_length()==length-1
        chunk=model.generate(input_ids=ids,attention_mask=torch.ones_like(ids),past_key_values=cache,max_new_tokens=5,do_sample=False,use_cache=True,logits_to_keep=1)
        assert torch.equal(full,chunk),(full,chunk)
        records.append(dict(prompt_tokens=length,equal_tokens=True))
(Path(__file__).resolve().parent/'CHUNK_CACHE_CPU_CHECK.json').write_text(json.dumps(dict(state='PASS_SYNTHETIC_CPU_API_ONLY',cases=records,CUDA_initialized=torch.cuda.is_initialized()),indent=2))
