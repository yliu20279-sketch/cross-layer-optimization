"""Build an isolated OPP-aware fork of the frozen native RPC backend."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Unexpected source around {old!r}')
    return text.replace(old, new)


def main(root, out, gets=None, pair=None):
    out.mkdir()
    receipt = json.loads((root / 'evidence/COUPLED_BUILD_04.json').read_text())
    for name in ('coupled_backend.cpp', 'coupled_matrix.h'):
        assert sha(root / 'runtime' / name) == receipt['source_sha256'][name]
    for item in receipt['inputs']:
        assert sha(item['path']) == item['sha256'], item['path']
    matrix = (root / 'runtime/coupled_matrix.h').read_text()
    matrix = replace(matrix, 'free[b]=st+1;done=std::max(done,st+1);',
                     'free[b]=st+r.sramService(b);done=std::max(done,free[b]);')
    (out / 'coupled_matrix.h').write_text(matrix)
    src = (root / 'runtime/coupled_backend.cpp').read_text()
    src = replace(src, '    U& chipCycle(){return s.cycle;}', '''    U opp_quarters=4, compute_remainder=0;
    std::array<U,8> sram_remainder{};
    U targetTicks(U base_cycles, U& remainder) const {
        const U total=base_cycles*4+remainder;
        remainder=total%opp_quarters;
        return total/opp_quarters;
    }
    U sramService(unsigned bank){return targetTicks(1,sram_remainder.at(bank));}
    U& chipCycle(){return s.cycle;}''')
    src = replace(src, '        auto result=NPUSim::scheduleNpuProgramEvents(events,config,s.cycle);', '''        const U begin=s.cycle;
        const U incoming_fraction=compute_remainder;
        auto result=NPUSim::scheduleNpuProgramEvents(events,config,begin);
        const auto at=[&](U cycle){return begin+((cycle-begin)*4+incoming_fraction)/opp_quarters;};''')
    src = replace(src, "<<e.start_cycle<<','<<e.complete_cycle<<'\\n';",
                  "<<at(e.start_cycle)<<','<<at(e.complete_cycle)<<'\\n';")
    src = replace(src, '        s.until(result.overall_finish_cycle);return result;',
                  '        s.until(begin+targetTicks(result.overall_finish_cycle-begin,compute_remainder));return result;')
    src = replace(src, '    while(true){U h[8],answer[8]', '''    U pending_opp=0, pending_release=0;
    std::ofstream opp_trace(out+"/OPP_MATRIX.csv");
    opp_trace<<"job,rank,opp_quarters,requested_release,rpc_ready,actual_start,complete,dram_requests\n";
    while(true){U h[8],answer[8]'''.replace('dram_requests\n"', 'dram_requests\\n"'))
    src = replace(src, '            if(h[0]==12){', '''            need(!pending_opp || h[0]==5,"OPP command must be consumed by the next matrix");
            if(h[0]==14){
                need(h[1]>=2&&h[1]<=4&&h[2]>=state.cycle&&h[2]<10000000000ull,"invalid OPP or release");
                pending_opp=h[1];pending_release=h[2];
            }else if(h[0]==12){''')
    src = replace(src, '                    if(h[7])kernel.run_fp16', '''                    const U ready=state.cycle;
                    const U selected=pending_opp ? pending_opp : 4;
                    const U release=pending_opp ? pending_release : ready;
                    state.until(release);
                    const U start=state.cycle, first_tx=state.txid;
                    runtime.opp_quarters=selected;
                    if(h[7])kernel.run_fp16''')
    src = replace(src, 'else kernel.run(a.address,b.address,c.address,h[4],h[5],h[6],state.jobs,out.c_str());}', '''else kernel.run(a.address,b.address,c.address,h[4],h[5],h[6],state.jobs,out.c_str());
                    if(pending_opp){
                        opp_trace<<state.jobs<<','<<a.rank<<','<<selected<<','<<release<<','<<ready<<','<<start<<','
                                 <<state.cycle<<','<<state.txid-first_tx<<'\\n';opp_trace.flush();
                    }
                    pending_opp=0;
                }''')
    # No per-transaction multi-gigabyte CSV for calibration. The backend still
    # executes every callback and retains total counters and native tile traces.
    src = replace(src, 'trace(dir+"/LIVE_EVENTS.csv")', 'trace("/dev/null")')
    if gets is not None:
        src = replace(src, '    std::map<size_t,U>network_pending;',
                      '    std::map<size_t,U>network_pending;\n' + gets.read_text())
        src = replace(src, 'on_packet=[this](size_t id,double t){auto it=',
                      'on_packet=[this](size_t id,double t){if(receive_gets_packet(id,t))return;auto it=')
        src = replace(src, 'if(!network_pending.empty()||queue.message_queue_size())',
                      '''service_gets();
        if(!network_pending.empty()||!gets_packets.empty()||queue.message_queue_size())''')
        src = replace(src, 'if(h[0]==14){', '''if(h[0]==15){
                state.arm_gets(h[1],h[2]);answer[3]=state.gets_start;
            }else if(h[0]==14){''')
        src = replace(src, 'else if(h[0]==8){answer[2]=state.cycle;',
                      'else if(h[0]==8){state.drain_gets();answer[2]=state.cycle;')
    if pair is not None:
        assert gets is not None
        src = replace(src, '    struct GetS {', pair.read_text()+'\n    struct GetS {')
        src = replace(src, '            if(h[0]==15){', '''            if(h[0]==16){
                need(state.cycle==0&&state.packetid==0&&state.txid==0,"late paired policy declaration");
                state.pair_policy.bind(h[1],h[2],h[3]);
            }else if(h[0]==15){''')
        src = replace(src, 'if(controls&&!link.can_issue(local,count*flitbytes,cycle))break;',
                      '''if(controls&&!link.can_issue(local,count*flitbytes,cycle))break;
                    if(!paired_admit(s.rank,d.rank,count))break;''')
        src = replace(src, '            need(cycle==gets_start+gets[next_gets].arrival,"GetS external arrival drifted");\n            gets[next_gets].request_inject=send_gets_packet(next_gets,false);\n            ++next_gets;',
                      '''            if(paired_admit(0,1,1)){
                gets[next_gets].request_inject=send_gets_packet(next_gets,false);
                ++next_gets;
            }''')
        src = replace(src, 'if(cycle>=gets[index].read_done){', 'if(cycle>=gets[index].read_done&&paired_admit(1,0,2)){')
        src = replace(src, 'state.drain_gets();answer[2]=state.cycle;',
                      'state.drain_gets();state.pair_policy.write(out);answer[2]=state.cycle;')
    patched = out / 'coupled_backend.cpp'
    patched.write_text(src)
    old = root / 'build_04'
    commands = [[str(tok).replace(str(old), str(out)).replace(str(root/'runtime/coupled_backend.cpp'), str(patched))
                 for tok in cmd] for cmd in receipt['commands']]
    popnet = next(Path(row['path']) for row in receipt['inputs'] if row['path'].endswith('/SString.cc.o')).parents[2]
    (out / 'COMMANDS.json').write_text(json.dumps(commands, indent=2) + '\n')
    for index, cmd in enumerate(commands):
        with (out / f'build_{index}.log').open('w') as log:
            subprocess.run(cmd, cwd=popnet, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
    print(json.dumps(dict(status='BUILT', binary=str(out/'coupled_backend'), sha256=sha(out/'coupled_backend'))), flush=True)


if __name__ == '__main__':
    main(*(Path(arg).resolve() for arg in sys.argv[1:]))
