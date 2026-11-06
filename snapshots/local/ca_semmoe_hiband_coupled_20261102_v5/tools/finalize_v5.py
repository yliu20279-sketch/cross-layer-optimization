"""Locally bind compact evidence and source; do not infer performance PASS."""
from pathlib import Path
import csv
import hashlib
import json
import sys
import tarfile
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.common import require,file_hash,digest
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p,obj):Path(p).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
review=ROOT/'remote_review';ev=ROOT/'evidence';ct=ROOT/'contracts'
build=read(review/'evidence/COUPLED_BUILD_04.json');runtime=read(review/'evidence/RUNTIME_IDENTITY_V5.json')
require(build['sha256']==runtime['binary_sha256'],'candidate runtime changed')
for name,expected in build['source_sha256'].items():require(file_hash(ROOT/'runtime'/name)==expected,'compiled source differs: '+name)
software=read(review/'evidence/SOFTWARE_CHECKS_v4.json')
require(software['tests']==32 and software['errors']==software['failures']==software['skipped']==0,'remote software checks incomplete')
bindings=[];metrics={}
for model in ('qwen3','qwen15'):
    final=review/'runs'/(model+'_layer02');initial=review/'runs'/(model+'_layer01')
    protocol=read(final/'PROTOCOL.json');result=read(final/'RESULT.json');audit=read(final/'INDEPENDENT_RAW_AUDIT.json')
    comparison=read(final/'independent_cpu_reference/COMPARISON.json')
    require(read(final/'backend/LAUNCH.json')['binary_sha256']==build['sha256'],'wrong full-layer binary')
    for rel,expected in protocol['code_sha256'].items():
        require(file_hash(ROOT/rel)==expected,'full-layer Python source differs: '+rel)
        bindings.append({'model':model,'path':rel,'sha256':expected})
    require(audit['migration_write_bytes']==audit['migration_read_bytes']==8192,'page migration was not audited')
    require(audit['transactions']==result['summary']['callbacks'],'raw callbacks differ')
    refstats=[]
    for phase in ('prefill','decode'):
        require((initial/(phase+'_input.bin')).read_bytes()==(final/(phase+'_input.bin')).read_bytes(),'diagnostic inputs changed between fixes')
        a=np.frombuffer((final/(phase+'_output.bin')).read_bytes(),dtype='<u2')
        b=np.frombuffer((final/'independent_cpu_reference'/(phase+'_output.bin')).read_bytes(),dtype='<u2')
        af=(a.astype('<u4')<<16).view('<f4') if model=='qwen3' else a.view('<f2').astype('<f4')
        bf=(b.astype('<u4')<<16).view('<f4') if model=='qwen3' else b.view('<f2').astype('<f4')
        stat=next(p for p in comparison['phases'] if p['phase']==phase)
        count=int((a!=b).sum());maximum=float(np.max(np.abs(af-bf)))
        require(count==stat['different_storage_bits'] and maximum==stat['maxabs'],'reference metrics do not reproduce locally')
        refstats.append({'phase':phase,'elements':len(a),'different_elements':count,'maxabs':maximum,
                         'selected_set_equal':stat['selected_set_equal']})
    metrics[model]={'TP':result['TP'],'EP':result['EP'],'transactions':audit['transactions'],'packets':audit['packets'],
        'allocations':audit['allocations'],'releases':audit['releases'],'KV_prefix_payloads':audit['KV_prefix_payloads_checked'],
        'primitive_jobs':audit['primitive_jobs'],'HB_peak_reserved_bytes':max(audit['HB_peak_reserved']),
        'reference':refstats,'raw_event_sha256':audit['raw_event_sha256'],'raw_event_bytes':audit['raw_event_bytes']}
    inherited=ct/(model+'_inherited_v4.json')
    if not inherited.exists():save(inherited,read(ct/(model+'.json')))
    contract=read(ct/(model+'.json'))
    contract['runtime']={'binary':{'path':build['binary'],'sha256':build['sha256']},'libraries':runtime['libraries'],
        'source_build_identity_sha256':digest(build),'scope':'serial diagnostic live-layer candidate, not parallel SOTA/performance admission'}
    contract['target_weight_dtype']='BF16' if model=='qwen3' else 'F16'
    contract['precision']['v5_candidate']={'norm_topk_prob':model=='qwen3','expert_accumulation':'ascending expert id',
        'matrix':'preserved BF16 FDA64' if model=='qwen3' else 'increasing-K FP32 dot partials of64, increasing-K partial sum',
        'attention_O_partials':'F32 then F32 SRS and BF16' if model=='qwen3' else 'F16 then F32 SRS and F16',
        'host_special_functions':'explicit NumPy/microprogram services; CPU/PCIe time unverified',
        'original_model_bit_exact_verified':False}
    contract['precision_sha256']=digest(contract['precision'])
    contract['p0_1b_status']='PARTIAL_WITH_LIVE_LAYER_AND_PHYSICAL_MAPPING'
    contract['formal_performance_started']=False
    contract['blocker_notes']=['driver is serial, not native concurrent Sem-MoE scheduling',
        'CPU/PCIe/cache-control costs incomplete; raw architecture transaction256 not unified with existing32-byte candidate',
        'single layer / one active request / two diagnostic phases only; not complete PP4 model or natural workload',
        'official CPU comparison has residual differences; no numerical/performance promotion']
    contract['v5_evidence_metrics']=metrics[model]
    save(ct/(model+'.json'),contract)
physical=read(review/'evidence/PHYSICAL_PERMUTATION_PROBE.json')
require(physical['output_bitwise_equal'] and physical['moved_valid_bytes']==8192,'physical numerical invariance absent')
p=review/'physical_permutation_probe01'
require((p/'output_before.f16').read_bytes()==(p/'output_after.f16').read_bytes(),'physical probe outputs differ locally')
negative=read(review/'evidence/PHYSICAL_PERMUTATION_NEGATIVES.json')
require(len(negative['cases'])==4 and all(c['rejected'] for c in negative['cases']),'negative mapping controls incomplete')
save(ev/'SOURCE_AND_LOCAL_REVIEW_V5.json',{'source_bindings':bindings,'compiled_source_set_matches':True,
    'independent_reference_metrics_recomputed':True,'fixed_diagnostic_inputs_preserved':True,
    'physical_projection_outputs_bitwise_equal':True,'large_raw_logs_recomputed_locally':False})
coverage=read(ct/'implementation_coverage.json')
newpaths={'Q3-02':'core/coupled_layer.py','Q3-03':'core/coupled_layer.py','Q3-04':'core/coupled_backend.py',
    'Q3-06':'tools/run_coupled_layer.py','Q15-03':'core/coupled_decoder.py','C-01':'runtime/coupled_backend.cpp',
    'C-02':'runtime/coupled_backend.cpp','C-03':'runtime/coupled_backend.cpp','C-04':'core/coupled_backend.py',
    'C-05':'runtime/coupled_backend.cpp','C-06':'tools/run_coupled_layer.py'}
partial={'Q3-02','Q3-03','Q3-04','Q15-03','C-01','C-02','C-03','C-04','C-05'}
for row in coverage:
    path=newpaths.get(row['id'],row['relative_path']);row.update(relative_path=path,path=str(ROOT/path),sha256=file_hash(ROOT/path))
    row['implementation']='implemented_limited_coupled' if row['id'] in partial else 'implemented'
    row['scope']='see REPORT: limited dataflow/mapping execution; concurrent scheduling/full costs/full model not admitted'
save(ct/'implementation_coverage.json',coverage)
with (ROOT/'IMPLEMENTATION_STATUS_v5.csv').open('w',newline='',encoding='utf-8-sig') as f:
    fields=['id','relative_path','implementation','sha256','scope'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    w.writerows({k:r[k] for k in fields} for r in coverage)
gates={model:{'p0_1b_complete':False,'parallel_schedule_verified':False,'CPU_PCIe_and_cache_costs_verified':False,
    'whole_model_or_PP4_verified':False,'original_model_numerics_verified':False,'performance_ready':False,
    'live_layer_payload_and_callback_scoped_check':True,'physical_page_migration_scoped_check':True,
    'formal_performance_started':False} for model in ('qwen3','qwen15')}
save(ct/'gates.json',gates)
save(ct/'runtime.json',{'models':{model:read(ct/(model+'.json'))['runtime'] for model in ('qwen3','qwen15')},
    'serial_diagnostic_driver':True,'native_concurrent_schedule_verified':False,
    'CPU_PCIe_cache_costs_verified':False,'formal_performance_started':False})
status={'status':'PARTIAL_P0_1B_LIVE_LAYER_AND_PHYSICAL_MAPPING_SCOPED',
    'directory_started':'2026-11-02','review_updated':'2026-11-03 Asia/Shanghai',
    'models':metrics,'remote_software_tests':32,'mapping_negative_controls':4,
    'p0_1c_previous_dispositions_retained':True,'old_cycles_promoted':0,
    'formal_performance_runs':0,'complete_model_forwards':0,'GPU_runs':0,'physical_NPU_runs':0,
    'full_layer_diagnostic_contexts':4,'independent_CPU_reference_layer_calls':8,
    'p0_1b_complete':False,'performance_ready':False,
    'remaining':['native concurrent TP/EP and multi-request scheduling',
                 'target CPU/PCIe/cache-maintenance costs and common timing/transaction contract',
                 'full PP4 decoder execution, broader numerical correctness and general paging/lifetime coverage',
                 'trained CA layout and matched identity/B+CA numerical admission; no natural performance claims'],
    'scope':'one layer, prefill1/cached decode1; final runs include fixed diagnostic page swap, not learned CA'}
save(ROOT/'STATUS.json',status)
print(json.dumps({'status':status['status'],'models':metrics,'formal_performance_runs':0},ensure_ascii=False))
