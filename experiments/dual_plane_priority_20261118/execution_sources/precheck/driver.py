"""Lyc L1/L2: new policy regressions, then 24 new runs. No synthesis."""
import concurrent.futures,csv,hashlib,json,os,subprocess,time,traceback
from pathlib import Path
R=Path(__file__).resolve().parent
SOURCES=['noc_pkg.sv','fifo.sv','benes8.sv','width_link.sv','split_width_link.sv','xy_router.sv','mesh.sv','hiband_fabric.sv','typed_ni.sv','cs_fabric.sv','configuration_sequencer.sv','experiment_top.sv']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):
    temp=p.with_suffix(p.suffix+'.tmp');temp.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');temp.replace(p)
def main():
    source=json.loads((R/'SOURCE_MANIFEST.json').read_text());image=source['image']
    for name,h in source['source_sha256'].items():assert sha(R/name)==h,name
    assert (R/'START_AUTHORIZED.json').exists(),'Use the deduplicating deployer, not direct launch'
    build=dict(status='building',source_digest=source['source_digest'],image=image,targets=[],started=time.time())
    write(R/'BUILD.json',build)
    docker=['docker','run','--rm','--network','none','--cpus','4','--memory','10g','--pids-limit','256','--mount',f'type=bind,src={R},dst=/work','-w','/work',image]
    def command(cmd,log,timeout=1800):
        start=time.time()
        with (R/log).open('w') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
        record=dict(command=cmd,returncode=p.returncode,seconds=time.time()-start,log=log,log_sha256=sha(R/log))
        assert p.returncode==0,record
        return record
    tests=[]
    tests.append(command(docker+['verilator','--cc','--exe','--assert','-Wno-fatal','-I/work/rtl','--top-module','xy_router','-GTYPE_PRIORITY=1','--Mdir','obj_priority_unit','/work/rtl/noc_pkg.sv','/work/rtl/fifo.sv','/work/rtl/benes8.sv','/work/rtl/xy_router.sv','/work/sim/priority_router_main.cpp'],'UNIT_BUILD.log'))
    tests.append(command(docker+['make','-C','obj_priority_unit','-f','Vxy_router.mk','-j','4'],'UNIT_COMPILE.log'))
    tests.append(command(docker+['/work/obj_priority_unit/Vxy_router'],'UNIT_TEST.log',60))
    for mode in [0,2,1]:
        prefix='Vdut';out=f'obj{mode}'
        cmd=docker+['verilator','--cc','--exe','--assert','-Wno-fatal','-I/work/rtl','--top-module','experiment_top','--prefix',prefix,'--Mdir',out,'-CFLAGS','-std=c++17',f'-GDUAL={mode}','-GTYPE_PRIORITY=1']+['/work/rtl/'+s for s in SOURCES]+['/work/sim/main.cpp']
        rec=dict(mode=mode,type_priority=1,commands=[])
        rec['commands'].append(command(cmd,f'VERILATE_{mode}.log'))
        rec['commands'].append(command(docker+['make','-C',out,'-f',prefix+'.mk','-j','4','OPT_FAST=-O1','OPT_SLOW=-O0'],f'COMPILE_{mode}.log'))
        modes=[0,1,2,3] if mode==2 else [0]
        for hb in modes:
            test=docker+[f'/work/{out}/Vdut','--selftest']+(['--shared'] if mode!=1 else [])+(['--mode',str(hb)] if mode==2 else [])
            rec['commands'].append(command(test,f'SELFTEST_{mode}_{hb}.log',900))
        if mode==1:rec['commands'].append(command(docker+['/work/obj1/Vdut','--controller-test'],'CONTROLLER_TEST.log',900))
        rec.update(status='PASS',binary_sha256=sha(R/out/prefix));build['targets'].append(rec);write(R/'BUILD.json',build)
    build.update(status='PASS',unit_tests=tests,finished=time.time());write(R/'BUILD.json',build)
    arms=[('mesh',0,0),('hiband_FG',2,0),('hiband_GB',2,1),('hiband_LB',2,2)]
    tasks=[dict(case=c['name'],arm=a,mode=m,hiband=hb,bank=8,clock=1,policy='type_priority') for c in source['cases'] for a,m,hb in arms]
    assert len(tasks)==24
    matrix=dict(status='running',source_digest=source['source_digest'],image=image,workers=8,tasks=tasks,runs=[],started=time.time(),completed=0,
        binaries={str(x['mode']):x['binary_sha256'] for x in build['targets']},case_hashes={c['name']:c['case_sha256'] for c in source['cases']})
    (R/'results').mkdir(exist_ok=True);write(R/'MATRIX.json',matrix)
    def run(t):
        name=t['case']+'_'+t['arm']+'_type_priority_b8';p=R/'results'/(name+'.json')
        assert not p.exists(),'Never overwrite or rerun an existing result'
        assert sha(R/'cases'/(t['case']+'.txt'))==matrix['case_hashes'][t['case']]
        cmd=['docker','run','--rm','--network','none','--cpus','1','--memory','3g','--pids-limit','256','--mount',f'type=bind,src={R},dst=/work,readonly',image,
            f'/work/obj{t["mode"]}/Vdut','--case','/work/cases/'+t['case']+'.txt',t['arm'],'--bank','8','--clock-ns','1','--shared']
        if t['mode']==2:cmd+=['--mode',str(t['hiband'])]
        start=time.time()
        with p.open('x') as out,(R/'results'/(name+'.err')).open('x') as err:ret=subprocess.run(cmd,stdout=out,stderr=err,timeout=900)
        if ret.returncode:return dict(name=name,task=t,status='FAIL',returncode=ret.returncode,command=cmd,seconds=time.time()-start)
        d=json.loads(p.read_text());assert d['status']=='PASS_RTL_DELIVERY_PAYLOAD_AND_SRAM'
        return dict(name=name,task=t,status='PASS',command=cmd,sha256=sha(p),seconds=time.time()-start)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(run,t):t for t in tasks}
        for fut in concurrent.futures.as_completed(futures):
            try:rec=fut.result()
            except Exception as e:rec=dict(task=futures[fut],status='FAIL',error=repr(e))
            matrix['runs'].append(rec);matrix['completed']=len(matrix['runs']);write(R/'MATRIX.json',matrix);print(json.dumps(rec),flush=True)
    matrix.update(status='PASS' if all(x['status']=='PASS' for x in matrix['runs']) else 'FAILED',finished=time.time());write(R/'MATRIX.json',matrix)
    assert matrix['status']=='PASS','Retain failures; no automatic retry'
    # Only own summary; original common analysis remains with C1/C4 owner.
    subprocess.run(['python3',str(R/'audit_priority.py')],cwd=R,check=True)

if __name__=='__main__':
    try:main()
    except BaseException as e:
        write(R/'FAILURE.json',dict(status='FAILED_RETAINED_NO_AUTOMATIC_RETRY',error=repr(e),traceback=traceback.format_exc(),time=time.time()))
        raise
