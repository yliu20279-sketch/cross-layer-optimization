"""Private native build; no mutation of accepted or active experiment roots."""
from pathlib import Path
import datetime,hashlib,json,shutil,subprocess
R=Path(__file__).resolve().parent;B=R.parent
V=B/'noc_crosslayer_validation_20261108';U=B/'noc_native_dram_causality_20261108'
state={'state':'preparing','scope':'short native configuration integration','application_performance':False}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save():state['updated']=datetime.datetime.now().isoformat();(R/'chain_build_status.json').write_text(json.dumps(state,indent=2))
def run(name,argv,timeout=1800):
    with (R/(name+'.log')).open('xb') as f:subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=timeout)
save()
try:
    shutil.copytree(V/'npu',R/'npu',ignore=shutil.ignore_patterns('build','__pycache__'))
    for name,source in [('unit_endpoint.cpp',U),('check_request_ids.cpp',V),('supervise.py',V),
                        ('check_source.py',V),('prepare_memory_program.py',U),('audit_memory_queries.py',U)]:
        shutil.copy2(source/name,R/name)
    for component in ('core','noc','reference_noc'):
        (R/component/'build').mkdir(parents=True)
        binary='interchiplet' if component=='core' else 'popnet_cs_ni'
        shutil.copy2(V/component/'build'/binary,R/component/'build'/binary)
        assert sha(R/component/'build'/binary)==sha(V/component/'build'/binary)
    # Append only an independent test executable in this private copy.
    with (R/'npu/CMakeLists.txt').open('a') as f:
        f.write('\nadd_executable(short_chain ../short_chain.cpp)\n'
                'target_include_directories(short_chain PRIVATE ${CMAKE_CURRENT_SOURCE_DIR} ${CMAKE_CURRENT_SOURCE_DIR}/reference_core ${SIM}/interchiplet/includes)\n'
                'target_link_libraries(short_chain PRIVATE original_runtime)\n'
                'target_compile_options(short_chain PRIVATE -Wall -Wextra -Werror)\n')
    state['state']='building_private_native_chain';save()
    run('chain_configure',['cmake','-S',str(R/'npu'),'-B',str(R/'npu/build'),'-DCMAKE_BUILD_TYPE=Release'])
    run('chain_compile',['cmake','--build',str(R/'npu/build'),'--target','short_chain','-j','2'])
    (R/'build_validation_status.json').write_text(json.dumps({'state':'protocol_units_passed',
        'binary_sha256':sha(R/'noc/build/popnet_cs_ni'),'proof':str(B/'noc_current_control_validation_20261108/status_retry1.json')}))
    files=[*R.glob('*.py'),R/'short_chain.cpp',R/'core/build/interchiplet',R/'noc/build/popnet_cs_ni',
           R/'reference_noc/build/popnet_cs_ni',R/'npu/build/short_chain',
           B/'ramulator_wallclock_20261107/build/ramulator2']
    files += [p for p in (R/'npu').rglob('*') if p.is_file() and 'build' not in p.parts]
    (R/'chain_input_hashes.json').write_text(json.dumps({str(p):sha(p) for p in files if p.is_file()},indent=2))
    state['state']='short_native_chain_running';save()
    run('chain_run',['python3',str(R/'run_chain.py')],timeout=1900)
    state['state']='independent_short_audits';save()
    run('chain_audit',['python3',str(R/'audit_chain.py')],timeout=1800)
    assert all(sha(Path(p))==h for p,h in json.loads((R/'chain_input_hashes.json').read_text()).items())
    state.update(state='passed',input_hashes_unchanged=True)
except BaseException as e:state.update(state='failed',reason=repr(e));save();raise
finally:save()
