from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import csv,datetime,hashlib,json,shutil,subprocess
R=Path(__file__).resolve().parent;B=R.parent;T=B/'noc_hb_transport_20261108';REF=B/'noc_dram_observer_reference_20261108'
state={'state':'preparing','performance_claim':False}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save():state['updated']=datetime.datetime.now().isoformat();(R/'observer_status.json').write_text(json.dumps(state,indent=2))
def run(root):
    with (root/'observer_driver.log').open('xb') as log:
        subprocess.run(['python3',str(root/'run_application.py'),'--name','observer_phase1','--seed',str(seed),
                        '--observer-only','--rounds','1','--timeout','1800'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1900)
save()
try:
    assert json.loads((R/'build_status.json').read_text())['state']=='passed'
    units=json.loads((R/'status.json').read_text());assert units['state']=='completed' and all(v['converged'] for v in units['cases'])
    old=json.loads((T/'runtime_preparation_status.json').read_text());prep=dict(old);prep['binaries']={k:sha(R/k) for k in old['binaries']}
    (R/'runtime_preparation_status.json').write_text(json.dumps(prep,indent=2));shutil.copy2(T/'hb_contract.json',R/'hb_contract.json')
    REF.mkdir()
    for c,exe in (('core','interchiplet'),('npu','endpoint_decoder'),('noc','popnet_cs_ni')):
        (REF/c/'build').mkdir(parents=True);shutil.copy2(T/c/'build'/exe,REF/c/'build'/exe)
    for f in ('run_application.py','runtime_preparation_status.json','capacity_validation.json','supervise.py','network_packet.py','check_source.py','build_validation_status.json','hb_contract.json'):
        shutil.copy2(T/f,REF/f)
    nets=sorted((p for p in (T/'layer1_program/run').glob('proc_r*_p2_t0') if (p/'source_audit.json').exists()),key=lambda p:int(p.name.split('_')[1][1:]))
    seed=nets[-1]/'output_delayInfo.txt';state.update(state='running_native_equivalence',seed=str(seed));save()
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,(R,REF)))
    a=REF/'observer_phase1/run';b=R/'observer_phase1/run';checks={}
    for n in range(16):
        actor=f'proc_r1_p1_t{n+16}'
        for p in (a/actor).rglob('*'):
            if p.is_file() and (p.suffix=='.csv' or p.name=='causal_program.txt'):
                rel=p.relative_to(a);checks[str(rel)]=sha(p)==sha(b/rel)
    for p in (a/'reports').glob('*.csv'):checks[str(p.relative_to(a))]=sha(p)==sha(b/p.relative_to(a))
    assert checks and all(checks.values()),[k for k,v in checks.items() if not v]
    (R/'observer_equivalence.json').write_text(json.dumps({'state':'passed','native_outputs':len(checks),'checks':checks,
        'old_causal_program_unchanged':True,'all_original_DRAM_transactions_unchanged':True,'same_actual_seed':str(seed)},indent=2))
    state.update(state='passed',original_outputs_byte_exact=len(checks))
except BaseException as e:state.update(state='failed',reason=repr(e));save();raise
finally:save()
