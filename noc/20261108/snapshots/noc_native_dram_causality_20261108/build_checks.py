from pathlib import Path
import datetime,hashlib,json,subprocess
R=Path(__file__).resolve().parent
state={'state':'building','application_started':False,'performance_claim':False}
def save():state['updated']=datetime.datetime.now().isoformat();(R/'build_status.json').write_text(json.dumps(state,indent=2))
def run(label,args,cwd=R):
    with (R/(label+'.log')).open('xb') as f:subprocess.run(args,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,timeout=1800,check=True)
save()
try:
    for component in ('npu','noc'):
        run(component+'_configure',['cmake','-S',str(R/component),'-B',str(R/component/'build'),'-DCMAKE_BUILD_TYPE=Release'])
        run(component+'_build',['cmake','--build',str(R/component/'build'),'-j','2'])
    state['state']='native_memory_causal_units';save()
    config='/mnt/sda1/h4567/qwen15_moe_target_v36_20261009/ramulator2_hb_partition_v3_6_candidate.yaml'
    for mode in ('forward','reverse'):
        case=R/('memory_unit_'+mode);case.mkdir();run('memory_'+mode,[str(R/'noc/build/check_memory_program'),config,mode],case)
    a=R/'memory_unit_forward';b=R/'memory_unit_reverse'
    for name in ('dram_program_queries.csv','causal_command_times.csv','program_fences_summary.json'):
        assert (a/name).read_bytes()==(b/name).read_bytes(),name
    run('protocol',['python3',str(R/'validate_protocol_fixed.py')])
    assert json.loads((R/'protocol_test_status.json').read_text())['state']=='passed'
    digest=hashlib.sha256((R/'noc/build/popnet_cs_ni').read_bytes()).hexdigest()
    (R/'build_validation_status.json').write_text(json.dumps({'state':'protocol_units_passed','binary_sha256':digest}))
    state.update(state='passed',native_memory_completion_order_invariant=True,seven_protocol_cases_passed=True)
except BaseException as e:state.update(state='failed',reason=repr(e));save();raise
finally:save()
