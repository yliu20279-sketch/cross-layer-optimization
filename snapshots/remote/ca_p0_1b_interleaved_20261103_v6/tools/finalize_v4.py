"""Bind final evidence to exact source bytes; preserve partial target status."""
from pathlib import Path
import csv
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.common import file_hash,require,digest
from core.phase_gates import source_gate
from models.qwen15.projections import all_projection_plans

def load(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
ev=ROOT/'evidence';ct=ROOT/'contracts'
build=load(ev/'REMOTE_BUILD_LIVE_02.json');numeric=load(ev/'REMOTE_PAYLOAD_AUDIT_v2.json')
software=load(ev/'REMOTE_SOFTWARE_CHECKS_v4.json');control=load(ev/'REAL_CONTROL_PROBE_02.json')
reuse=load(ev/'REUSE_DISPOSITIONS.json')
require(software['tests']==28 and not software['failures'] and not software['errors'] and not software['skipped'],
        'final remote checks incomplete')
require(control['binary_sha256']==build['binary_sha256'],'real-backend probe binary differs')
require(numeric['native_library_sha256']==build['payload_sha256'],'CPU payload library differs')
for path,expected in numeric['sources'].items():require(file_hash(ROOT/path)==expected,'payload source changed: '+path)
for name,expected in build['sources'].items():require(file_hash(ROOT/'runtime'/name)==expected,'compiled source changed: '+name)
require(reuse['matched_cycle_cases']==0 and reuse['q3_seven_reconstructed']==7 and reuse['q15_main_cases']==100,
        'reuse disposition inconsistent')
manifest=load(ct/'qwen15_tensor_inventory.json')
save(ct/'qwen15_projection_bindings.json',all_projection_plans(list(manifest['objects'].values())))
for name in ('qwen3','qwen15'):
    c=load(ct/(name+'.json'))
    c['p0_1b_status']='PARTIAL'
    c['p0_1c_status']='COMPLETE_IDENTITY_GATED_DISPOSITIONS_ONLY'
    c['tested_candidates']={
        'cpu_payload':{'binary':build['payload_library'],'sha256':build['payload_sha256'],
                       'scope':'normalized-input MoE CPU function, not original model numerical certification or target timing'},
        'memory_network_controls':{'binary':build['binary'],'sha256':build['binary_sha256'],
                                   'scope':'three-transaction real backend probe; analytical compute; not full layer'},
    }
    c['full_layer_payload_timing_coupling_verified']=False
    c['formal_performance_started']=False
    if name=='qwen3':
        c['bf16_byte_service']={'manifest_sha256':file_hash(ct/'qwen3_target_manifest.json'),
                               'objects':numeric['q3_object_count'],'sampled_spans':numeric['q3_sampled_spans'],
                               'sampled_objects':numeric['q3_sampled_objects'],'sampled_shards':numeric['q3_sampled_shards'],
                               'all_payload_bytes_rehashed_this_round':False}
    save(ct/(name+'.json'),c)
coverage=load(ct/'implementation_coverage.json')
changes={'Q3-03':'core/payload_collectives.py','C-01':'runtime/native_live_controls.cc',
         'C-04':'runtime/live_controls.h','C-05':'runtime/live_controls.h'}
for row in coverage:
    path=changes.get(row['id'],row['relative_path'])
    row.update(relative_path=path,path=str(ROOT/path),sha256=file_hash(ROOT/path))
    row['scope']='CPU payload/native control/reference only; full target coupling remains unverified'
save(ct/'implementation_coverage.json',coverage)
gates={}
for name,prefix in [('qwen3','Q3'),('qwen15','Q15')]:
    gates[name]=source_gate(load(ct/(name+'.json')),[r for r in coverage if r['id'].startswith((prefix,'C-'))])
    require(not gates[name]['p0_1_source_complete'],'unexpected target admission')
save(ct/'gates_v4.json',gates)
previous=ev/'INHERITED_GATES_v3.json'
if not previous.exists():save(previous,load(ct/'gates.json'))
save(ct/'gates.json',{name:{'source':value,'performance':{'ready':False,
     'reason':'full target numeric payload/timing/lifetime/cost coupling is not complete',
     'formal_performance_started':False}} for name,value in gates.items()})
save(ct/'runtime.json',{'models':{name:{'prior_target_runtime':load(ct/(name+'.json'))['runtime'],
     'tested_candidates':load(ct/(name+'.json'))['tested_candidates']} for name in ('qwen3','qwen15')},
     'full_composite_executed':False,'full_layer_payload_timing_coupled':False,'formal_performance_started':False})
with (ROOT/'IMPLEMENTATION_STATUS_v4.csv').open('w',newline='',encoding='utf-8-sig') as f:
    fields=['id','relative_path','implementation','sha256','scope'];writer=csv.DictWriter(f,fieldnames=fields)
    writer.writeheader();writer.writerows({k:r[k] for k in fields} for r in coverage)
status={'status':'PARTIAL_P0_1B_COMPLETE_SCOPED_P0_1C','plan_saved':'CA_两模型实验计划_20261102_v4.md',
        'p0_1b':'PARTIAL: CPU functional MoE and actual control integration; full target layer still missing',
        'p0_1c':'complete identity-gated decisions for requested known historical assets, not all-event replay',
        'remote_tests':software,'final_build_identity':digest(build),'real_control_probe_runs':2,
        'final_diagnostic_MoE_subgraphs':2,'complete_model_forwards':0,'GPU_runs':0,
        'formal_performance_runs':0,'p0_2_started':False,'performance_ready':False,
        'next_required':[
            'connect actual attention/residual/norm/KV output to normalized MoE inputs without fixture substitution',
            'couple actual numeric primitive, SRS/SAG payload and physical memory/NoC completion in the same target execution',
            'bind 72 Q15 QKV biases and all PP/TP precision boundaries in the full target layer',
            'complete dynamic host/HB/KV/activation/SRAM lifetime, migration/cache version and CPU/PCIe costs',
            'only then conduct P0-2 minimal numerical/timing admission before formal performance matrices'],
        'sources':{p.name:file_hash(p) for p in (ev/'REMOTE_BUILD_LIVE_02.json',ev/'REMOTE_PAYLOAD_AUDIT_v2.json',
                    ev/'REMOTE_SOFTWARE_CHECKS_v4.json',ev/'REAL_CONTROL_PROBE_02.json',ev/'REUSE_DISPOSITIONS.json')}}
save(ROOT/'STATUS.json',status)
print(json.dumps({'status':status['status'],'remote_tests':software['tests'],'formal_performance_runs':0,
                  'q3_source_missing':gates['qwen3']['missing'],'q15_source_missing':gates['qwen15']['missing']}))
