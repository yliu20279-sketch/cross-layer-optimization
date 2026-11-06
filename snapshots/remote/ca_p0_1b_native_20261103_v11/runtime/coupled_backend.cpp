// One live state for numerical SRAM primitives, external DRAM and PopNet.
// Host software/PCIe costs are explicitly not certified by this candidate.
#include <ramulator/base/config.h>
#include <ramulator/base/factory.h>
#include <ramulator/base/request.h>
#include <ramulator/frontend/i_frontend.h>
#include <ramulator/memory_system/i_memory_system.h>
#include "configuration.h"
#include "sim_foundation.h"
#include "mess_queue.h"
#include "SRGen.h"
#include "npusim_runtime.h"
#include "live_controls.h"
#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <unistd.h>
#include <vector>

static std::function<void(size_t,double)> on_packet;
void coupled_packet_complete(size_t id,double time){if(!on_packet)throw std::runtime_error("packet callback missing");on_packet(id,time);}
using U=unsigned long long;
static void need(bool ok,const char*why){if(!ok)throw std::runtime_error(why);}
static uint64_t digest64(const unsigned char*p,U n){uint64_t h=1469598103934665603ull;for(U i=0;i<n;++i){h^=p[i];h*=1099511628211ull;}return h;}
struct Object{int rank;U address,valid,reserved,generation,role;std::vector<U>frames;};

class CoupledState {
public:
    static constexpr U capacity=512ull*1024*1024;
    std::array<Ramulator::IFrontEnd*,16>fronts;
    std::array<Ramulator::IMemorySystem*,16>memories;
    std::map<U,Object>objects;
    std::map<U,U>kv_owner;
    std::array<std::map<U,U>,16>allocations;
    std::array<std::map<U,std::array<unsigned char,4096>>,16>physical;
    std::array<std::map<U,U>,16>physical_owner;
    std::array<U,16>peak{};
    U cycle=0,next_object=1,txid=0,callbacks=0,packetid=0,packets_done=0,jobs=0,primitive_events=0,last_logged_job=0;
    U mapping_generation=0,migration_bytes=0,mapping_installs=0;
    double nextdram=1.25,tck=1.25;
    mess_queue& queue;sim_foundation& network;configuration&config;
    p0live::LinkController link;
    bool controls;
    std::string out;
    std::ofstream trace,life,program,mappings;
    std::map<size_t,U>network_pending;
    CoupledState(mess_queue&q,sim_foundation&n,configuration&c,const std::string&ram,const std::string&dir,bool ctl)
       :queue(q),network(n),config(c),link(10,3),controls(ctl),out(dir),
        trace(dir+"/LIVE_EVENTS.csv"),life(dir+"/LIFETIMES.csv"),program(dir+"/PRIMITIVES.csv"),mappings(dir+"/MAPPING_EVENTS.jsonl") {
        trace<<std::setprecision(17)<<"event,time,id,rank,address,bytes,write,object,generation,payload_fnv64,logical_offset,migration\n";
        life<<"event,time,object,rank,address,valid,reserved,generation\n";
        program<<"job,rank,kind,ops,start,complete\n";
        for(int p=0;p<16;++p){auto cfg=Ramulator::Config::parse_config_file(ram);
            fronts[p]=Ramulator::Factory::create_frontend(cfg);memories[p]=Ramulator::Factory::create_memory_system(cfg);
            fronts[p]->connect_memory_system(memories[p]);memories[p]->connect_frontend(fronts[p]);
            need(memories[p]->get_tx_bytes()==256,"candidate architecture expects full 256-byte backend");
            need(std::abs(memories[p]->get_tCK()-tck)<1e-9,"DRAM clock differs");}
        on_packet=[this](size_t id,double t){auto it=network_pending.find(id);need(it!=network_pending.end(),"unknown/double packet callback");
            if(controls)link.callback(it->second,t);network_pending.erase(it);++packets_done;
            trace<<"NOC_DONE,"<<t<<','<<id<<",-1,0,0,0,0,0,0\n";};
    }
    void tick(){
        need(cycle<10000000000ull,"target clock watchdog");
        queue.coupled_advance(double(cycle));
        while(nextdram<=double(cycle)+1e-8){for(int p=0;p<16;++p)memories[p]->tick();nextdram+=tck;}
        if(!network_pending.empty()||queue.message_queue_size())for(auto&r:network.inter_network())r.router_sim_pwr(1.0);
        ++cycle;
    }
    void until(U target){while(cycle<target)tick();}
    U alloc(int rank,U bytes,U role=0){
        need(rank>=0&&rank<16&&bytes&&bytes<=capacity&&role<=2,"invalid allocation/role");
        U extent=(bytes+4095)/4096*4096,address=0;
        // Fixed workspaces need a free identity range in BOTH virtual and
        // physical domains, including after a movable weight has been freed.
        while(address<=capacity-extent){bool available=true;U next=address+4096;
            for(auto&row:allocations[rank])if(std::max(address,row.first)<std::min(address+extent,row.first+row.second)){
                available=false;next=std::max(next,row.first+row.second);break;}
            if(available)for(U page=address/4096;page<(address+extent)/4096;++page)if(physical_owner[rank].count(page)){
                available=false;next=(page+1)*4096;break;}
            if(available)break;address=next;
        }
        need(address<=capacity-extent,"HB capacity exhausted");U id=next_object++;
        need(allocations[rank].emplace(address,extent).second,"live allocation alias");
        std::vector<U>frames;
        for(U page=address/4096;page<(address+extent)/4096;++page){
            need(physical_owner[rank].emplace(page,id).second,"physical allocation alias");
            need(physical[rank].emplace(page,std::array<unsigned char,4096>{}).second,"physical page not free");frames.push_back(page);}
        objects.emplace(id,Object{rank,address,bytes,extent,id,role,std::move(frames)});
        U live=0;for(auto&p:allocations[rank])live+=p.second;peak[rank]=std::max(peak[rank],live);
        life<<"allocate,"<<cycle<<','<<id<<','<<rank<<','<<address<<','<<bytes<<','<<extent<<','<<id<<'\n';return id;
    }
    Object& object(U id){auto it=objects.find(id);need(it!=objects.end(),"unknown/stale allocation handle");return it->second;}
    void release(U id){auto&o=object(id);life<<"release,"<<cycle<<','<<id<<','<<o.rank<<','<<o.address<<','<<o.valid<<','<<o.reserved<<','<<o.generation<<'\n';
        for(U page:o.frames){need(physical_owner[o.rank].at(page)==id,"physical ownership changed");physical_owner[o.rank].erase(page);physical[o.rank].erase(page);}
        need(allocations[o.rank].erase(o.address)==1,"allocator release mismatch");objects.erase(id);}
    void access(U id,U offset,void*buffer,U bytes,bool write,U override_frame=~U(0),bool migration=false){
        auto&o=object(id);U bound=migration?o.reserved:o.valid;
        need(bytes&&offset<=bound&&bytes<=bound-offset,"actual operand exceeds live extent");
        // SRAM accesses may have advanced the shared clock by reference. Catch
        // the memory/network engines up BEFORE admitting the next transaction.
        queue.coupled_advance(double(cycle));
        while(nextdram<=double(cycle)+1e-8){for(int p=0;p<16;++p)memories[p]->tick();nextdram+=tck;}
        U issued=0,completed=0,outstanding=0;int rank=o.rank;
        while(issued<bytes||outstanding){
            while(issued<bytes&&outstanding<16){U logical=offset+issued;
                U frame=override_frame==~U(0)?o.frames.at(logical/4096):override_frame;
                U a=frame*4096+logical%4096;
                need(physical[rank].count(frame),"physical frame absent");
                if(!migration)need(physical_owner[rank].at(frame)==id,"model read mapped to another owner");
                U n=std::min({U(256),bytes-issued,U(4096-a%4096)}),local=issued,serial=txid;
                U value=write?digest64((unsigned char*)buffer+local,n):0;
                auto cb=[&,local,n,serial,value,a,migration](Ramulator::Request&){
                    auto*actual=physical[rank].at(a/4096).data()+a%4096;
                    if(write)std::memcpy(actual,(unsigned char*)buffer+local,n);
                    else std::memcpy((unsigned char*)buffer+local,actual,n);
                    U hash=write?value:digest64((unsigned char*)buffer+local,n);
                    trace<<"DRAM_DONE,"<<nextdram<<','<<serial<<','<<rank<<','<<a<<','<<n<<','<<write<<','<<id<<','<<o.generation<<','<<hash<<','<<offset+local<<','<<migration<<'\n';
                    --outstanding;completed+=n;++callbacks;
                };
                bool accepted=fronts[rank]->receive_external_requests(write?Ramulator::Request::Type::Write:Ramulator::Request::Type::Read,
                     a,0,int(id%2147483647),cb,int(n));
                if(!accepted)break;
                trace<<"DRAM_ISSUE,"<<cycle<<','<<serial<<','<<rank<<','<<a<<','<<n<<','<<write<<','<<id<<','<<o.generation<<','<<value<<','<<offset+local<<','<<migration<<'\n';
                ++txid;++outstanding;issued+=n;
            }
            tick();
        }
        need(completed==bytes,"missing payload callback bytes");
    }
    void paired_kv_reads(U a,U ar,U b,U br,unsigned char* output){
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
                log<<"complete,"<<nextdram<<','<<request<<','<<id<<','<<serial<<'\n';
            };
            need(fronts[rank]->receive_external_requests(Ramulator::Request::Type::Read,address,0,
                    int(id%2147483647),callback,256),"KV batch queue rejected request");
            ++txid;
            log<<"issue,"<<cycle<<','<<request<<','<<id<<','<<serial<<'\n';
        }
        while(done!=2)tick();
    }
    // Primitive accesses are made by the actual SramMatrix numerical loop.
    void absolute(int rank,U address,void*buffer,U bytes,bool write){
        for(auto&row:objects){auto&o=row.second;if(o.rank==rank&&address>=o.address&&address-o.address<=o.valid&&bytes<=o.valid-(address-o.address)){
            access(row.first,address-o.address,buffer,bytes,write);return;}}
        need(false,"primitive referenced an unallocated HB span");
    }
    void transfer(U from,U to,U bytes){
        auto&s=object(from);auto&d=object(to);need(s.rank!=d.rank&&bytes&&bytes<=s.valid&&bytes<=d.valid,"invalid transfer extent");
        bool local=std::abs(s.rank%4-d.rank%4)+std::abs(s.rank/4-d.rank/4)==1;
        std::vector<unsigned char> staging(65536);
        for(U off=0;off<bytes;off+=staging.size()){
            U n=std::min(U(staging.size()),bytes-off);access(from,off,staging.data(),n,false);
            U remaining=(n+config.flit_size()*8-1)/(config.flit_size()*8);
            if(controls)link.select(local?remaining:0,local?0:remaining,cycle);
            while(remaining||!network_pending.empty()){
                queue.coupled_advance(double(cycle));
                while(remaining){U flitbytes=config.flit_size()*8;
                    need(flitbytes&&(!controls||flitbytes<=512),"invalid packet occupancy");
                    U count=std::min(remaining,controls?std::min(U(32),512/flitbytes):U(32));
                    if(controls&&!link.can_issue(local,count*flitbytes,cycle))break;
                    U token=controls?link.accept(local,count*flitbytes,cycle):0,id=packetid++;
                    network_pending[id]=token;
                    add_type src={s.rank%4,s.rank/4},dst={d.rank%4,d.rank/4};SPacket p;
                    p.startTime=cycle;p.sourceAddress=src;p.destinationAddress=dst;p.packetSize=count;p.id=id;
                    network.router(src).inputTrace(p);network.router(src).receive_packet();
                    trace<<"NOC_ISSUE,"<<cycle<<','<<id<<','<<s.rank<<",0,"<<count*flitbytes<<",0,"<<from<<','<<s.generation<<','<<digest64(staging.data(),n)<<",0,0\n";
                    remaining-=count;
                }
                tick();
            }
            access(to,off,staging.data(),n,true);
        }
    }
    std::vector<U> layout(){std::vector<U>rows;
        for(auto&entry:objects){auto&o=entry.second;if(o.role!=1)continue;
            for(U p=0;p<o.frames.size();++p){rows.push_back(entry.first);rows.push_back(p);rows.push_back(o.frames[p]);rows.push_back(o.rank);}}
        return rows;
    }
    void install(const std::vector<U>&rows,U budget_percent){
        need(!network_pending.size()&&txid==callbacks,"map install before drain");
        need(budget_percent>0&&budget_percent<=10&&rows.size()%3==0,"invalid mapping/budget");
        using Key=std::pair<U,U>;std::map<Key,U>candidate;
        for(U i=0;i<rows.size();i+=3)need(candidate.emplace(Key{rows[i],rows[i+1]},rows[i+2]).second,"duplicate mapping key");
        std::map<int,std::set<U>>old_pool,new_pool;U pages=0,total=0,changed=0;
        std::map<std::pair<int,U>,Key>owners;std::map<std::pair<int,U>,U>permutation;
        for(auto&entry:objects){auto&o=entry.second;if(o.role!=1)continue;total+=o.valid;
            for(U p=0;p<o.frames.size();++p){++pages;Key key{entry.first,p};auto it=candidate.find(key);
                need(it!=candidate.end(),"missing movable weight page");U dest=it->second;
                need(dest<capacity/4096,"destination frame exceeds capacity");
                old_pool[o.rank].insert(o.frames[p]);need(new_pool[o.rank].insert(dest).second,"mapping physical alias");
                owners[{o.rank,o.frames[p]}]=key;permutation[{o.rank,o.frames[p]}]=dest;
                if(dest!=o.frames[p])changed+=std::min(U(4096),o.valid-p*4096);
            }}
        need(pages&&candidate.size()==pages,"fixed object/domain changed");
        need(old_pool==new_pool,"partition weight frame pool changed");
        need(changed<=total*budget_percent/100,"mapping exceeds effective-weight budget");
        U start=cycle;std::set<std::pair<int,U>>visited;
        std::array<unsigned char,4096>carry,temp;
        // Actual cycle rotation: two 4KiB SRAM buffers; no full-image oracle
        // or hidden host copy is substituted for modeled reads and writes.
        for(auto&row:permutation){auto origin=row.first;if(visited.count(origin)||row.second==origin.second)continue;
            int rank=origin.first;U current=origin.second;Key held=owners.at(origin);
            access(held.first,held.second*4096,carry.data(),4096,false,current,true);until(cycle+16);
            while(true){visited.insert({rank,current});U next=permutation.at({rank,current});
                if(next==origin.second){access(held.first,held.second*4096,carry.data(),4096,true,next,true);until(cycle+16);migration_bytes+=4096;break;}
                Key displaced=owners.at({rank,next});
                access(displaced.first,displaced.second*4096,temp.data(),4096,false,next,true);until(cycle+16);
                access(held.first,held.second*4096,carry.data(),4096,true,next,true);until(cycle+16);migration_bytes+=4096;
                carry.swap(temp);current=next;held=displaced;
            }
        }
        for(auto&entry:candidate){auto&o=object(entry.first.first);o.frames[entry.first.second]=entry.second;physical_owner[o.rank][entry.second]=entry.first.first;}
        ++mapping_generation;++mapping_installs;
        mappings<<"{\"generation\":"<<mapping_generation<<",\"start\":"<<start<<",\"complete\":"<<cycle<<",\"changed_valid_bytes\":"<<changed
                <<",\"total_valid_weight_bytes\":"<<total<<",\"migration_SRAM_bytes\":8192,\"cpu_cost_verified\":false}\n";mappings.flush();
    }
    void finish(){
        need(network_pending.empty()&&txid==callbacks&&objects.empty(),"live state at finish");
        for(int p=0;p<16;++p)need(physical[p].empty()&&physical_owner[p].empty()&&allocations[p].empty(),"physical page or allocator leak");
        trace.flush();life.flush();program.flush();mappings.flush();
        std::ofstream f(out+"/BACKEND_SUMMARY.json");
        f<<"{\"status\":\"PASS_LIVE_COUPLED_SUBGRAPH_ONLY\",\"clock_ns\":"<<cycle
         <<",\"transactions\":"<<txid<<",\"callbacks\":"<<callbacks<<",\"packets\":"<<packetid
         <<",\"packet_callbacks\":"<<packets_done<<",\"jobs\":"<<jobs<<",\"primitive_events\":"<<primitive_events
         <<",\"link_switches\":"<<link.switches<<",\"mapping_installs\":"<<mapping_installs<<",\"migration_write_bytes\":"<<migration_bytes
         <<",\"primitive_trace_sampling_interval\":10000,\"cpu_pcie_costs_verified\":false,\"formal_performance\":false,\"HB_peak_reserved\":[";
        for(int p=0;p<16;++p){if(p)f<<',';f<<peak[p];}f<<"]}\n";
    }
};

struct Runtime {
    CoupledState&s;int rank;NPUSim::NPUConfig config;
    Runtime(CoupledState&state,int r):s(state),rank(r){
        config.intra_delay_enable=false;config.vector_ops_per_cycle=16;config.reduce_ops_per_cycle=16;
        config.sram_bandwidth_bytes_per_cycle=256;config.mac_unit_count=4096;config.sram_per_mac_bytes=1024;
    }
    U& chipCycle(){return s.cycle;}
    void load(U address,void*data,U bytes,const char*){s.absolute(rank,address,data,bytes,false);}
    void store(U address,const void*data,U bytes,const char*){s.absolute(rank,address,const_cast<void*>(data),bytes,true);}
    auto scheduleProgram(const std::vector<NPUSim::NpuProgramEvent>& events){
        auto result=NPUSim::scheduleNpuProgramEvents(events,config,s.cycle);
        for(const auto&e:result.entries){
            if(s.last_logged_job!=s.jobs||s.primitive_events%10000==0){
                s.program<<s.jobs<<','<<rank<<','<<int(e.event.kind)<<','<<e.event.ops<<','<<e.start_cycle<<','<<e.complete_cycle<<'\n';s.last_logged_job=s.jobs;}
            ++s.primitive_events;
        }
        s.until(result.overall_finish_cycle);return result;
    }
};
#include "coupled_matrix.h"

static void io_exact(int fd,void*buffer,size_t n,bool write_request){
    char*p=(char*)buffer;while(n){auto done=write_request ? ::write(fd,p,n) : ::read(fd,p,n);
        if(done<=0)throw std::runtime_error("host RPC pipe closed/short");p+=done;n-=done;}
}
int main(int argc,char**argv){try{
    need(argc==4,"usage backend out ram_config control");std::string out=argv[1],ram=argv[2];
    int response=dup(STDOUT_FILENO);need(response>=0,"RPC descriptor duplication failed");
    need(std::freopen((out+"/backend.stdout").c_str(),"w",stdout),"stdout redirect failed");
    std::vector<std::string>args={"coupled","-A","4","-c","2","-V","2","-B","12","-O","12","-F","4","-L","1000","-T","1000000000","-r","1","-I",out+"/empty.trace","-R","0"};
    std::vector<char*>av;for(auto&a:args)av.push_back(a.data());
    SRGen rng;configuration config(av.size(),av.data());mess_queue queue(0);sim_foundation network;
    CoupledState state(queue,network,config,ram,out,std::string(argv[3])=="project_dynamic");
    U hello[8]={0x5035434f55504c45ull,0};io_exact(response,hello,sizeof(hello),true);
    while(true){U h[8],answer[8]={0x5035434f55504c45ull,0};io_exact(STDIN_FILENO,h,sizeof(h),false);
        try{
            if(h[0]==12){
                need(h[3]&&h[3]<=(1ull<<32),"invalid request identity");
                answer[2]=state.alloc(int(h[1]),h[2]);
                state.kv_owner.emplace(answer[2],h[3]);
            }else if(h[0]==13){
                std::array<unsigned char,512> bytes{};
                state.paired_kv_reads(h[1],h[2],h[3],h[4],bytes.data());
                answer[2]=state.cycle;answer[3]=bytes.size();answer[7]=state.cycle;
                io_exact(response,answer,sizeof(answer),true);
                io_exact(response,bytes.data(),bytes.size(),true);continue;
            }else if(h[0]==1)answer[2]=state.alloc(int(h[1]),h[2],h[3]);
            else if(h[0]==2||h[0]==3){
                need(h[3]&&h[3]<=128ull*1024*1024,"host transfer bound");std::vector<unsigned char>data(h[3]);
                if(h[0]==2)io_exact(STDIN_FILENO,data.data(),data.size(),false);
                auto owner=state.kv_owner.find(h[1]);
                if(owner!=state.kv_owner.end()&&owner->second!=h[4]){
                    std::ofstream denied(out+"/KV_DENIED.csv",std::ios::app);
                    denied<<h[0]<<','<<h[4]<<','<<h[1]<<','<<state.txid<<','<<state.cycle<<'\n';
                    answer[3]=0;answer[7]=state.cycle;
                    io_exact(response,answer,sizeof(answer),true);continue;
                }
                state.access(h[1],h[2],data.data(),h[3],h[0]==2);
                answer[2]=state.cycle;answer[3]=data.size();io_exact(response,answer,sizeof(answer),true);
                if(h[0]==3)io_exact(response,data.data(),data.size(),true);continue;
            }else if(h[0]==4){
                auto owner=state.kv_owner.find(h[1]);
                if(owner!=state.kv_owner.end()&&owner->second!=h[2]){
                    std::ofstream denied(out+"/KV_DENIED.csv",std::ios::app);
                    denied<<h[0]<<','<<h[2]<<','<<h[1]<<','<<state.txid<<','<<state.cycle<<'\n';
                    answer[7]=state.cycle;io_exact(response,answer,sizeof(answer),true);continue;
                }
                state.release(h[1]);state.kv_owner.erase(h[1]);answer[3]=1;
            }
            else if(h[0]==5||h[0]==6){
                auto&a=state.object(h[1]);auto&b=state.object(h[2]);auto&c=state.object(h[3]);
                need(a.rank==b.rank&&a.rank==c.rank,"primitive spans mixed partitions");
                Runtime runtime(state,a.rank);SramMatrix<Runtime> kernel(runtime);++state.jobs;
                if(h[0]==5){need(h[4]>=1&&h[4]<=19&&h[5]>=1&&h[5]<=4096&&h[6]>=1&&h[6]<=4096,"matrix geometry outside reviewed primitive");
                    need(h[7]<=1,"unknown matrix precision contract");
                    if(h[7])kernel.run_fp16(a.address,b.address,c.address,h[4],h[5],h[6],state.jobs,out.c_str());
                    else kernel.run(a.address,b.address,c.address,h[4],h[5],h[6],state.jobs,out.c_str());}
                else {need(h[5]<=1,"invalid vector kind");kernel.binary(a.address,b.address,c.address,h[4],h[5],state.jobs,out.c_str());}
            }else if(h[0]==7)state.transfer(h[1],h[2],h[3]);
            else if(h[0]==8){answer[2]=state.cycle;state.finish();io_exact(response,answer,sizeof(answer),true);break;}
            else if(h[0]==9){auto&o=state.object(h[1]);answer[2]=o.rank;answer[3]=o.address;answer[4]=o.valid;answer[5]=o.generation;}
            else if(h[0]==10){need(h[3]==state.mapping_generation,"stale mapping generation");need(h[1]&&h[1]<=16*131072,"mapping row count outside finite pools");
                std::vector<U>rows(h[1]*3);io_exact(STDIN_FILENO,rows.data(),rows.size()*sizeof(U),false);state.install(rows,h[2]);}
            else if(h[0]==11){auto rows=state.layout();answer[2]=rows.size()/4;answer[3]=rows.size()*sizeof(U);answer[4]=state.mapping_generation;answer[7]=state.cycle;
                io_exact(response,answer,sizeof(answer),true);if(!rows.empty())io_exact(response,rows.data(),rows.size()*sizeof(U),true);continue;}
            else throw std::runtime_error("unknown live RPC opcode");
            if(h[0]!=9)answer[2]=(h[0]==1||h[0]==12)?answer[2]:state.cycle;
            answer[7]=state.cycle;io_exact(response,answer,sizeof(answer),true);
        }catch(const std::exception&e){std::string message=e.what();answer[1]=1;answer[2]=message.size();
            io_exact(response,answer,sizeof(answer),true);io_exact(response,message.data(),message.size(),true);
            throw;
        }
    }
    return 0;
}catch(const std::exception&e){std::cerr<<"FAILED "<<e.what()<<'\n';return 2;}}
