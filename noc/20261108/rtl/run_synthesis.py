"""Generic logic only: private Yosys, strict checks, source/output hashes."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,platform,subprocess,sys,time

ROOT=Path(__file__).resolve().parent
TOPS=('router_local_top','router_aux_top','terminal_switch','node_selectors','managed_endpoint')

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    os.chdir(ROOT);out=ROOT/'build/synth';out.mkdir(parents=True,exist_ok=True)
    status={'status':'running','host':platform.node(),'utc':datetime.now(timezone.utc).isoformat(),
            'process_library':None,'area_um2':None,'timing_closed':False,'application_performance':False,
            'tops':{},'source_sha256':{},'tool_wheel_sha256':{}}
    target=out/'synthesis_status.json'
    def save():target.write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
    for p in sorted((ROOT/'rtl').glob('*.sv')):status['source_sha256'][p.relative_to(ROOT).as_posix()]=digest(p)
    for p in (ROOT/'synth/tops.sv',ROOT/'run_synthesis.py',ROOT/'tool_command.py'):status['source_sha256'][p.relative_to(ROOT).as_posix()]=digest(p)
    for p in sorted((ROOT/'tools/wheels').glob('*.whl')):status['tool_wheel_sha256'][p.name]=digest(p)
    save()
    tool=[sys.executable,'tool_command.py']
    try:
        version=subprocess.run(tool+['-V'],capture_output=True,text=True,timeout=180)
        status['tool_version']=version.stdout+version.stderr
        if version.returncode:raise RuntimeError('Yosys version check failed')
        for top in TOPS:
            start=time.monotonic()
            # Parse only dependencies needed for each top. No benchmark or RTL changes.
            if top.startswith('router_'):sources=['rtl/aux_xy_router.sv','synth/tops.sv']
            elif top=='managed_endpoint':sources=['rtl/ni_config_agent.sv','rtl/merge_two.sv','rtl/managed_endpoint.sv']
            else:sources=[f'rtl/{top}.sv']
            script=['read_verilog -sv '+' '.join(sources)]
            if top in ('node_selectors','managed_endpoint'):script.append(f'chparam -set NODE_ID 5 {top}')
            script += [f'hierarchy -check -top {top}',f'synth -top {top}','flatten','opt_clean','check -assert',
                       'select -assert-none t:$dlatch t:$adlatch t:$dlatchsr t:$_DLATCH*',
                       'scc -expect 0',f'tee -o build/synth/{top}.stat.json stat -json',
                       f'write_json build/synth/{top}.netlist.json',
                       f'write_verilog -noattr build/synth/{top}.netlist.v']
            ys=out/f'{top}.ys';ys.write_text('\n'.join(script)+'\n',encoding='utf-8')
            command=tool+['-s',ys.relative_to(ROOT).as_posix()]
            cp=subprocess.run(command,capture_output=True,text=True,timeout=600)
            log=out/f'{top}.log';log.write_text(cp.stdout+cp.stderr,encoding='utf-8')
            status['tops'][top]={'passed':cp.returncode==0,'seconds':round(time.monotonic()-start,3),'command':command,'returncode':cp.returncode}
            save()
            print(f'{top}: returncode={cp.returncode}, seconds={status["tops"][top]["seconds"]}',flush=True)
            if cp.returncode:raise RuntimeError(f'{top} synthesis/check failed; inspect log')
            stat=out/f'{top}.stat.json';netlist=out/f'{top}.netlist.json';verilog=out/f'{top}.netlist.v'
            stats=json.loads(stat.read_text())
            net=json.loads(netlist.read_text())
            cells=net['modules'][top]['cells']
            types={}
            for cell in cells.values():types[cell['type']]=types.get(cell['type'],0)+1
            latches=[name for name in types if 'LATCH' in name.upper()]
            if latches:raise RuntimeError(f'unexpected mapped latch: {latches}')
            status['tops'][top].update({'generic_cells':len(cells),'cell_types':types,'latch_cells':0,
                                       'stat_sha256':digest(stat),'netlist_sha256':digest(netlist),'verilog_sha256':digest(verilog),
                                       'log_sha256':digest(log),'script_sha256':digest(ys)})
            save()
        status['status']='passed_generic_synthesis';save()
        print('PASS generic synthesis: 5 tops, no selected latches, check/assert and SCC=0; no process-area or timing claim',flush=True)
    except BaseException as e:
        status['status']='failed';status['error']=str(e);save();raise

if __name__=='__main__':main()
