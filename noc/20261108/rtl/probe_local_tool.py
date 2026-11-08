"""Retain the standard Windows driver failure and independent core smoke check."""
from pathlib import Path
import json,os,subprocess
from iverilog_direct import compile_sv
ROOT=Path(__file__).resolve().parent
def main():
    os.chdir(ROOT);(ROOT/'build').mkdir(exist_ok=True)
    iv=os.environ['IVERILOG'];vv=os.environ['VVP']
    command=[iv,'-g2012','-s','tb_tool_smoke','-o','build/probe_driver.vvp','tb/tb_tool_smoke.sv']
    driver=subprocess.run(command,capture_output=True,text=True,errors='replace',timeout=30)
    rc,log,meta=compile_sv(iv,'tb_tool_smoke',['tb/tb_tool_smoke.sv'],'build/probe_core.vvp')
    if rc:raise RuntimeError('core smoke compile failed')
    sim=subprocess.run([vv,'build/probe_core.vvp'],capture_output=True,text=True,errors='replace',timeout=30)
    assert sim.returncode==0 and 'PASS tool_smoke' in sim.stdout
    result={'standard_driver_command':command,'standard_driver_returncode':driver.returncode,
            'standard_driver_output':driver.stdout+driver.stderr,'core_metadata':meta,'core_log':log,
            'core_simulation_returncode':sim.returncode,'core_simulation_output':sim.stdout+sim.stderr}
    (ROOT/'build/windows_tool_probe.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(f"tool probe: driver={driver.returncode}; ivlpp={meta['ivlpp_returncode']}; ivl={rc}; vvp={sim.returncode}")
if __name__=='__main__':main()
