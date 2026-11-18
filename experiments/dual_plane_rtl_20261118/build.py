"""Immutable source snapshots, pinned image, real RTL and independent units."""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent
SOURCES=['noc_pkg.sv','fifo.sv','benes8.sv','width_link.sv','split_width_link.sv','xy_router.sv','mesh.sv','hiband_fabric.sv','typed_ni.sv','cs_fabric.sv','configuration_sequencer.sv','experiment_top.sv']
def main():
    paths=[*[R/'rtl'/s for s in SOURCES],*sorted((R/'rtl').glob('*.svh')),*sorted((R/'sim').glob('*.cpp')),*sorted((R/'sim').glob('*.h'))]
    hashes={p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    digest=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()[:16]
    image=subprocess.check_output(['docker','image','inspect',os.environ.get('NOC_TOOL_IMAGE','noc-experiment-tools:20261118-clean'),'--format','{{.Id}}'],text=True).strip()
    build_id=digest+'_'+image.replace('sha256:','')[:12]
    dest=R/'builds'/build_id;src=dest/'source';src.mkdir(parents=True,exist_ok=True)
    for p in paths:
        target=src/p.relative_to(R);target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert target.read_bytes()==p.read_bytes()
        else:shutil.copy2(p,target)
    ledger=dict(source_digest=digest,build_id=build_id,image=image,source_sha256=hashes,status='building',builds=[])
    def save():
        (dest/'RECEIPT.json').write_text(json.dumps(ledger,indent=2))
        (R/'CURRENT_BUILD.json').write_text(json.dumps(dict(path=str(dest),**ledger),indent=2))
    save()
    docker=['docker','run','--rm','--network','none','--cpus','4','--memory','10g','--mount',f'type=bind,src={dest},dst=/work','-w','/work',image]
    targets=[('benes','benes8',['benes8.sv'],'benes_main.cpp',[]),
             ('benes5','benes8',['benes8.sv'],'benes_main.cpp',['-GROUTER=1']),
             ('link','width_link',['noc_pkg.sv','width_link.sv'],'link_main.cpp',[]),
             ('split','split_width_link',['noc_pkg.sv','split_width_link.sv'],'split_link_main.cpp',[])]
    targets += [(str(m),'experiment_top',SOURCES,'main.cpp',[f'-GDUAL={m}']) for m in [1,0,2]]
    for tag,top,files,cpp,extra in targets:
        prefix='Vdut' if top=='experiment_top' else 'V'+top
        cmd=docker+['verilator','--cc','--exe','--assert','-Wno-fatal','-I/work/source/rtl','--top-module',top,'--prefix',prefix,'--Mdir','obj'+tag,'-CFLAGS','-std=c++17',*extra]+['/work/source/rtl/'+s for s in files]+['/work/source/sim/'+cpp]
        start=time.time();log=dest/('BUILD_'+tag+'.log')
        with log.open('w') as f:
            p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
            if p.returncode==0:
                p=subprocess.run(docker+['make','-C','obj'+tag,'-f',prefix+'.mk','-j','4','OPT_FAST=-O1','OPT_SLOW=-O0'],stdout=f,stderr=subprocess.STDOUT)
        ledger['builds'].append(dict(target=tag,returncode=p.returncode,seconds=time.time()-start));save()
        if p.returncode:
            ledger['status']='BUILD_FAILED';save();raise RuntimeError(log.read_text()[-5000:])
        commands=[docker+[f'/work/obj{tag}/{prefix}']]
        if tag=='benes5':commands=[docker+[f'/work/obj{tag}/{prefix}','--five']]
        if top=='experiment_top':commands=[docker+[f'/work/obj{tag}/{prefix}','--selftest']+(['--shared'] if tag!='1' else [])]
        if tag=='2':commands=[docker+[f'/work/obj2/{prefix}','--selftest','--shared','--mode',str(m)] for m in [0,1,2,3]]
        if tag=='1':commands.append(docker+['/work/obj1/Vdut','--controller-test'])
        with (dest/('SELFTEST_'+tag+'.log')).open('w') as f:
            for cmd in commands:
                p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=900)
                if p.returncode:break
        print(tag,'test',p.returncode,(dest/('SELFTEST_'+tag+'.log')).read_text()[-2200:],flush=True)
        if p.returncode:
            ledger['status']='TEST_FAILED';save();raise RuntimeError('RTL regression failed '+tag)
        ledger['builds'][-1]['selftest']='PASS';save()
    ledger['status']='PASS';save()
if __name__=='__main__':main()
