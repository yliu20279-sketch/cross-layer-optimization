"""Converge actual content identities and FP16 execution contracts; no launch."""
from pathlib import Path
import csv
import hashlib
import json
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.common import digest, require
from core.readiness import preflight
from models.qwen15.projections import all_projection_plans
from core.phase_gates import source_gate


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    ev=ROOT/'evidence';contracts=ROOT/'contracts'
    complete=read(ev/'FP16_COMPLETE_METADATA.json')
    values={Path(x['path']).name:x['value'] for x in complete['records']}
    af=read(ev/'ARCHIVEFREE_METADATA.json')
    afvalues={Path(x['file']).name:x['value'] for x in af}
    manifest=afvalues['TARGET_MANIFEST_ARCHIVEFREE.json'];receipt=afvalues['ARCHIVEFREE_RECEIPT.json']
    require(len(manifest)==4659 and receipt['runtime_gptq_archive_dependencies']==0,'FP16 object closure failed')
    logical=[{k:obj[k] for k in ('name','dtype','shape','layout','bytes','payload_sha256')} for obj in manifest]
    target_id=digest(logical)
    source=values['SOURCE_IDENTITY.json']
    source_id=digest([{'file':Path(x['file']).name,'bytes':x['bytes'],'sha256':x['sha256']}
                      for x in source['files']+source['metadata']])
    require(values['COMPLETE.json']['independent_checks']==4488,'not all projections checked')
    tokenizer=next(x['sha256'] for x in source['metadata'] if Path(x['file']).name=='tokenizer.json')
    runtime=read(ev/'NATIVE_BUILD_RECEIPT.json')
    require(not complete['runtime_libraries']['unresolved'],'unresolved native candidate library')
    precision={'source_quantization':'legacy GPTQ INT4 group128', 'target_weights':'F16',
               'activation_storage':'F16','gemm_K_accumulation':'F32 increasing-K; final GEMM store F16',
               'shared_TP':'F16 rank partials; fixed-order F32 sum; final F16',
               'qkv_bias':'nonzero F16 operands retained; projection epilogue before final F16 output',
               'runtime_unpack_ops':0,'runtime_scale_zero_gidx_reads':0,
               'reference_tolerances':'old scoped rtol=atol=.002 retained; not full-model quality pass'}
    q15=read(contracts/'qwen15.json')
    q15.update(model_id='Qwen/Qwen1.5-MoE-A2.7B-Chat-GPTQ-Int4',
               display_name='Qwen1.5-MoE-A2.7B-Chat / GPTQ-decoded FP16',
               execution_representation='GPTQ-decoded-FP16',source_quantization='GPTQ_INT4',
               target_weight_dtype='F16',checkpoint_content_sha256=target_id,
               source_checkpoint_sha256=source_id,content_snapshot_id='sha256:'+target_id,
               tokenizer_sha256=tokenizer,target_manifest_sha256=receipt['target_manifest_sha256'],
               precision=precision,precision_sha256=digest(precision),revision=None,
               upstream_revision_verified=False,target_assets_verified=True,
               runtime_gptq_archive_dependencies=0,host_weights_reserved_bytes=None,
               blocker_notes=['original BF16 asset requirement removed by explicit user instruction',
                              'full target model forward and native composite validation not run'])
    q15['runtime']={'binary':{'path':runtime['native_binary'],'sha256':runtime['native_sha256']},
                    'libraries':complete['runtime_libraries']['libraries'],
                    'source_build_identity_sha256':digest(runtime),
                    'scope':'compiled FP16 tiled substrate + accept/callback hook; not complete composite',
                    'candidate_executed_as_model':False}
    q15['spec'].update(id=q15['model_id'],target_representation='GPTQ-decoded-FP16',weight_dtype='F16')
    if 'actual_bf16_memory_io' in q15['capabilities']:
        q15['capabilities']['actual_fp16_memory_io'] = q15['capabilities'].pop('actual_bf16_memory_io')
    target_objects={obj['name']:dict(obj,checkpoint_sha256=target_id) for obj in manifest}
    save(contracts/'qwen15_tensor_inventory.json',{'objects':target_objects,'content_snapshot_sha256':target_id,
         'target_manifest_sha256':receipt['target_manifest_sha256'],'logical_valid_bytes':receipt['target_valid_bytes'],
         'source_quantized_format_is_archival':True,'runtime_gptq_archive_dependencies':0})
    # Deterministic finite host backing. This does not certify an HB schedule,
    # KV, activation or all-SRAM peak; those remain separately blocked.
    cursor=0;backing=[]
    for obj in manifest:
        cursor=(cursor+4095)//4096*4096
        reserved=(obj['bytes']+4095)//4096*4096
        backing.append({'name':obj['name'],'host_address':cursor,'valid_bytes':obj['bytes'],
                        'reserved_bytes':reserved,'dtype':'F16','payload_sha256':obj['payload_sha256']})
        cursor+=reserved
    require(cursor<=128*1024**3,'host weight backing over capacity')
    q15['host_weights_reserved_bytes']=cursor
    save(contracts/'qwen15_host_backing.json',{'host_bytes':128*1024**3,'weight_reserved_bytes':cursor,
         'objects':backing,'weight_backing_verified':True,'hb_lifetimes_verified':False,
         'KV_activation_SRAM_peaks_verified':False,'no_infinite_host_backing':True})
    save(contracts/'qwen15.json',q15)
    save(contracts/'qwen15_projection_bindings.json',all_projection_plans(manifest))
    q3=read(contracts/'qwen3.json')
    q3comp=read(ev/'Q3_RUNTIME_COMPONENTS.json')
    require(all(x.get('match') for x in q3comp['records']),'Q3 candidate changed')
    byname={Path(x['path']).name:x for x in q3comp['records']}
    q3['runtime']={'binary':{k:byname['host'][k] for k in ('path','sha256')},
                   'libraries':[{k:byname['libfull.so'][k] for k in ('path','sha256')}],
                   'source_build_identity_sha256':digest(q3comp),
                   'required_components':[{k:x[k] for k in ('path','sha256')} for x in q3comp['records']],
                   'scope':'existing BF16 host/gateway/primitive-service candidate, not new composite execution',
                   'candidate_executed_here':False}
    q3['blocker_notes']=['content snapshot fixed; upstream revision remains unverified',
                         'native causal scheduler/collectives integration and full costs remain pending']
    save(contracts/'qwen3.json',q3)
    original=contracts/'original_model_search.json'
    if original.exists():
        shutil.copyfile(original,ev/'PREVIOUS_ORIGINAL_MODEL_SEARCH.json');original.unlink()
    save(contracts/'assets.json',{'user_amendment':'Q15 existing Chat-GPTQ decoded to FP16; Q3 remains BF16',
         'qwen15_target_assets_verified':True,'qwen15_source_snapshot_sha256':source_id,
         'qwen15_target_snapshot_sha256':target_id,'qwen15_runtime_dtype':'F16',
         'original_bf16_search_no_longer_a_blocker':True,'qwen3_runtime_dtype':'BF16',
         'models_share_no_precision_assumption':True})
    save(contracts/'runtime.json',{'models':{'qwen3':q3['runtime'],'qwen15':q15['runtime']},
         'native_composite_not_validated':True,'costs_unverified':True,'p0_2_started':False})
    phases={};coverage=[]
    filemap={'Q3-01':'models/qwen3/sem_moe.py','Q3-02':'models/qwen3/build_graph.py',
             'Q3-03':'core/collectives.py','Q3-04':'core/artifacts.py','Q3-05':'models/qwen3/run_contract.py',
             'Q3-06':'runner.py','Q15-01':'models/qwen15/sem_moe.py','Q15-02':'core/scheduling.py',
             'Q15-03':'models/qwen15/build_graph.py','Q15-04':'core/artifacts.py',
             'Q15-05':'models/qwen15/capture_contract.py','Q15-06':'models/qwen15/run_contract.py',
             'Q15-07':'validation/test_contracts.py','C-01':'runtime/native_main_fp16_hook.cc',
             'C-02':'core/memory.py','C-03':'core/runtime.py','C-04':'core/runtime.py',
             'C-05':'runtime/p0_event_sink.h','C-06':'runner.py','C-07':'core/reuse.py'}
    partial={'Q3-02','Q3-03','Q3-04','Q15-03','C-01','C-04','C-05'}
    for name,path in filemap.items():
        p=ROOT/path
        coverage.append({'id':name,'path':str(p),'relative_path':path,
                         'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                         'implementation':'partial_native_binding' if name in partial else 'implemented',
                         'scope':'software/reference or compiled hook only; see implementation ledger'})
    for name,contract in [('qwen3',q3),('qwen15',q15)]:
        model='Q3' if name=='qwen3' else 'Q15'
        phases[name]={'source':source_gate(contract,[x for x in coverage if x['id'].startswith((model,'C-'))]),
                      'performance':preflight(contract)}
    save(contracts/'implementation_coverage.json',coverage)
    save(contracts/'gates.json',phases)
    with (ROOT/'IMPLEMENTATION_STATUS.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=['id','relative_path','implementation','sha256','scope'])
        writer.writeheader();writer.writerows({k:x[k] for k in writer.fieldnames} for x in coverage)
    save(ev/'REUSE_DECISIONS_v3.json',{'scope':'updated for authorized Q15 decoded FP16',
         'layer0_reused_projection_payloads':183,'reuse_payload_checks':'bitwise source-decoded vs old materialized',
         'old_q15_four_numerics':'retain isolated layer0 target-FP16 tolerance scope only',
         'old_joint_native':'substrate/identity reference only, not new Sem-MoE+HiBand cycle reuse',
         'old_125_w4_proxy_cycles':'historical only; no new FP16 cycle promotion',
         'qwen3_old_fp16':'not substituted for retained BF16 contract',
         'new_source_gptq_trace':'must be revalidated against target execution before free-running inference claims',
         'cycles_promoted_to_new_composite':0})
    print(json.dumps({'target_snapshot':target_id,'source_snapshot':source_id,'target_bytes':receipt['target_valid_bytes'],
                      'host_reserved':cursor,'projection_bindings':len(read(contracts/'qwen15_projection_bindings.json')),
                      'performance_ready':False},ensure_ascii=False))


if __name__=='__main__':main()
