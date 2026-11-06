"""Real cached teacher-forced decode routes; no synthetic routing."""
import argparse,csv,gzip,hashlib,json,time
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

def main():
    a=argparse.ArgumentParser()
    for k in ('model','dataset','out'): a.add_argument('--'+k,required=True)
    a.add_argument('--context',type=int,default=128); a.add_argument('--decode',type=int,default=8); a.add_argument('--requests',type=int,default=1)
    a.add_argument('--profile-requests',type=int,default=0); a.add_argument('--selection-tokens',type=int,default=0)
    args=a.parse_args(); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    tok=AutoTokenizer.from_pretrained(args.model,local_files_only=True)
    records=json.loads(Path(args.dataset).read_text()); chosen=[]
    for index,r in enumerate(records):
        turns=r.get('conversations',r.get('messages',[])); messages=[]
        for t in turns:
            role={'human':'user','gpt':'assistant','system':'system','user':'user','assistant':'assistant'}.get(t.get('from',t.get('role')))
            content=t.get('value',t.get('content',''))
            if role and isinstance(content,str) and content.strip(): messages.append({'role':role,'content':content})
        if len(messages)<2: continue
        ids=tok.apply_chat_template(messages,tokenize=True,add_generation_prompt=False,enable_thinking=False)
        if len(ids)<max(args.selection_tokens,args.context+args.decode): continue
        rid=hashlib.sha256(str(r.get('id',index)).encode()).hexdigest()[:16]
        chosen.append((rid,index,ids[:args.context+args.decode]))
        if len(chosen)==args.requests: break
    if len(chosen)!=args.requests: raise RuntimeError('insufficient real tokens')
    print('SELECTED_REAL_REQUESTS',len(chosen),flush=True)
    model=AutoModelForCausalLM.from_pretrained(args.model,local_files_only=True,torch_dtype=torch.bfloat16,device_map={'':0},attn_implementation='sdpa').eval()
    layers=model.config.num_hidden_layers; topk=model.config.num_experts_per_tok
    fields=['request_id','split','position','phase','token_id','layer','expert','route_prob','count']
    partial=out/'routing_trace.csv.gz.partial'; rows=0; started=time.time()
    with gzip.open(partial,'wt',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for j,(rid,index,ids) in enumerate(chosen):
            with torch.inference_mode():
                pre=model(input_ids=torch.tensor([ids[:args.context]],device='cuda'),use_cache=True,output_router_logits=False)
                cache=pre.past_key_values; del pre
                for step in range(args.decode):
                    position=args.context+step
                    result=model(input_ids=torch.tensor([[ids[position]]],device='cuda'),past_key_values=cache,use_cache=True,output_router_logits=True)
                    cache=result.past_key_values
                    if len(result.router_logits)!=layers: raise RuntimeError('router layer mismatch')
                    for layer,logits in enumerate(result.router_logits):
                        if logits.shape[-1]!=model.config.num_experts: raise RuntimeError('expert mismatch')
                        prob=torch.softmax(logits.float(),dim=-1); values,experts=prob.topk(topk,dim=-1)
                        for e,p in zip(experts.reshape(-1).tolist(),values.reshape(-1).tolist()):
                            w.writerow(dict(request_id=rid,split='profile' if j<args.profile_requests else 'eval',position=position,phase='decode_cached_teacher_forced',token_id=ids[position],layer=layer,expert=e,route_prob=p,count=1)); rows+=1
                    del result
            del cache
            print(json.dumps({'completed':j+1,'rows':rows,'seconds':time.time()-started}),flush=True)
    expected=args.requests*args.decode*layers*topk
    if rows!=expected: raise RuntimeError(f'{rows} != {expected}')
    partial.rename(out/'routing_trace.csv.gz')
    manifest={'status':'PASS','model':args.model,'context':args.context,'decode':args.decode,'requests':args.requests,'layers':layers,'experts':model.config.num_experts,'top_k':topk,'rows':rows,'decode_method':'cached incremental teacher-forced real continuation, not generated decode','dataset':args.dataset,'records':[{'request_id':r,'source_index':i,'token_sha256':hashlib.sha256(json.dumps(ids).encode()).hexdigest()} for r,i,ids in chosen]}
    manifest.update(profile_requests=args.profile_requests,eval_requests=args.requests-args.profile_requests,selection_min_tokens=args.selection_tokens,selection_policy='first eligible dataset records; shared minimum length across contexts; population bias disclosed')
    (out/'trace_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n'); print(json.dumps(manifest),flush=True)
if __name__=='__main__': main()
