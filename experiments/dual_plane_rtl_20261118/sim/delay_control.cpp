// Configuration/hold control: the same pending packet IDs and real sequencer
// commands as forced_cs, but selected payloads remain on M Mesh.
// Reuse the unmodified packet, endpoint, SRAM and RTL interface implementation.
#define main baseline_entry
#include "main.cpp"
#undef main

static void benchmark_delay(const string&file,const string&arm,bool dual,int mode,int banklat,int clockns){
 auto waves=loadcase(file);vector<string> results;long long allread=0,allwrite=0,allbank=0;
 auto begin=chrono::steady_clock::now();
 for(auto&w:waves){
  Harness h(dual);h.d->hiband_mode=mode;h.bankLatency=banklat;h.clock_ns=clockns;
  bool onlyGets=arm=="gets_only",onlyMoe=arm=="moe_only";
  bool force=true,runtime=false;
  auto hoststart=chrono::steady_clock::now();vector<Path> plan=force?construct(w):vector<Path>{};
  long long planning_ns=chrono::duration_cast<chrono::nanoseconds>(chrono::steady_clock::now()-hoststart).count();
  if(onlyGets)for(auto f:w.flows)h.nextid+=(f[2]+511)/512;
  for(auto f:w.flows)if(!onlyGets)for(int off=0;off<f[2];off+=512){
   Path* chosen=nullptr;for(auto&p:plan)if(p.src==f[0]&&p.dst==f[1]){chosen=&p;break;}
   auto&p=h.add(f[0],f[1],3,min(512,f[2]-off));
   if(chosen&&force){p.circuit=false;p.cs=chosen->cs[0];p.hold=true;}
  }
  for(auto g:w.gets)if(!onlyMoe)h.gets(g[1],g[2],g[0]);
  int setup_begin=-1,setup_end=-1;bool late=false;
  if(force&&!plan.empty()){
   setup_begin=h.now;h.apply(plan);setup_end=h.now;
  }
  PolicyReceipt policy;
  if(runtime){policy=runtime_policy(h,w.H);planning_ns=policy.host_ns;late=policy.late;plan.clear();}
  h.drain();if(!dual)need(h.d->hiband_mode_ready||mode==0,"HiBand mode was not acknowledged");
  int mt=0,ct=0;vector<int> lat;long long niwait=0;
  uint64_t canonical=1469598103934665603ull;
  for(auto&[id,p]:h.packets){
   if(p.op==3||p.op==4)mt=max(mt,p.committed);
   if(p.op==2){ct=max(ct,p.committed);auto&request=h.packets.at(p.txn);lat.push_back(p.committed-request.at);niwait+=request.inject-request.at;}
   for(auto&w:p.got)for(auto x:w){canonical^=x;canonical*=1099511628211ull;}
  }
  sort(lat.begin(),lat.end());int p99=lat.empty()?0:lat[(lat.size()*99+99)/100-1];
  long long expectedRead=0,expectedWrite=0;
  for(auto&[id,p]:h.packets){if(p.op==3)expectedRead+=p.body.size();if(p.op==3||p.op==2)expectedWrite+=p.body.size();}
  need(h.source_services==expectedRead&&h.dest_services==expectedWrite,"SRAM service count mismatch");
  need(h.bank_services==lat.size()*2,"GetS bank read count mismatch");
  allread+=h.source_services;allwrite+=h.dest_services;allbank+=h.bank_services;
  ostringstream s;s<<"{\"stage\":\""<<w.stage<<"\",\"finish\":"<<max(mt,ct)<<",\"moe\":"<<mt<<",\"gets\":"<<ct<<",\"gets_p99\":"<<p99<<",\"gets_count\":"<<lat.size()<<",\"gets_injection_wait_sum\":"<<niwait<<",\"packets\":"<<h.packets.size()<<",\"canonical_payload_hash\":\""<<hex<<canonical<<dec<<"\",\"m_flits\":"<<h.d->m_flits<<",\"c_flits\":"<<h.d->c_flits<<",\"cs_flits\":"<<h.d->cs_flits<<",\"configuration_requests\":"<<h.d->config_flits<<",\"setup_begin\":"<<setup_begin<<",\"setup_end\":"<<setup_end<<",\"planner_ns\":"<<planning_ns<<",\"decision_late\":"<<(late?"true":"false")<<",\"selected_paths\":"<<plan.size()<<",\"candidates\":"<<policy.candidates<<",\"evaluated\":"<<policy.evaluated<<",\"installed\":"<<(policy.installed?"true":"false")<<",\"policy_reason\":\""<<policy.reason<<"\"}";
  results.push_back(s.str());
 }
 auto elapsed=chrono::duration_cast<chrono::milliseconds>(chrono::steady_clock::now()-begin).count();
 cout<<"{\"status\":\"PASS_RTL_DELIVERY_PAYLOAD_AND_SRAM\",\"arm\":\""<<arm<<"\",\"dual\":"<<dual<<",\"hiband_mode\":"<<mode<<",\"bank_latency\":"<<banklat<<",\"clock_ns\":"<<clockns<<",\"read_flits\":"<<allread<<",\"write_flits\":"<<allwrite<<",\"bank_flits\":"<<allbank<<",\"wall_ms\":"<<elapsed<<",\"runtime_status\":\""<<(arm=="runtime"?"EXACT_RTL_MODEL_WITH_CHARGED_CPU_TIME":"NOT_RUNTIME_POLICY")<<"\",\"waves\":[";
 for(size_t i=0;i<results.size();i++){if(i)cout<<",";cout<<results[i];}cout<<"]}\n";
}
int main(int argc,char**argv){
 try{Verilated::commandArgs(argc,argv);(void)legal_paths(0,1);
  need(argc>3&&string(argv[1])=="--case"&&string(argv[3])=="delay_control","usage: --case FILE delay_control");
  int bank=8,clockns=1;for(int i=4;i<argc;i++){
   if(string(argv[i])=="--bank"&&i+1<argc)bank=stoi(argv[++i]);
   if(string(argv[i])=="--clock-ns"&&i+1<argc)clockns=stoi(argv[++i]);
  }
  benchmark_delay(argv[2],argv[3],true,0,bank,clockns);return 0;
 }catch(exception&e){cerr<<"FAIL "<<e.what()<<'\n';return 1;}
}
