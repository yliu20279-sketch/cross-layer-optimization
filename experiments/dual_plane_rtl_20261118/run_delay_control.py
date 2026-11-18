"""Add 30 matched configuration controls using the same tested RTL library."""
import concurrent.futures,hashlib,json,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    build=json.loads((R/'CURRENT_BUILD.json').read_text());assert build['status']=='PASS'
    root=Path(build['path']);image=build['image'];src=root/'source'
    assert sha(R/'sim/main.cpp')==build['source_sha256']['sim/main.cpp']
    assert sha(R/'sim/controller.h')==build['source_sha256']['sim/controller.h']
    digest=sha(R/'sim/delay_control.cpp');dest=R/'control_builds'/(build['build_id']+'_'+digest[:8]);dest.mkdir(parents=True,exist_ok=True)
    for name in ['main.cpp','controller.h','delay_control.cpp']:shutil.copy2(R/'sim'/name,dest/name)
    docker=['docker','run','--rm','--network','none','--cpus','2','--memory','3g',
       '--mount',f'type=bind,src={root},dst=/rtl,readonly','--mount',f'type=bind,src={dest},dst=/control','-w','/control',image]
    with (dest/'BUILD.log').open('w') as f:
        p=subprocess.run(docker+['g++','-std=c++17','-O1','-I/rtl/obj1','-I/usr/share/verilator/include','-I/usr/share/verilator/include/vltstd',
            '/control/delay_control.cpp','/rtl/obj1/Vdut__ALL.a','/rtl/obj1/verilated.o','/rtl/obj1/verilated_threads.o','-pthread','-latomic','-o','/control/delay_control'],stdout=f,stderr=subprocess.STDOUT)
    if p.returncode:raise RuntimeError((dest/'BUILD.log').read_text()[-3000:])
    receipt=dict(status='built',base_build_id=build['build_id'],rtl_digest=build['source_digest'],image=image,
        source_sha256={'sim/delay_control.cpp':digest,**{n:v for n,v in build['source_sha256'].items() if n.startswith('sim/')}},
        binary_sha256=sha(dest/'delay_control'))
    cases=json.loads((R/'CASES.json').read_text());out=R/'delay_controls'/build['build_id'];out.mkdir(parents=True,exist_ok=True)
    tasks=[dict(case=c['name'],arm='delay_control',mode=1,hiband=0,bank=8,clock=1) for c in cases]
    def run(t):
        case=R/'cases'/(t['case']+'.txt');expected=next(c['case_sha256'] for c in cases if c['name']==t['case']);assert sha(case)==expected
        name=t['case']+'_delay_control_b8'
        with (out/(name+'.json')).open('w') as f,(out/(name+'.err')).open('w') as e:
            p=subprocess.run(['docker','run','--rm','--network','none','--cpus','1','--memory','3g',
                '--mount',f'type=bind,src={dest},dst=/control,readonly','--mount',f'type=bind,src={R/"cases"},dst=/cases,readonly',
                image,'/control/delay_control','--case','/cases/'+case.name,'delay_control'],stdout=f,stderr=e,timeout=900)
        assert p.returncode==0,(name,(out/(name+'.err')).read_text()[-2000:])
        d=json.loads((out/(name+'.json')).read_text());assert d['status']=='PASS_RTL_DELIVERY_PAYLOAD_AND_SRAM'
        assert all(w['cs_flits']==0 and w['configuration_requests'] in [0,62] for w in d['waves'])
        print('control PASS',name,flush=True);return dict(name=name,status='PASS')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:runs=list(pool.map(run,tasks))
    # Do not race a base matrix writer. Controls can run alongside the base jobs.
    while True:
        matrix=json.loads((R/'MATRIX.json').read_text())
        assert matrix['rtl_digest']==build['source_digest']
        if matrix['status']!='running':break
        time.sleep(5)
    assert matrix['status']=='PASS';target=Path(matrix['result_path'])
    for run in runs:shutil.copy2(out/(run['name']+'.json'),target/(run['name']+'.json'))
    # Require identical setup timing before releasing the selected packets.
    for t in tasks:
        a=json.loads((target/(t['case']+'_forced_cs_b8.json')).read_text())
        b=json.loads((target/(t['case']+'_delay_control_b8.json')).read_text())
        assert [(w['setup_begin'],w['setup_end'],w['configuration_requests'],w['selected_paths']) for w in a['waves']]==[(w['setup_begin'],w['setup_end'],w['configuration_requests'],w['selected_paths']) for w in b['waves']],t['case']
    matrix['tasks']=[t for t in matrix['tasks'] if t['arm']!='delay_control']+tasks
    matrix['runs']=[t for t in matrix['runs'] if not t.get('name','').endswith('_delay_control_b8')]+runs
    receipt.update(status='PASS_IDENTICAL_SETUP_AND_HOLD_CONTROL',runs=len(runs));matrix['delay_control_extension']=receipt
    matrix.update(completed=len(matrix['runs']),finished_unix=time.time())
    (dest/'RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n');(R/'DELAY_CONTROL.json').write_text(json.dumps(receipt,indent=2)+'\n')
    for p in [R/'MATRIX.json',target/'MANIFEST.json']:p.write_text(json.dumps(matrix,indent=2)+'\n')
    print('PASS 30 matched configuration controls; matrix now',len(matrix['tasks']),'runs',flush=True)
if __name__=='__main__':main()
