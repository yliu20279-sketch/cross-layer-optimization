"""Original BF16 single-GPU functional baseline with official mini agent.
No NPU simulation, training, remote API, quantization or shared-source edits.
"""
import ast
import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import textwrap
import time
import types

ROOT=Path(__file__).resolve().parent
MODEL=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B')
MINI=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/source/mini-swe-agent')
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',MSWEA_SILENT_STARTUP='1',
                  MSWEA_GLOBAL_CONFIG_DIR=str(ROOT/'mini_global_config'))
import sys
sys.path.insert(0,str(MINI/'src'))
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
import transformers
import transformers.models.qwen3_moe.modeling_qwen3_moe as qwen_module
from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.docker import DockerEnvironment
from minisweagent.models.utils.actions_text import parse_regex_actions,format_observation_messages
import yaml

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def command(cmd,cwd=None,timeout=60):
    p=subprocess.run(cmd,cwd=cwd,capture_output=True,text=True,timeout=timeout)
    return dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)


class Backend:
    def __init__(self):
        self.requests=[];self.current=None;self.capture=False;self.call_number=0
        torch.set_num_threads(4);torch.manual_seed(20261026)
        free=int(subprocess.check_output(['nvidia-smi','-i','0','--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True).strip())
        if free<72*1024:raise RuntimeError('GPU0 resource gate failed, not preempting')
        torch.backends.cuda.matmul.allow_tf32=False
        torch.backends.cuda.matmul.allow_bf16_reduced_precision_reduction=False
        self.tokenizer=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
        started=time.monotonic()
        self.model=AutoModelForCausalLM.from_pretrained(MODEL,local_files_only=True,
            torch_dtype=torch.bfloat16,device_map={'':0},attn_implementation='eager',low_cpu_mem_usage=True).eval()
        load_seconds=time.monotonic()-started
        counts={}
        for _,p in self.model.named_parameters():counts[str(p.dtype)]=counts.get(str(p.dtype),0)+p.numel()
        assert counts=={'torch.bfloat16':30532122624},counts
        index=json.loads((MODEL/'model.safetensors.index.json').read_text())['weight_map']
        verified=json.loads((MODEL.parent.parent/'MODEL_VERIFICATION.json').read_text())
        file_hashes={x['path']:x['sha256'] for x in verified}
        save(ROOT/'FIXTURE_WEIGHT_BINDINGS.json',dict(model_revision='ad44e777bcd18fa416d9da3bd8f70d33ebb85d39',
            index_sha256=sha(MODEL/'model.safetensors.index.json'),config_sha256=sha(MODEL/'config.json'),
            layer0_weights={name:dict(shard=shard,verified_shard_sha256=file_hashes[shard]) for name,shard in index.items() if name.startswith('model.layers.0.')},
            copied_weights=False,scope='read corresponding same-checkpoint weights by key for future fixture validation'))
        model_source=Path(inspect.getsourcefile(qwen_module))
        if sha(model_source)!='3af43d01f9f902c8009b6dd7d7b8b563561b53dd0aa54175f585ae90d049fdb8':
            raise RuntimeError('Installed model source differs from frozen source')
        save(ROOT/'GPU_BACKEND_BINDING.json',dict(torch=torch.__version__,transformers=transformers.__version__,
            model=str(MODEL),model_revision='ad44e777bcd18fa416d9da3bd8f70d33ebb85d39',model_source=str(model_source),model_source_sha256=sha(model_source),
            parameter_dtypes=counts,attention='eager',thinking=False,decoding='per-request policy; see REQUEST.json',load_seconds=load_seconds,
            CUDA_VISIBLE_DEVICES=os.environ.get('CUDA_VISIBLE_DEVICES'),allow_tf32=False,allow_bf16_reduced_precision_reduction=False,
            GPU=torch.cuda.get_device_name(0),max_memory_allocated=torch.cuda.max_memory_allocated(),
            scope='GPU BF16 functional backend; not target architecture timing'))
        self.model.register_forward_pre_hook(self._start_forward,with_kwargs=True)
        self.model.register_forward_hook(self._end_forward,with_kwargs=True)
        layer=self.model.model.layers[0]
        layer.register_forward_pre_hook(self._layer_input,with_kwargs=True)
        layer.register_forward_hook(self._layer_output,with_kwargs=True)
        layer.self_attn.register_forward_hook(self._attention_output,with_kwargs=True)

    def _start_forward(self,module,args,kwargs):
        if self.current is None:return
        ids=kwargs.get('input_ids',args[0] if args else None)
        cache=kwargs.get('past_key_values');past=cache.get_seq_length() if cache is not None else 0
        rec=dict(index=len(self.current['forwards']),phase='prefill' if past<self.current['prompt_tokens'] else 'decode',past_tokens=int(past),input_tokens=int(ids.shape[-1]))
        if self.capture:rec['input_token_ids']=ids.detach().cpu().tolist()
        begin=torch.cuda.Event(enable_timing=True);end=torch.cuda.Event(enable_timing=True);begin.record()
        rec['_events']=(begin,end);self.current['forwards'].append(rec);self.forward=rec

    def _end_forward(self,module,args,kwargs,result):
        if self.current is not None:self.forward['_events'][1].record()

    def _fixture(self):
        if not self.capture or self.current is None:return None
        rec=self.forward
        # Keep only first prefill and first decode of each real request.
        if rec['phase']=='decode':
            key='decode'
            existing=self.current['fixtures'].get(key)
            if existing and existing['forward']['index']!=rec['index']:return None
            return self.current['fixtures'].setdefault(key,{'forward':{k:v for k,v in rec.items() if not k.startswith('_')}})
        chunks=self.current['fixtures'].setdefault('prefill_chunks',{})
        return chunks.setdefault(str(rec['index']),{'forward':{k:v for k,v in rec.items() if not k.startswith('_')}})

    def _layer_input(self,module,args,kwargs):
        f=self._fixture()
        if f is not None:
            x=args[0] if args else kwargs['hidden_states'];f['decoder_input']=x.detach().cpu()
            position=kwargs.get('position_embeddings')
            if position is not None:f['cos'],f['sin']=[t.detach().cpu() for t in position]
            if self.forward['phase']=='decode':
                cache=kwargs.get('past_key_value')
                if cache is not None and len(cache.key_cache)>0:
                    f['layer0_key_cache_before']=cache.key_cache[0].detach().cpu()
                    f['layer0_value_cache_before']=cache.value_cache[0].detach().cpu()

    def _layer_output(self,module,args,kwargs,result):
        f=self._fixture()
        if f is not None:f['decoder_output']=result[0].detach().cpu()

    def _attention_output(self,module,args,kwargs,result):
        f=self._fixture()
        if f is not None:f['attention_output']=result[0].detach().cpu()

    def probabilities(self,module,logits,probabilities):
        if self.capture and module._swe_layer==0:
            f=self._fixture()
            if f is not None:
                f['router_logits']=logits.detach().cpu();f['router_probabilities_fp32']=probabilities.detach().cpu()

    def routes(self,module,hidden,ids,weights):
        if not self.capture:return
        rec=self.forward
        self.current['routes'].append(dict(layer=module._swe_layer,forward=rec['index'],phase=rec['phase'],
            selected_experts=ids.detach().to('cpu',dtype=torch.int16),final_weights=weights.detach().cpu()))
        if module._swe_layer==0:
            f=self._fixture()
            if f is not None:
                f['moe_input']=hidden.detach().cpu();f['actual_selected_experts']=ids.detach().cpu();f['actual_final_weights']=weights.detach().cpu()

    def instrument(self):
        original=qwen_module.Qwen3MoeSparseMoeBlock.forward
        tree=ast.parse(textwrap.dedent(inspect.getsource(original)));fn=tree.body[0];fn.decorator_list=[]
        body=[];injections=0
        for node in fn.body:
            body.append(node)
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='routing_weights' for t in node.targets):
                if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute):
                    if node.value.func.attr=='softmax':
                        body+=ast.parse('_capture_probabilities(self, router_logits, routing_weights)').body;injections+=1
                    if node.value.func.attr=='to':
                        body+=ast.parse('_capture_routes(self, hidden_states, selected_experts, routing_weights)').body;injections+=1
        if injections!=2:raise RuntimeError('Source instrumentation point mismatch')
        fn.body=body
        module_ast=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),fn],type_ignores=[])
        ast.fix_missing_locations(module_ast)
        env=dict(original.__globals__);env.update(_capture_probabilities=self.probabilities,_capture_routes=self.routes)
        exec(compile(module_ast,'<swe_capture_actual_dispatch>','exec'),env)
        wrapped=env['forward']
        for i,layer in enumerate(self.model.model.layers):
            layer.mlp._swe_layer=i;layer.mlp.forward=types.MethodType(wrapped,layer.mlp)
        save(ROOT/'INSTRUMENTATION.json',dict(source_forward_sha256=hashlib.sha256(inspect.getsource(original).encode()).hexdigest(),
            method='AST inserts two observers into unchanged source forward body, after actual softmax and actual final BF16 weights',
            observer_AST_sha256=hashlib.sha256(ast.dump(module_ast,include_attributes=False).encode()).hexdigest(),
            no_TopK_recomputation=True,full_layers=48,source_file_modified=False))

    def generate(self,messages,task,limit=512,capture=True):
        self.call_number+=1;rid=f'R{self.call_number:04d}';directory=ROOT/'requests'/rid;directory.mkdir(parents=True,exist_ok=False)
        clean=[{'role':m['role'],'content':m['content']} for m in messages]
        ids=self.tokenizer.apply_chat_template(clean,tokenize=True,add_generation_prompt=True,enable_thinking=False,return_tensors='pt')
        if ids.shape[-1]+limit>32768:raise RuntimeError('CONTEXT_LIMIT_NO_TRUNCATION')
        record=dict(request_id=rid,task_id=task,prompt_token_ids=ids.tolist(),prompt_tokens=int(ids.shape[-1]),forwards=[],routes=[],fixtures={},capture=capture)
        self.current=record;self.capture=capture
        save(directory/'messages.json',clean)
        inputs=ids.to('cuda:0');torch.cuda.synchronize();torch.cuda.reset_peak_memory_stats();start=time.monotonic()
        policy=getattr(self,'decoding',dict(do_sample=True,temperature=0.7,top_p=0.8,top_k=20))
        request_seed=20261026+self.call_number
        torch.manual_seed(request_seed)
        with torch.inference_mode():
            chunk_size=getattr(self,'prefill_chunk_size',256)
            cache=None
            if chunk_size and inputs.shape[-1]>chunk_size:
                for begin in range(0,inputs.shape[-1]-1,chunk_size):
                    end=min(begin+chunk_size,inputs.shape[-1]-1)
                    output=self.model(input_ids=inputs[:,begin:end],attention_mask=torch.ones((1,end),dtype=torch.long,device=inputs.device),
                        past_key_values=cache,use_cache=True,logits_to_keep=1,return_dict=True)
                    cache=output.past_key_values
                    del output
            generated=self.model.generate(input_ids=inputs,attention_mask=torch.ones_like(inputs),max_new_tokens=limit,
                past_key_values=cache,use_cache=True,logits_to_keep=1,pad_token_id=self.tokenizer.eos_token_id,
                **policy,output_router_logits=False)
        torch.cuda.synchronize();wall=time.monotonic()-start
        new=generated[0,ids.shape[-1]:].detach().cpu().tolist();text=self.tokenizer.decode(new,skip_special_tokens=True)
        for forward in record['forwards']:
            begin,end=forward.pop('_events');forward['CUDA_event_ms']=begin.elapsed_time(end)
        routes=record.pop('routes');fixtures=record.pop('fixtures')
        if capture:
            expected=48*len(record['forwards'])
            if len(routes)!=expected:raise RuntimeError(f'Incomplete routing {len(routes)} vs {expected}')
            for route in routes:
                if route['selected_experts'].shape[-1]!=8 or route['final_weights'].dtype!=torch.bfloat16:raise RuntimeError('Route shape/dtype mismatch')
                if int(route['selected_experts'].min())<0 or int(route['selected_experts'].max())>=128:raise RuntimeError('Expert range')
            torch.save(routes,directory/'actual_routes.pt');torch.save(fixtures,directory/'layer0_actual_fixtures.pt')
        record.update(new_token_ids=new,new_tokens=len(new),text=text,generation_wall_seconds=wall,decoding=policy,request_seed=request_seed,prefill_chunk_size=chunk_size,fixture_schema='prefill_chunks plus first decode with layer0 KV before',peak_allocated_bytes=torch.cuda.max_memory_allocated(),peak_reserved_bytes=torch.cuda.max_memory_reserved(),
            prefill_CUDA_ms=sum(f['CUDA_event_ms'] for f in record['forwards'] if f['phase']=='prefill'),
            decode_CUDA_ms=sum(f['CUDA_event_ms'] for f in record['forwards'] if f['phase']=='decode'),
            eos=bool(new and new[-1]==self.tokenizer.eos_token_id),max_new_tokens=limit,route_records=len(routes),
            scope='GPU instrumented functional time; no NPU cycle interpretation')
        save(directory/'REQUEST.json',record)
        save(directory/'MANIFEST.json',[dict(path=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(directory.iterdir()) if p.is_file()])
        self.requests.append(record);self.current=None;print('REQUEST',rid,task,record['prompt_tokens'],len(new),round(wall,3),flush=True)
        return record


class LocalModel:
    def __init__(self,backend,task,max_tokens):self.backend=backend;self.task=task;self.max_tokens=max_tokens;self.config=types.SimpleNamespace(model_name='local/Qwen3-30B-A3B-BF16')
    def query(self,messages,**kwargs):
        r=self.backend.generate(messages,self.task,self.max_tokens,True)
        actions=parse_regex_actions(r['text'],action_regex=r'```bash\s*\n(.*?)\n```',
            format_error_template='Please provide exactly ONE fenced bash block: ```bash followed by a newline, one shell command, newline and ```. {{error}}')
        return dict(role='assistant',content=r['text'],extra=dict(actions=actions,cost=0,local_request_id=r['request_id'],
            usage=dict(prompt_tokens=r['prompt_tokens'],completion_tokens=r['new_tokens'])))
    def format_message(self,**kwargs):return kwargs
    def format_observation_messages(self,message,outputs,template_vars=None):
        return format_observation_messages(outputs,observation_template='{% if output.exception_info %}<exception>{{output.exception_info}}</exception>\n{% endif %}<returncode>{{output.returncode}}</returncode>\n<output>{{output.output}}</output>',template_vars=template_vars)
    def get_template_vars(self,**kwargs):return dict(model_name=self.config.model_name,**kwargs)
    def serialize(self):return {'info':{'config':{'model':{'model_name':self.config.model_name,'backend':'local Transformers BF16','max_new_tokens':self.max_tokens}}}}


class LoggedDocker(DockerEnvironment):
    def __init__(self,log,**kwargs):self.log=Path(log);self.records=[];super().__init__(**kwargs)
    def execute(self,action,cwd='',**kwargs):
        start=time.monotonic();entry=dict(command=action.get('command',''),start_utc=time.time(),start_monotonic=start)
        try:
            result=super().execute(action,cwd,**kwargs);entry.update(result=result);return result
        except Exception as exc:
            entry['exception']=type(exc).__name__;raise
        finally:
            entry.update(done_monotonic=time.monotonic(),seconds=time.monotonic()-start);self.records.append(entry);save(self.log,self.records)


def tiny(backend):
    p=ROOT/'tiny_repository';p.mkdir(exist_ok=False)
    (p/'mean.py').write_text('def mean(values):\n    return sum(values) / len(values)\n')
    tests='''import unittest\nfrom mean import mean\nclass MeanTests(unittest.TestCase):\n    def test_empty(self): self.assertIsNone(mean([]))\n    def test_values(self): self.assertEqual(mean([2,4,6]),4)\nif __name__ == "__main__": unittest.main()\n'''
    (p/'test_mean.py').write_text(tests);test_hash=sha(p/'test_mean.py')
    for cmd in [['git','init'],['git','config','user.email','swe-local@example.invalid'],['git','config','user.name','swe-local'],['git','add','.'],['git','commit','-m','tiny compatibility fixture']]:
        result=command(cmd,p);assert result['returncode']==0,result
    image='codex-aligned-build:20260827-slim'
    image_id=subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip()
    environment=LoggedDocker(ROOT/'TINY_TOOL_EVENTS.json',image=image,cwd='/work',timeout=120,
        run_args=['--label','swe_qwen3_step3=1','--network','none','--cpus','2','--memory','2g','--pids-limit','512','-v',str(p)+':/work','-v',str(p/'test_mean.py')+':/work/test_mean.py:ro'],container_timeout='25m')
    baseline=environment.execute({'command':'python3 -m unittest -v'})
    config=yaml.safe_load((MINI/'src/minisweagent/config/default.yaml').read_text())['agent']
    config.update(**revised_prompt())
    config.update(step_limit=16,cost_limit=0,wall_time_limit_seconds=1200,max_consecutive_format_errors=3,output_path=ROOT/'TINY_TRAJECTORY.json')
    agent=DefaultAgent(LocalModel(backend,'tiny_mean_compatibility',512),environment,**config)
    started=time.monotonic()
    try:
        result=agent.run('Fix this repository bug: mean([]) raises ZeroDivisionError, but the empty-input result must be None. Preserve ordinary nonempty means. Inspect the files and run regression tests before submitting. Do not modify tests. Python3 is available; git is not installed inside this container. Work in /work.')
        final=environment.execute({'command':'python3 -m unittest -v'})
        integrity=sha(p/'test_mean.py')==test_hash
        diff=command(['git','diff','--binary'],p);(ROOT/'TINY_PATCH.diff').write_text(diff['stdout'])
        report=dict(state='PASS_TINY_AUTONOMOUS_LOOP' if result.get('exit_status')=='Submitted' and final['returncode']==0 and integrity and bool(diff['stdout']) else 'FAIL_TINY_GATE',
            agent_result=result,baseline=baseline,final_test=final,test_file_unchanged=integrity,
            wall_seconds=time.monotonic()-started,tool_calls=len(environment.records),image=image,image_id=image_id,
            container_id=environment.container_id,scope='synthetic compatibility fixture, not SWE-bench task',
            official_mini_agent_commit='04d809ceab9df28f9adaed044884180159172930')
        save(ROOT/'TINY_RESULT.json',report);return report
    finally:
        if environment.container_id:
            command(['docker','stop','--time','2',environment.container_id],timeout=15)
            environment.container_id=None # preserve stopped container and logs, do not auto-remove


def main():
    save(ROOT/'GPU_RUN_STATUS.json',{'state':'STARTING','scope':'step3 BF16 GPU functional baseline'})
    try:
        backend=Backend();messages=[dict(role='user',content='Reply with exactly the word READY.')]
        before=backend.generate(messages,'short_generation_capture_off',32,False)
        backend.instrument();after=backend.generate(messages,'short_generation_capture_on',32,True)
        identical=before['new_token_ids']==after['new_token_ids']
        save(ROOT/'SHORT_GENERATION.json',dict(state='PASS' if identical and after['new_tokens']>0 else 'FAIL',
            output_tokens_identical=identical,capture_off_request=before['request_id'],capture_on_request=after['request_id'],
            capture_off_seconds=before['generation_wall_seconds'],capture_on_seconds=after['generation_wall_seconds'],
            perturbation_scope='one paired short prompt, no statistical overhead claim',response=after['text']))
        if not identical:raise RuntimeError('Instrumentation changed short-generation tokens')
        report=tiny(backend)
        save(ROOT/'GPU_RUN_STATUS.json',{'state':report['state'],'requests':len(backend.requests),
            'scope':'GPU short generation and tiny compatibility only; development SWE tasks separate',
            'model_dtype':'BF16','NPU_simulation_runs':0})
    except Exception as exc:
        import traceback
        save(ROOT/'GPU_RUN_STATUS.json',dict(state='FAILED_RETAINED',error=repr(exc),traceback=traceback.format_exc()))
        traceback.print_exc();raise

if __name__=='__main__':main()
