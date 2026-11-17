"""Build the shared 8-endpoint native concurrency calibration backend."""

import json
from pathlib import Path
import subprocess
import sys

from build_opp_backend import replace, sha


POLICY = r"""
    U wave_mode=0, wave_local_budget=1536, wave_global_budget=1536;
    U wave_budget_tick=~U(0), wave_local_used=0, wave_global_used=0;
    static bool local_wave(int src,int dst){return src/4==dst/4;}
    void bind_wave_budget(const std::vector<U>& rows){
        U local=0,global=0;
        for(size_t i=0;i<rows.size();i+=5){
            auto s=object(rows[i]).rank,d=object(rows[i+1]).rank;
            (local_wave(s,d)?local:global)+=rows[i+2];
        }
        if(wave_mode!=1){wave_local_budget=wave_global_budget=1536;return;}
        need(wave_mode==1,"invalid HiBand mode");
        if(!global)wave_local_budget=1536;
        else if(!local)wave_local_budget=0;
        else wave_local_budget=(5*local>=3*(local+global))?1024:512;
        wave_global_budget=1536-wave_local_budget;
    }
    bool admit_wave_packet(int s,int d,U count){
        if(wave_budget_tick!=cycle){
            wave_budget_tick=cycle;
            wave_local_used=wave_global_used=0;
        }
        bool local=local_wave(s,d);
        U& used=local?wave_local_used:wave_global_used;
        const U cap=local?wave_local_budget:wave_global_budget;
        U bytes=count*32;
        need(bytes<=cap,"packet exceeds admitted class share");
        if(used+bytes>cap||wave_local_used+wave_global_used+bytes>1536)return false;
        used+=bytes;
        return true;
    }
"""


def main(root, out, transfer):
    out.mkdir()
    approved = json.loads((root/'evidence/COUPLED_BUILD_04.json').read_text())
    for name in ('coupled_backend.cpp','coupled_matrix.h'):
        assert sha(root/'runtime'/name)==approved['source_sha256'][name]
    for entry in approved['inputs']:
        assert sha(entry['path'])==entry['sha256']
    src = (root/'runtime/coupled_backend.cpp').read_text()
    src = replace(src,'    std::map<size_t,U>network_pending;',
                  '    std::map<size_t,U>network_pending;\n'+POLICY+transfer.read_text())
    src = replace(src,'on_packet=[this](size_t id,double t){auto it=',
                  'on_packet=[this](size_t id,double t){complete_wave_packet(id,t);auto it=')
    src = replace(src,'trace(dir+"/LIVE_EVENTS.csv")','trace("/dev/null")')
    src = replace(src,'need(cycle<10000000000ull,"target clock watchdog");',
                  'need(cycle<100000000000ull,"target clock watchdog");')
    src = replace(src,'            if(h[0]==12){',r'''            if(h[0]==17){
                need(h[1]<=2&&state.cycle==0&&!state.controls,"late wave policy");
                state.wave_mode=h[1];
            }else if(h[0]==18){
                need(h[1]>0&&h[1]<=512&&config.flit_size()*8==32,"wave descriptor count or flit width");
                std::vector<U> rows(h[1]*5);
                io_exact(STDIN_FILENO,rows.data(),rows.size()*sizeof(U),false);
                state.bind_wave_budget(rows);
                auto stamps=state.wave(rows);
                answer[2]=state.wave_local_budget;answer[3]=state.wave_global_budget;
                answer[7]=state.cycle;
                io_exact(response,answer,sizeof(answer),true);
                io_exact(response,stamps.data(),stamps.size()*sizeof(U),true);continue;
            }else if(h[0]==12){''')
    cpp = out/'coupled_backend.cpp'
    cpp.write_text(src)
    old = root/'build_04'
    commands = [[str(arg).replace(str(old),str(out)).replace(str(root/'runtime/coupled_backend.cpp'),str(cpp))
                 for arg in command] for command in approved['commands']]
    popnet = next(Path(row['path']) for row in approved['inputs'] if row['path'].endswith('/SString.cc.o')).parents[2]
    (out/'COMMANDS.json').write_text(json.dumps(commands,indent=2)+'\n')
    for i,command in enumerate(commands):
        with (out/f'build_{i}.log').open('w') as log:
            subprocess.run(command,cwd=popnet,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
    print(json.dumps(dict(binary=str(out/'coupled_backend'),sha256=sha(out/'coupled_backend'))))


if __name__=='__main__':
    main(*(Path(arg).resolve() for arg in sys.argv[1:]))
