from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,platform,subprocess,time
ROOT=Path(__file__).resolve().parent
TOOL=Path('/mnt/sdb1/h4567/noc_rtl_validation_20261103/tools/iverilog/bin')
def main():
    os.chdir(ROOT);out=ROOT/'build/netlist_tests';out.mkdir(parents=True,exist_ok=True)
    result={'host':platform.node(),'utc':datetime.now(timezone.utc).isoformat(),'all_passed':False,'tests':{}}
    report=out/'verification.json'
    def save():report.write_text(json.dumps(result,indent=2)+'\n')
    save()
    cases=[('router','tb_aux_router','MAPPED_ROUTER',['router_aux_top','router_local_top'],'PASS aux_router'),
           ('cs','tb_switch','MAPPED_SWITCH',['terminal_switch'],'PASS switch')]
    for name,top,define,modules,expected in cases:
        files=[f'build/synth/{m}.netlist.v' for m in modules]+[f'tb/{top}.sv']
        cmd=[str(TOOL/'iverilog'),'-g2012','-s',top,'-D'+define,'-o',f'build/netlist_tests/{name}.vvp']+files
        before=time.monotonic()
        cp=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
        (out/f'{name}_compile.log').write_text(cp.stdout+cp.stderr)
        if cp.returncode:raise RuntimeError(f'{name} netlist compile failed')
        simcmd=[str(TOOL/'vvp'),f'build/netlist_tests/{name}.vvp']
        sim=subprocess.run(simcmd,capture_output=True,text=True,timeout=300)
        log=sim.stdout+sim.stderr;(out/f'{name}_simulation.log').write_text(log)
        passed=sim.returncode==0 and expected in log and 'FATAL' not in log
        result['tests'][name]={'passed':passed,'seconds':round(time.monotonic()-before,3),'compile_command':cmd,'simulation_command':simcmd,
                              'output':log.strip(),'sha256':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}}
        save();print(log,flush=True)
        if not passed:raise RuntimeError(f'{name} netlist regression failed')
    result['all_passed']=True;save()
if __name__=='__main__':main()
