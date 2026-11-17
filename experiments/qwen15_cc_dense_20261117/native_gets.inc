    struct GetS {
        U arrival, address;
        U request_inject=0, request_done=0, read_done=0, reply_inject=0, reply_done=0;
        unsigned submitted=0, acknowledged=0;
        bool request_received=false;
    };
    std::vector<GetS> gets;
    size_t next_gets=0, complete_gets=0;
    U gets_start=0;
    std::map<size_t,std::pair<size_t,bool>> gets_packets;
    std::vector<size_t> gets_reads, gets_replies;
    size_t gets_read_head=0, gets_reply_head=0;

    void arm_gets(U count, U dispatch_offset){
        need(gets.empty()&&(count==256||count==512)&&dispatch_offset==32,"unexpected GetS fixture");
        std::ifstream file(out+"/GETS.stim");
        U release=0,address=0;
        while(file>>release>>address){
            need(release==(512/count)*gets.size()&&address==0x10000000ull+64*gets.size(),"GetS fixture changed");
            gets.push_back({release,address});
        }
        need(file.eof()&&gets.size()==count,"missing GetS arrivals");
        gets_start=cycle;
        until(gets_start+dispatch_offset);
    }

    U send_gets_packet(size_t index,bool response){
        const int source=response?1:0, destination=response?0:1;
        const U id=packetid++;
        need(gets_packets.emplace(id,std::make_pair(index,response)).second,"GetS packet reused");
        add_type src={source,0}, dst={destination,0};
        SPacket packet;
        packet.startTime=cycle;
        packet.sourceAddress=src;
        packet.destinationAddress=dst;
        packet.packetSize=response?2:1;
        packet.id=id;
        network.router(src).inputTrace(packet);
        network.router(src).receive_packet();
        return cycle;
    }

    bool receive_gets_packet(size_t id,double when){
        auto pending=gets_packets.find(id);
        if(pending==gets_packets.end())return false;
        auto [index,response]=pending->second;
        auto& request=gets.at(index);
        const U stamp=U(std::ceil(when));
        if(response){
            need(request.acknowledged==2&&stamp>=request.reply_inject,"GetS reply order");
            request.reply_done=stamp;
            ++complete_gets;
            if(complete_gets==gets.size())write_gets();
        }else{
            need(!request.request_received&&stamp>=request.request_inject,"GetS request replay");
            request.request_received=true;
            request.request_done=stamp;
            gets_reads.push_back(index);
        }
        gets_packets.erase(pending);
        ++packets_done;
        return true;
    }

    void service_gets(){
        if(next_gets<gets.size()&&cycle>=gets_start+gets[next_gets].arrival){
            need(cycle==gets_start+gets[next_gets].arrival,"GetS external arrival drifted");
            gets[next_gets].request_inject=send_gets_packet(next_gets,false);
            ++next_gets;
        }
        if(gets_read_head<gets_reads.size()){
            const size_t index=gets_reads[gets_read_head];
            auto& request=gets[index];
            if(cycle>=request.request_done){
                auto address=request.address+32*request.submitted;
                bool accepted=fronts[1]->receive_external_requests(Ramulator::Request::Type::Read,
                    address,0,1073741824+int(index),[this,index](Ramulator::Request&){
                        ++callbacks;
                        auto& record=gets[index];
                        if(++record.acknowledged==2){
                            record.read_done=U(std::ceil(nextdram));
                            gets_replies.push_back(index);
                        }
                    },32);
                if(accepted){
                    ++txid;
                    if(++request.submitted==2)++gets_read_head;
                }
            }
        }
        if(gets_reply_head<gets_replies.size()){
            const size_t index=gets_replies[gets_reply_head];
            if(cycle>=gets[index].read_done){
                gets[index].reply_inject=send_gets_packet(index,true);
                ++gets_reply_head;
            }
        }
    }

    void drain_gets(){
        if(gets.empty())return;
        const U deadline=cycle+100000;
        while(complete_gets<gets.size()&&cycle<deadline)tick();
        if(complete_gets!=gets.size()){
            std::cerr<<"GetS state at drain cutoff "<<next_gets<<','<<gets_reads.size()<<','
                     <<gets_read_head<<','<<gets_replies.size()<<','<<gets_reply_head<<','
                     <<complete_gets<<','<<gets_packets.size()<<'\n';
            need(false,"GetS drain watchdog");
        }
        need(gets_packets.empty(),"pending GetS at end");
    }

    void write_gets(){
        std::ofstream result(out+"/GETS.csv");
        result<<"id,arrival,request_inject,request_done,read_done,reply_inject,reply_done\n";
        for(size_t i=0;i<gets.size();++i){
            const auto& r=gets[i];
            result<<i<<','<<r.arrival<<','<<r.request_inject-gets_start<<','<<r.request_done-gets_start<<','
                  <<r.read_done-gets_start<<','<<r.reply_inject-gets_start<<','<<r.reply_done-gets_start<<'\n';
        }
    }
