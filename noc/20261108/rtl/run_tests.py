from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,platform,shutil,subprocess,time
from iverilog_direct import compile_sv

ROOT=Path(__file__).resolve().parent
CLUSTER_TOOLS=Path('/mnt/sdb1/h4567/noc_rtl_validation_20261103/tools/iverilog/bin')

def main():
    os.chdir(ROOT);build=ROOT/'build';build.mkdir(exist_ok=True)
    iv=os.environ.get('IVERILOG') or shutil.which('iverilog') or str(CLUSTER_TOOLS/'iverilog')
    vv=os.environ.get('VVP') or shutil.which('vvp') or str(CLUSTER_TOOLS/'vvp')
    result={'utc':datetime.now(timezone.utc).isoformat(),'host':platform.node(),'platform':platform.platform(),'working_directory':str(ROOT),
            'all_passed':False,'tests':{},'sha256':{},'scope':'5-input/6-output router and functional transition tests; no HiBand microarchitecture or application performance validation'}
    def save(): (build/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    save()
    for exe,name in ((iv,'iverilog'),(vv,'vvp')):
        cp=subprocess.run([exe,'-V'],capture_output=True,text=True,errors='replace',timeout=30)
        (build/f'{name}_version.log').write_text(cp.stdout+cp.stderr,encoding='utf-8')
        if cp.returncode:raise RuntimeError(f'{name} runtime missing/broken: {cp.returncode}')
        result[name]={'path':exe,'sha256':hashlib.sha256(Path(exe).read_bytes()).hexdigest()}
    if os.name=='nt':
        result['compiler_mode']='real ivlpp + ivl, avoiding crashing Windows shell driver'
        rc,log,meta=compile_sv(iv,'tb_tool_invalid',['negative/invalid.sv'],'build/invalid.vvp')
    else:
        result['compiler_mode']='standard iverilog driver'
        cp=subprocess.run([iv,'-g2012','-s','tb_tool_invalid','-o','build/invalid.vvp','negative/invalid.sv'],capture_output=True,text=True)
        rc,log,meta=cp.returncode,cp.stdout+cp.stderr,{}
    (build/'negative_compile.log').write_text(log,encoding='utf-8')
    if rc==0 or 'syntax error' not in log:raise RuntimeError('compiler did not reject intentional syntax error')
    result['negative_compiler_check']={'rejected':True,'returncode':rc,'metadata':meta}
    for name,top,args in [('tool_smoke','tb_tool_smoke',[]),('aux_router','tb_aux_router',[]),('transition','tb_transition',[]),('timeout','tb_transition',['+FAIL_MODE']),('management','tb_management',[])]:
        before=time.monotonic()
        rtl=[] if name=='tool_smoke' else (['rtl/aux_xy_router.sv'] if name=='aux_router' else [p.as_posix() for p in sorted(Path('rtl').glob('*.sv'))])
        image=f'build/{name}.vvp'
        cmd=[iv,'-g2012','-Wall','-s',top,'-o',image]+rtl+[f'tb/{top}.sv']
        metadata={}
        if os.name=='nt':
            compile_rc,compile_log,metadata=compile_sv(iv,top,rtl+[f'tb/{top}.sv'],image)
            cmd=metadata['compile_command']
        else:
            cp=subprocess.run(cmd,capture_output=True,text=True,errors='replace',timeout=180)
            compile_rc,compile_log=cp.returncode,cp.stdout+cp.stderr
        (build/f'{name}_compile.log').write_text(compile_log,encoding='utf-8')
        if compile_rc:raise RuntimeError(f'{name}: compilation failed ({compile_rc})')
        sim=subprocess.run([vv,image]+args,capture_output=True,text=True,errors='replace',timeout=300)
        output=sim.stdout+sim.stderr
        (build/f'{name}_simulation.log').write_text(output,encoding='utf-8')
        ok=sim.returncode==0 and f'PASS {name}' in output and 'FATAL' not in output
        result['tests'][name]={'passed':ok,'seconds':round(time.monotonic()-before,3),'compile_command':cmd,'compile_metadata':metadata,'compile_returncode':compile_rc,'simulation_returncode':sim.returncode,'simulation_command':[vv,image]+args,'output':output.strip()}
        print(output,flush=True);save()
        if not ok:raise RuntimeError(f'{name}: simulation failed')
    for folder in ('rtl','tb','synth','negative'):
        for p in sorted((ROOT/folder).glob('*')):
            if p.is_file():result['sha256'][p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    for name in ('run_tests.py','check_artifacts.py','run_remote.sh','iverilog_direct.py','run_local.ps1','probe_local_tool.py'):
        result['sha256'][name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    result['all_passed']=True;save()

if __name__=='__main__':
    (ROOT/'build').mkdir(exist_ok=True)
    status=ROOT/'build/runner.exit'
    status.write_text('running\n',encoding='ascii')
    try:
        main()
    except BaseException:
        status.write_text('1\n',encoding='ascii')
        raise
    else:
        status.write_text('0\n',encoding='ascii')
