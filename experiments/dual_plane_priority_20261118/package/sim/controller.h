// Source metadata is visible at the phase boundary. No old completion trace is
// consulted. The exact timing backend forks the live RTL/endpoint process.
#include <unistd.h>
#include <sys/wait.h>
#include <cerrno>
struct Candidate{vector<Path> paths;map<uint32_t,int> assignment;long long volume=0;};
static const vector<Path>& legal_paths(int s,int d){
 static const auto table=[](){array<array<vector<Path>,16>,16>a;for(int s=0;s<16;s++)for(int d=0;d<16;d++)if(s!=d){a[s][d]=paths(s,d);if(a[s][d].size()>2)a[s][d].resize(2);}return a;}();
 return table[s][d];
}
static vector<pair<int,int>> xyedges(int s,int d){
 vector<pair<int,int>> es;while(s%4!=d%4){int t=s+(s%4<d%4?1:-1);es.push_back({s,t});s=t;}
 while(s/4!=d/4){int t=s+(s/4<d/4?4:-4);es.push_back({s,t});s=t;}return es;
}
static bool assign_packets(const Harness&h,const vector<Path>&ps,int H,Candidate&out){
 out.paths=ps;out.volume=0;out.assignment.clear();int mask=0;
 for(auto&p:ps){int used=0;for(int c:p.cs)used|=1<<c;if(mask&used)return false;mask|=used;}
 array<long long,16> tx{},rx{},mem{};array<long long,13> csload{};map<pair<int,int>,long long> load;
 for(auto&[id,p]:h.packets)if(p.committed<0){
  int f=int(p.body.size())+1;tx[p.src]+=f;rx[p.dst]+=f;
  if(p.op==3)mem[p.src]+=p.body.size();
  if(p.op==3||p.op==2)mem[p.dst]+=p.body.size();
  if(p.op==1)mem[p.dst]+=2;
  if(p.op!=3||p.sent>=0){
   if(p.op!=1&&p.op!=2){
    if(p.circuit){for(auto&old:h.active_paths)if(old.src==p.src&&old.dst==p.dst&&old.cs.front()==p.cs)for(int c:old.cs)csload[c]+=f;}
    else{for(auto e:xyedges(p.src,p.dst))load[e]+=f;}
   }continue;
  }
  int selected=-1;
  for(size_t j=0;j<ps.size();j++)if(ps[j].src==p.src&&ps[j].dst==p.dst){
   bool fits=true;for(int c:ps[j].cs)fits&=csload[c]+f<=H;
   if(fits&&(selected<0||ps[j].cs.size()<ps[selected].cs.size()))selected=int(j);
  }
  if(selected>=0){out.assignment[id]=selected;out.volume+=p.bytes;for(int c:ps[selected].cs)csload[c]+=f;}
  else for(auto e:xyedges(p.src,p.dst))load[e]+=f;
 }
 // Reserve the actual command/ACK routes used by the RTL control protocol.
 auto control=[&](int n){tx[0]++;rx[n]++;tx[n]++;rx[0]++;for(auto e:xyedges(0,n))load[e]++;for(auto e:xyedges(n,0))load[e]++;};
 if(!ps.empty()){
  for(int n=0;n<16;n++){control(n);control(n);control(n);}
  for(int c=0;c<13;c++)control(c<9?4*(c/3)+c%3:c==9?0:c==10?2:c==11?8:10);
  control(0);
 }
 for(int n=0;n<16;n++)if(tx[n]>H||rx[n]>H||mem[n]>H)return false;
 for(auto[e,v]:load)if(v>H)return false;return true;
}
static string key_of(const vector<Path>&ps){
 vector<string> keys;for(auto&p:ps){string s=to_string(p.src)+">"+to_string(p.dst)+":";for(auto c:p.cs)s+=to_string(c)+",";keys.push_back(s);}
 sort(keys.begin(),keys.end());string s;for(auto&x:keys)s+=x+";";return s;
}
static vector<Candidate> candidate_pool(const Harness&h,int H){
 map<pair<int,int>,long long> volumes;for(auto&[id,p]:h.packets)if(p.op==3&&p.sent<0&&p.committed<0)volumes[{p.src,p.dst}]+=p.bytes;
 vector<Candidate> pool;vector<Path> current;set<string> seen;
 auto order=[&](const Candidate&a,const Candidate&b){
  if(a.volume!=b.volume)return a.volume>b.volume;
  int ac=0,bc=0;auto ai=image(a.paths),bi=image(b.paths);
  for(int c=0;c<13;c++){ac+=ai[c]!=h.active_image[c];bc+=bi[c]!=h.active_image[c];}
  return make_pair(ac,key_of(a.paths))<make_pair(bc,key_of(b.paths));
 };
 for(int round=0;round<13;round++){
  vector<pair<long long,pair<int,int>>> flows;
  Candidate old;assign_packets(h,current,H,old);auto remaining=volumes;
  for(auto[id,j]:old.assignment){auto&p=h.packets.at(id);remaining[{p.src,p.dst}]-=p.bytes;}
  for(auto[sd,b]:remaining)if(b>0)flows.push_back({-b,sd});
  sort(flows.begin(),flows.end());if(flows.size()>4)flows.resize(4);
  vector<Path> extensions;for(auto&item:flows){auto sd=item.second;auto&ps=legal_paths(sd.first,sd.second);extensions.insert(extensions.end(),ps.begin(),ps.end());}
  vector<Candidate> next;
  auto offer=[&](vector<Path> ps){Candidate c;if(assign_packets(h,ps,H,c)&&seen.insert(key_of(ps)).second){pool.push_back(c);next.push_back(c);}};
  for(size_t i=0;i<extensions.size();i++){
   auto ps=current;ps.push_back(extensions[i]);offer(ps);
   for(size_t j=i+1;j<extensions.size();j++){
    ps=current;ps.push_back(extensions[i]);ps.push_back(extensions[j]);offer(ps);
   }
  }
  if(next.empty())break;sort(next.begin(),next.end(),order);
  if(next.front().volume<=old.volume)break;current=next.front().paths;
 }
 sort(pool.begin(),pool.end(),order);return pool;
}
struct Prediction{int join=0,moe=0;vector<pair<uint32_t,int>> coherence;};
static Prediction completion(const Harness&h){
 Prediction r;for(auto&[id,p]:h.packets){
  if(p.op==3||p.op==4)r.moe=max(r.moe,p.committed);
  if(p.op==2)r.coherence.push_back({p.txn,p.committed});r.join=max(r.join,p.committed);
 }sort(r.coherence.begin(),r.coherence.end());return r;
}
static void pipe_all(int fd,void*ptr,size_t n,bool writing){
 auto*p=static_cast<char*>(ptr);while(n){ssize_t k=writing?write(fd,p,n):read(fd,p,n);if(k<0&&errno==EINTR)continue;need(k>0,"timing-model transport failed");p+=k;n-=size_t(k);}
}
static void set_holds(Harness&h,const Candidate&c){
 for(auto&[id,p]:h.packets)if(p.op==3&&p.sent<0&&(p.circuit||c.assignment.count(id))){
  if(!p.saved_route){p.old_circuit=p.circuit;p.old_cs=p.cs;p.old_version=p.version;p.saved_route=true;}
  p.hold=true;auto at=c.assignment.find(id);p.circuit=at!=c.assignment.end();
  if(p.circuit)p.cs=c.paths.at(at->second).cs.front();
 }
}
static void release_holds(Harness&h){
 for(auto&[id,p]:h.packets)if(p.hold){
  p.hold=false;
  if(p.saved_route){p.circuit=p.old_circuit;p.cs=p.old_cs;p.version=p.old_version;p.saved_route=false;}
 }
}
static Prediction predict(Harness&h,const Candidate*candidate){
 int fd[2];need(pipe(fd)==0,"timing-model pipe failed");pid_t child=fork();need(child>=0,"timing-model snapshot failed");
 if(child==0){
  close(fd[0]);
  try{
   if(candidate){set_holds(h,*candidate);h.apply(candidate->paths);}h.drain();auto r=completion(h);
   int header[3]={r.join,r.moe,int(r.coherence.size())};pipe_all(fd[1],header,sizeof header,true);
   for(auto&[id,time]:r.coherence){uint32_t data[2]={id,uint32_t(time)};pipe_all(fd[1],data,sizeof data,true);}
   close(fd[1]);_exit(0);
  }catch(...){close(fd[1]);_exit(2);}
 }
 close(fd[1]);int head[3];pipe_all(fd[0],head,sizeof head,false);Prediction r;r.join=head[0];r.moe=head[1];
 for(int i=0;i<head[2];i++){uint32_t data[2];pipe_all(fd[0],data,sizeof data,false);r.coherence.push_back({data[0],int(data[1])});}
 close(fd[0]);int status;need(waitpid(child,&status,0)==child&&WIFEXITED(status)&&WEXITSTATUS(status)==0,"timing-model child failed");return r;
}
static bool guarded(const Prediction&cand,const Prediction&base,int eta=0,int coherence_budget=32){
 if(cand.join+eta>=base.join||cand.moe>base.moe||cand.coherence.size()!=base.coherence.size())return false;
 for(size_t i=0;i<cand.coherence.size();i++)if(cand.coherence[i].first!=base.coherence[i].first||cand.coherence[i].second-base.coherence[i].second+eta>coherence_budget)return false;
 return true;
}
struct PolicyReceipt{long long host_ns=0;int candidates=0,evaluated=0;bool installed=false,late=false;string reason;};
static bool advance_cpu(Harness&h,long long ns,int deadline=4000000){
 long long until=min<long long>(h.now+(ns+h.clock_ns-1)/h.clock_ns,deadline);
 while(h.now<until&&h.done<int(h.packets.size()))h.tick();
 return h.done==int(h.packets.size());
}
static bool stationary(const Harness&h){
 if(!h.d->network_idle||h.backpressure||!h.callback.empty())return false;
 for(auto&[id,p]:h.packets)if(p.committed<0&&(!p.hold||p.sent>=0||p.op!=3))return false;
 for(auto&node:h.jobs)for(auto&q:node)if(!q.empty())return false;
 return true;
}
static PolicyReceipt runtime_policy(Harness&h,int H){
 PolicyReceipt rec;auto start=chrono::steady_clock::now();auto pool=candidate_pool(h,H);
 auto elapsed=[&](){return chrono::duration_cast<chrono::nanoseconds>(chrono::steady_clock::now()-start).count();};
 rec.candidates=pool.size();rec.host_ns=elapsed();
 if(advance_cpu(h,rec.host_ns)){rec.late=true;rec.reason="phase_completed_during_construction";return rec;}
 if(pool.empty()){rec.reason="no_feasible_extension";return rec;}
 auto mark=chrono::steady_clock::now();auto base=predict(h,nullptr);
 long long cost=chrono::duration_cast<chrono::nanoseconds>(chrono::steady_clock::now()-mark).count();rec.host_ns+=cost;
 if(advance_cpu(h,cost)){rec.late=true;rec.reason="phase_completed_during_timing_model";return rec;}
 for(auto&c:pool){
  if(rec.evaluated>=8)break;
  ++rec.evaluated;
  mark=chrono::steady_clock::now();auto candidate=predict(h,&c);
  cost=chrono::duration_cast<chrono::nanoseconds>(chrono::steady_clock::now()-mark).count();rec.host_ns+=cost;
  if(advance_cpu(h,cost)){rec.late=true;rec.reason="phase_completed_during_timing_model";return rec;}
  if(!guarded(candidate,base))continue;
  set_holds(h,c);h.pause();while(!h.d->cs_idle)h.tick();
  // Final prediction starts from the acknowledged paused RTL state. The old
  // S0 prediction keeps its original absolute completion timestamps.
  bool idle_snapshot=stationary(h);int snapshot_cycle=h.now;
  mark=chrono::steady_clock::now();auto final=predict(h,&c);
  cost=chrono::duration_cast<chrono::nanoseconds>(chrono::steady_clock::now()-mark).count();rec.host_ns+=cost;
  // Empty routers rotate their output priority with period five. Rounding
  // the measured CPU service upward preserves that phase in an idle snapshot.
  long long charged=(((cost+h.clock_ns-1)/h.clock_ns+4)/5)*5*h.clock_ns;
  advance_cpu(h,charged,max(h.now,base.join));
  if(h.now>=base.join){
   release_holds(h);for(int n=0;n<16;n++)need(h.cfg(n,4,0,0,h.d->active_version),"rollback resume failed");
   rec.reason="final_decision_deadline";return rec;
  }
  if(idle_snapshot&&stationary(h)&&(h.now-snapshot_cycle)%5==0){
   final.join+=h.now-snapshot_cycle;final.moe+=h.now-snapshot_cycle;
   if(guarded(final,base)){
    h.apply(c.paths);rec.installed=true;rec.reason="acknowledged_update_after_final_check";return rec;
   }
  }
  // Other traffic changed the state during the model computation. Decline
  // the update within this bounded decision; do not install a stale estimate.
  release_holds(h);for(int n=0;n<16;n++)need(h.cfg(n,4,0,0,h.d->active_version),"rollback resume failed");
  rec.reason="final_state_changed_or_timing_guard";return rec;
 }
 rec.reason="timing_or_coherence_guard";return rec;
}
static void controller_test(){
 Harness h(true);h.backpressure=11;
 h.add(5,0,3,512);h.add(5,8,3,512);for(int i=0;i<12;i++)h.gets(0,1,i*3);
 auto pool=candidate_pool(h,8192);need(!pool.empty()&&pool[0].volume==1024,"joint allocation or shared-NI construction");
 for(int i=0;i<12;i++)h.tick();auto baseline=predict(h,nullptr);h.drain();auto actual=completion(h);
 need(baseline.join==actual.join&&baseline.moe==actual.moe&&baseline.coherence==actual.coherence,"snapshot timing model mismatch");
 Harness q(true);q.add(5,0,3,512);q.add(5,8,3,512);for(int i=0;i<12;i++)q.gets(0,1,i*3);
 auto p=candidate_pool(q,8192).front();auto predicted=predict(q,&p);set_holds(q,p);q.apply(p.paths);q.drain();actual=completion(q);
 need(predicted.join==actual.join&&predicted.moe==actual.moe&&predicted.coherence==actual.coherence,"candidate timing model mismatch");
 Harness r(true);r.add(5,8,3,512);auto c=candidate_pool(r,8192).front();set_holds(r,c);r.pause();
 need(stationary(r),"paused snapshot should be idle");auto frozen=predict(r,&c);for(int i=0;i<10;i++)r.tick();
 r.apply(c.paths);r.drain();actual=completion(r);need(actual.join==frozen.join+10,"idle final-state timing shift mismatch");
 Harness restore(true);restore.apply({Path{5,8,{3}}});auto&old=restore.add(5,8,3,32,restore.now,true,3,restore.d->active_version);
 Candidate mesh;set_holds(restore,mesh);need(old.hold&&!old.circuit,"old unbound CS descriptor not held for Mesh fallback");
 release_holds(restore);need(old.circuit&&old.cs==3&&old.version==restore.d->active_version,"S0 descriptor restoration failed");restore.drain();
 cout<<"PASS joint packet assignment, CS exclusion, shared NI budgets, exact live-state RTL timing snapshots, per-transaction completion checks\n";
}
