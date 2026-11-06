from pathlib import Path
p=Path('runtime/coupled_backend.cpp')
s=p.read_text()
s=s.replace('    std::map<U,Object>objects;','    std::map<U,Object>objects;\n    std::map<U,U>kv_owner;')
i=s.index('    // Primitive accesses')
s=s[:i]+"""    void paired_kv_reads(U a,U ar,U b,U br,unsigned char* output){
        need(ar!=br&&ar&&br&&kv_owner.at(a)==ar&&kv_owner.at(b)==br,"KV batch ownership");
        std::array<U,2> ids{a,b},requests{ar,br};
        std::ofstream log(out+"/KV_BATCH.csv",std::ios::app);
        unsigned done=0;
        for(unsigned i=0;i<2;++i){
            U id=ids[i],request=requests[i];auto&obj=object(id);
            need(obj.valid>=256,"short KV batch span");
            int rank=obj.rank; U frame=obj.frames.at(0),address=frame*4096,serial=txid;
            need(physical_owner[rank].at(frame)==id,"KV physical owner changed");
            auto callback=[&,i,request,id,rank,frame,serial](Ramulator::Request&){
                std::memcpy(output+i*256,physical[rank].at(frame).data(),256);
                ++done;++callbacks;
                log<<"complete,"<<nextdram<<','<<request<<','<<id<<','<<serial<<'\\n';
            };
            need(fronts[rank]->receive_external_requests(Ramulator::Request::Type::Read,address,0,
                    int(id%2147483647),callback,256),"KV batch queue rejected request");
            ++txid;
            log<<"issue,"<<cycle<<','<<request<<','<<id<<','<<serial<<'\\n';
        }
        while(done!=2)tick();
    }
"""+s[i:]
mark='            if(h[0]==1)answer[2]=state.alloc(int(h[1]),h[2],h[3]);'
s=s.replace(mark,'''            if(h[0]==12){
                need(h[3]&&h[3]<=(1ull<<32),"invalid request identity");
                answer[2]=state.alloc(int(h[1]),h[2]);
                state.kv_owner.emplace(answer[2],h[3]);
            }else if(h[0]==13){
                std::array<unsigned char,512> bytes{};
                state.paired_kv_reads(h[1],h[2],h[3],h[4],bytes.data());
                answer[2]=state.cycle;answer[3]=bytes.size();answer[7]=state.cycle;
                io_exact(response,answer,sizeof(answer),true);
                io_exact(response,bytes.data(),bytes.size(),true);continue;
            }else if(h[0]==1)answer[2]=state.alloc(int(h[1]),h[2],h[3]);''')
s=s.replace('                state.access(h[1],h[2],data.data(),h[3],h[0]==2);','''                auto owner=state.kv_owner.find(h[1]);
                if(owner!=state.kv_owner.end()&&owner->second!=h[4]){
                    std::ofstream denied(out+"/KV_DENIED.csv",std::ios::app);
                    denied<<h[0]<<','<<h[4]<<','<<h[1]<<','<<state.txid<<','<<state.cycle<<'\\n';
                    answer[3]=0;answer[7]=state.cycle;
                    io_exact(response,answer,sizeof(answer),true);continue;
                }
                state.access(h[1],h[2],data.data(),h[3],h[0]==2);''')
s=s.replace('}else if(h[0]==4)state.release(h[1]);','''}else if(h[0]==4){
                auto owner=state.kv_owner.find(h[1]);
                if(owner!=state.kv_owner.end()&&owner->second!=h[2]){
                    std::ofstream denied(out+"/KV_DENIED.csv",std::ios::app);
                    denied<<h[0]<<','<<h[2]<<','<<h[1]<<','<<state.txid<<','<<state.cycle<<'\\n';
                    answer[7]=state.cycle;io_exact(response,answer,sizeof(answer),true);continue;
                }
                state.release(h[1]);state.kv_owner.erase(h[1]);answer[3]=1;
            }''')
s=s.replace('h[0]==1?answer[2]:state.cycle','(h[0]==1||h[0]==12)?answer[2]:state.cycle')
p.write_text(s)
