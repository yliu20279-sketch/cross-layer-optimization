"""Same model/inputs, source vs skip-empty loop, exact outputs/routes before agent use."""
import time,torch,json,types
import backend as b

def validate(backend):
    layer=backend.model.model.layers[0].mlp;original=b.qwen_module.Qwen3MoeSparseMoeBlock.forward
    shapes=[1,7,257];checks=[]
    # Real checkpoint layer0, synthetic values. Same kernels and ascending accumulation.
    for n in shapes:
        torch.manual_seed(20261027+n);x=torch.randn(1,n,2048,device='cuda',dtype=torch.bfloat16)
        with torch.inference_mode():reference=original(layer,x)
        backend.skip_empty_experts=True;backend.instrument()
        with torch.inference_mode():candidate=layer(x)
        checks.append(dict(tokens=n,output_bitwise=torch.equal(reference[0],candidate[0]),router_bitwise=torch.equal(reference[1],candidate[1])))
        assert all(checks[-1][k] for k in ['output_bitwise','router_bitwise'])
    # Full model short greedy generation and each last-logit vector, no route fixture copies.
    messages=[dict(role='user',content='Write a Python function that returns the sum of a list. Be brief.')]
    backend.decoding=dict(do_sample=False);backend.thinking=False
    for module in backend.model.model.layers:module.mlp.forward=types.MethodType(original,module.mlp)
    logits=[]
    hook=backend.model.register_forward_hook(lambda m,a,k,o:logits.append(o.logits.detach().cpu()),with_kwargs=True)
    baseline=backend.generate(messages,'backend_source_gate',24,False)
    source_logits=logits[:];logits.clear()
    backend.skip_empty_experts=True;backend.instrument()
    candidate=backend.generate(messages,'backend_skip_empty_gate',24,False)
    hook.remove()
    assert baseline['new_token_ids']==candidate['new_token_ids']
    assert len(source_logits)==len(logits) and all(torch.equal(x,y) for x,y in zip(source_logits,logits))
    result=dict(state='PASS_LIMITED_EXACT_OUTPUT',synthetic_real_layer0=checks,whole_model_short_generated_tokens_equal=True,whole_model_short_logits_bitwise=True,
        source_seconds=baseline['generation_wall_seconds'],optimized_seconds=candidate['generation_wall_seconds'],
        scope='same original BF16 checkpoint, eager operations and ascending accumulation; limited equivalence checks, not arbitrary input/NPU certification')
    b.save(b.ROOT/'BACKEND_EQUIVALENCE.json',result);return result
