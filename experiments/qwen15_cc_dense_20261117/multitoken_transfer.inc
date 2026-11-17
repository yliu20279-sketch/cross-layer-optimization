    // One ready set shares the physical mesh, endpoint queues and target clock.
    struct WaveFlow {
        U src, dst, bytes, circuit, hops, sent=0, start=0, finish=0, wire_start=~U(0), wire_done=0;
        unsigned packets=0, stage=0;
        U issued=0, completed=0;
        unsigned dram_pending=0;
        std::vector<unsigned char> payload;
        WaveFlow(U s,U d,U b,U c,U h) :src(s),dst(d),bytes(b),circuit(c),hops(h),payload(b) {}
    };
    std::map<size_t,WaveFlow*> wave_packets;
    std::array<unsigned,16> wave_dram_pending{};
    bool complete_wave_packet(size_t id,double time){
        auto it=wave_packets.find(id);
        if(it==wave_packets.end())return false;
        auto& f=*it->second;
        need(f.packets>0,"duplicate wave packet callback");
        --f.packets;
        f.wire_done=std::max(f.wire_done,U(std::ceil(time)));
        wave_packets.erase(it);
        return true;
    }
    void wave_memory(WaveFlow& f){
        bool write=f.stage==2;
        U handle=write?f.dst:f.src;
        auto& obj=object(handle);
        int rank=obj.rank;
        if(f.issued==f.bytes||wave_dram_pending[rank]>=16)return;
        U offset=f.issued;
        U frame=obj.frames.at(offset/4096);
        need(physical_owner[rank].at(frame)==handle,"wave endpoint ownership");
        U address=frame*4096+offset%4096, bytes=std::min(U(32),f.bytes-offset);
        auto complete=[this,&f,rank,frame,address,offset,bytes,write](Ramulator::Request&){
            auto* dram=physical[rank].at(frame).data()+address%4096;
            auto* data=f.payload.data()+offset;
            if(write)std::memcpy(dram,data,bytes);
            else std::memcpy(data,dram,bytes);
            f.completed+=bytes;
            --f.dram_pending;
            --wave_dram_pending[rank];
            ++callbacks;
        };
        if(fronts[rank]->receive_external_requests(
               write?Ramulator::Request::Type::Write:Ramulator::Request::Type::Read,
               address,0,int(handle%2147483647),complete,int(bytes))){
            f.issued+=bytes;
            ++f.dram_pending;
            ++wave_dram_pending[rank];
            ++txid;
        }
    }
    std::vector<U> wave(const std::vector<U>& descriptor){
        need(descriptor.size()%5==0&&!descriptor.empty()&&!controls&&wave_packets.empty()&&network_pending.empty(),
             "invalid concurrent transfer");
        std::vector<WaveFlow> flows;
        flows.reserve(descriptor.size()/5);
        std::map<U,std::array<U,3>> circuit_geometry;
        for(size_t i=0;i<descriptor.size();i+=5){
            U s=descriptor[i],d=descriptor[i+1],bytes=descriptor[i+2];
            U c=descriptor[i+3],h=descriptor[i+4];
            const auto& src=object(s);
            const auto& dst=object(d);
            need(src.rank>=0&&src.rank<8&&dst.rank>=0&&dst.rank<8&&src.rank!=dst.rank&&
                 bytes&&bytes<=src.valid&&bytes<=dst.valid&&bytes<=65536,"concurrent tensor span");
            if(c){
                need(wave_mode==2&&c<=2&&h>0&&h<=13,"invalid model circuit");
                std::array<U,3> geometry{U(src.rank),U(dst.rank),h};
                need(circuit_geometry.emplace(c,geometry).first->second==geometry,"circuit destination changed");
            }else need(h==0,"Mesh flow with circuit length");
            flows.emplace_back(s,d,bytes,c,h);
            flows.back().start=cycle;
        }
        U closed=0, first=0, deadline=cycle+2000000;
        const U config_ready=cycle+40;
        std::array<U,3> circuit_next{0,config_ready,config_ready};
        std::multimap<U,WaveFlow*> circuit_callbacks;
        while(closed<flows.size()){
            if(cycle>=deadline){
                std::cerr<<"concurrent transfer at "<<cycle<<" closed "<<closed<<" packet_wait "<<wave_packets.size()<<'\n';
                for(const auto& f:flows)if(f.stage!=3)
                    std::cerr<<object(f.src).rank<<'>'<<object(f.dst).rank<<" stage "<<f.stage
                             <<" issued "<<f.issued<<" completed "<<f.completed<<" dram "<<f.dram_pending
                             <<" sent "<<f.sent<<" packets "<<f.packets<<" wire_done "<<f.wire_done<<'\n';
                need(false,"concurrent transfer watchdog");
            }
            // PopNet compares each message's start time with its own clock in
            // receive_packet(). Match the existing single-transfer RPC.
            queue.coupled_advance(double(cycle));
            while(!circuit_callbacks.empty()&&circuit_callbacks.begin()->first<=cycle){
                auto entry=circuit_callbacks.begin();
                auto& f=*entry->second;
                need(f.packets>0,"duplicate modeled circuit callback");
                --f.packets;
                ++packets_done;
                f.wire_done=entry->first;
                circuit_callbacks.erase(entry);
            }
            std::array<bool,16> issued_source{};
            for(size_t index=0;index<flows.size();++index){
                auto& f=flows[(first+index)%flows.size()];
                if(f.stage==0&&f.completed==f.bytes){
                    f.stage=1;
                    f.completed=f.issued=0;
                }
                if(f.stage==1&&f.sent>=f.bytes&&!f.packets&&cycle>=f.wire_done)f.stage=2;
                if(f.stage==2&&f.completed==f.bytes){
                    f.stage=3;
                    f.finish=cycle;
                    ++closed;
                }
                if(f.stage==0||f.stage==2)wave_memory(f);
                if(f.stage!=1||f.sent>=f.bytes)continue;
                int s=object(f.src).rank,d=object(f.dst).rank;
                if(issued_source[s])continue;
                if(f.circuit&&cycle<circuit_next[f.circuit])continue;
                U quota=(local_wave(s,d)?wave_local_budget:wave_global_budget)/32;
                // Compare the policies at a common 512-byte packet size.
                U count=std::min({U(16),(f.bytes-f.sent+31)/32,quota});
                need(count>0,"active transfer class has no grant");
                if(!admit_wave_packet(s,d,count))continue;
                U id=packetid++;
                ++f.packets;
                if(f.sent==0)f.wire_start=cycle;
                f.sent+=count*32;
                issued_source[s]=true;
                if(f.circuit){
                    // Capacity and hop pipeline follow the CS RTL timing
                    // abstraction. Endpoint access still uses real Ramulator.
                    circuit_next[f.circuit]=cycle+count;
                    circuit_callbacks.emplace(cycle+count+f.hops,&f);
                    continue;
                }
                need(network_pending.emplace(id,0).second&&wave_packets.emplace(id,&f).second,"duplicate wave packet id");
                add_type src={s%4,s/4},dst={d%4,d/4};
                SPacket p;
                p.startTime=cycle;
                p.sourceAddress=src;
                p.destinationAddress=dst;
                p.packetSize=count;
                p.id=id;
                network.router(src).inputTrace(p);
                network.router(src).receive_packet();
            }
            ++first;
            if(closed<flows.size())tick();
        }
        need(wave_packets.empty()&&network_pending.empty()&&circuit_callbacks.empty()&&txid==callbacks,"wave final drain");
        std::vector<U> stamps;
        for(auto& f:flows){
            need(!f.dram_pending&&!f.packets&&f.finish>f.start&&f.wire_done>f.start,"incomplete wave tensor");
            need(f.start<=f.wire_start&&f.wire_start<f.wire_done,"wave injection timing");
            stamps.insert(stamps.end(),{f.start,f.wire_start,f.wire_done,f.finish});
        }
        return stamps;
    }
