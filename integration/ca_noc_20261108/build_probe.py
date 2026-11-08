"""Build an isolated CA backend with target parameters and a completion wait RPC.

    No source experiment is modified. Existing memory libraries are linked locally,
not copied into the repository. This is a serialized integration probe.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def replace(text, old, new):
    assert text.count(old) == 1, 'source interface changed: '+old[:70]
    return text.replace(old, new)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ca-root', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    args=ap.parse_args();ca=args.ca_root.resolve();out=args.out.resolve()
    assert not out.exists() and ca not in out.parents
    receipt=json.loads((ca/'evidence/NATIVE_BUILD_RECEIPT.json').read_text())
    # Only retain the actual memory dependency. Old NoC/thermal objects are not
    # linked: all network transfers are owned by the accepted target backend.
    checks=[]
    ramlib=next(Path(x) for x in receipt['link'] if x.endswith('/libramulator.so'))
    ramrow=next(r for r in receipt['backend_checks'] if r['path']==str(ramlib))
    assert sha(ramlib)==ramrow['expected']
    checks.append({'path':str(ramlib),'sha256':sha(ramlib)})
    out.mkdir(parents=True)
    source=(ca/'runtime/coupled_backend.cpp').read_text()
    source=replace(source,'static constexpr U capacity=512ull*1024*1024;',
                   'static constexpr U capacity=2147483648ull;')
    source=replace(source,'get_tx_bytes()==256','get_tx_bytes()==32')
    source=replace(source,'candidate architecture expects full 256-byte backend','integrated target requires 32-byte DRAM transactions')
    source=replace(source,'std::min({U(256),bytes-issued,U(4096-a%4096)})',
                   'std::min({U(32),bytes-issued,U(4096-a%4096)})')
    source=replace(source,'class CoupledState {','static std::string target_npu_config;\nclass CoupledState {')
    for name in ('configuration.h','sim_foundation.h','mess_queue.h','SRGen.h','live_controls.h'):
        source=replace(source,'#include "'+name+'"\n','')
    source=replace(source,'#include <array>','#include <algorithm>\n#include <array>')
    a=source.index('static std::function<void(size_t,double)> on_packet;')
    b=source.index('using U=unsigned long long;',a)
    source=source[:a]+source[b:]
    source=replace(source,'    mess_queue& queue;sim_foundation& network;configuration&config;\n    p0live::LinkController link;\n    bool controls;\n','')
    source=replace(source,'''    CoupledState(mess_queue&q,sim_foundation&n,configuration&c,const std::string&ram,const std::string&dir,bool ctl)
       :queue(q),network(n),config(c),link(10,3),controls(ctl),out(dir),''',
       '''    CoupledState(const std::string&ram,const std::string&dir)
       :out(dir),''')
    a=source.index('        on_packet=[this]')
    b=source.index('\n    }\n    void tick()',a)
    source=source[:a]+source[b:]
    source=source.replace('        queue.coupled_advance(double(cycle));\n','')
    source=replace(source,'        if(!network_pending.empty()||queue.message_queue_size())for(auto&r:network.inter_network())r.router_sim_pwr(1.0);\n','')
    a=source.index('    void transfer(U from,U to,U bytes){')
    b=source.index('    std::vector<U> layout()',a)
    source=source[:a]+source[b:]
    source=replace(source,'<<link.switches','<<0')
    a=source.index('    std::vector<std::string>args={')
    b=source.index('    U hello[8]=',a)
    source=source[:a]+'    CoupledState state(ram,out);\n'+source[b:]
    old='''        config.intra_delay_enable=false;config.vector_ops_per_cycle=16;config.reduce_ops_per_cycle=16;
        config.sram_bandwidth_bytes_per_cycle=256;config.mac_unit_count=4096;config.sram_per_mac_bytes=1024;'''
    source=replace(source,old,'''        config=NPUSim::loadConfig(target_npu_config);
        need(config.mac_unit_count==1&&config.sram_per_mac_bytes==4194304,
             "integrated target requires one array and 4MiB SRAM per NPU");
        need(config.sram_bandwidth_bytes_per_cycle==256,"SRAM bandwidth changed");''')
    source=replace(source,'need(argc==4,"usage backend out ram_config control");std::string out=argv[1],ram=argv[2];',
                   'need(argc==5,"usage backend out ram_config off npu_config");std::string out=argv[1],ram=argv[2];\n'
                   '    need(std::string(argv[3])=="off","legacy network controls must be disabled");target_npu_config=argv[4];')
    source=replace(source,'}else if(h[0]==7)state.transfer(h[1],h[2],h[3]);',
                   '}else if(h[0]==7)throw std::runtime_error("legacy NoC transfer disabled in integrated probe");\n'
                   '            else if(h[0]==16){need(h[1]>=state.cycle,"completion cannot move clock backwards");state.until(h[1]);}')
    generated=out/'coupled_backend.cpp';generated.write_text(source)
    base=list(receipt['compile'])
    base=[x for x in base if x!='-I'+str(Path(receipt['native_binary']).parent)]
    base+=['-I'+str(ca/'runtime')]
    base += [x for x in json.loads((ca/'upstream/BRIDGE_BUILD_COMMAND.json').read_text()) if x.startswith('-I')]
    base+=['-O2','-ffp-contract=off','-fno-fast-math','-ffunction-sections','-fdata-sections']
    commands=[]
    npu=Path('/mnt/sdb1/h3240101068/npusim_ramulator2_validation_20260826/workspace/NPUSim/npusim_runtime.cpp')
    native_inputs={str(p):sha(p) for p in (npu,npu.with_suffix('.h'),ca/'runtime/coupled_matrix.h')}
    for p,name in ((generated,'coupled'),(npu,'npusim')):
        cmd=list(base);cmd[cmd.index('-c')+1]=str(p);cmd[cmd.index('-o')+1]=str(out/(name+'.o'))
        commands.append(cmd)
        with (out/(name+'.compile.log')).open('xb') as f:
            subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=300)
    link=['/usr/bin/c++',str(out/'coupled.o'),str(out/'npusim.o'),str(ramlib),
          '-lboost_graph','-lpthread','-Wl,--gc-sections','-Wl,-rpath,'+str(ramlib.parent),
          '-o',str(out/'coupled_backend')]
    with (out/'link.log').open('xb') as f:
        subprocess.run(link,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
    assert all(sha(Path(p))==value for p,value in native_inputs.items()),'build inputs changed'
    report=dict(state='build_only',binary=str(out/'coupled_backend'),binary_sha256=sha(out/'coupled_backend'),
                source_sha256=sha(ca/'runtime/coupled_backend.cpp'),derived_source_sha256=sha(generated),
                frozen_dependencies=checks,native_inputs=native_inputs,commands=commands+[link],capacity_per_partition=2147483648,
                dram_transaction_bytes=32,legacy_noc_transfer_disabled=True,performance_ready=False)
    (out/'build_receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('state','binary_sha256','dram_transaction_bytes')}))

if __name__=='__main__':main()
