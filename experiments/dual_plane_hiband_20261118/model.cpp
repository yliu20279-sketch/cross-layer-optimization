// Standalone architectural screening model, not author RTL or PopNet.
// Clocked 8-byte phits; 256-bit links; finite wormhole input queues.
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cmath>
#include <deque>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>
using namespace std;
constexpr int NN=80, PORTS=8, VN=3, DEPTH=64, SLOTS=16;
struct Flow {int s,d,bytes;};
struct Get {int at,s,d;};
struct Wave {string stage; int H; vector<Flow> flows; vector<Get> gets;};
struct Path {int s,d,mask; vector<int> cs;};
struct Phit {int p,pos,seq;};
struct Packet {
 int s,d,v,bytes,nph,txn,at,read=0,sent=0,received=0,done=-1;
 bool assembled=false,hold=false; vector<int> route;
};
struct Job {int p,left,ready,kind;}; // 0 source read, 1 receive write, 2 bank read
struct Result {
 int finish=0,moe=0,gets=0,packets=0,maxq=0,maxrx=0; long long phits=0;
 vector<int> getdone; vector<long long> stalls=vector<long long>(3);
 vector<array<int,5>> timeline; // request TX/RX, bank done, reply TX/RX
 long long tx=0,sram=0,wire=0,cswire=0;
};
struct Graph {
 array<vector<int>,NN> adj;
 Graph(){
  auto edge=[&](int a,int b){adj[a].push_back(b);adj[b].push_back(a);};
  for(int plane: {0,16,32}){
   for(int i=0;i<16;i++){
    if(i%4<3)edge(plane+i,plane+i+1);
    if(i/4<3)edge(plane+i,plane+i+4);
    edge(plane+i,64+i);
   }
  }
  for(int c=0;c<9;c++){
   int n=(c/3)*4+c%3;
   for(int ni:{n,n+1,n+4,n+5})edge(48+c,64+ni);
  }
  for(auto pr:vector<pair<int,int>>{{0,9},{2,10},{6,11},{8,12},{9,10},{9,11},{10,12},{11,12}})
   edge(48+pr.first,48+pr.second);
  for(auto& v:adj){sort(v.begin(),v.end()); assert(v.size()<=PORTS);}
 }
 int port(int n,int other)const{
  auto it=find(adj[n].begin(),adj[n].end(),other);
  if(it==adj[n].end())throw runtime_error("unwired route");
  return int(it-adj[n].begin());
 }
 vector<int> mesh(int s,int d,int plane)const{
  vector<int> r{plane+s};int a=s;
  while(a%4!=d%4){a+=(a%4<d%4?1:-1);r.push_back(plane+a);}
  while(a/4!=d/4){a+=(a/4<d/4?4:-4);r.push_back(plane+a);}
  r.push_back(64+d);return r;
 }
 vector<Path> paths(int s,int d)const{
  vector<Path> out;
  function<void(int,int,vector<int>)> dfs=[&](int c,int mask,vector<int> cur){
   cur.push_back(c);mask|=1<<c;
   if(find(adj[48+c].begin(),adj[48+c].end(),64+d)!=adj[48+c].end())out.push_back({s,d,mask,cur});
   for(int n:adj[48+c]) if(n>=48&&n<61&&!(mask&(1<<(n-48))))dfs(n-48,mask,cur);
  };
  for(int n:adj[64+s])if(n>=48&&n<57)dfs(n-48,0,{});
  sort(out.begin(),out.end(),[](auto&a,auto&b){return make_pair(a.cs.size(),a.cs)<make_pair(b.cs.size(),b.cs);});
  if(out.size()>2)out.resize(2);
  return out;
 }
} graph;
using Plan=vector<Path>;
struct Sim {
 const Wave& w; string arm; Plan plan; int setup,banklat;
 int now=0,complete=0,expected=0,moeremain=0,nextget=0;
 deque<Packet> p;
 array<array<deque<int>,VN>,16> pending,active;
 array<array<deque<Job>,VN>,16> jobs;
 array<array<int,VN>,16> live{},rx{},txrr{},unused{};
 array<int,16> sramptr{},txptr{},outstanding{};
 vector<deque<Phit>> q=vector<deque<Phit>>(NN*PORTS*VN);
 vector<int> owner=vector<int>(NN*PORTS*VN,-1), rr=vector<int>(NN*PORTS*VN,0);
 vector<int> vrr=vector<int>(NN*PORTS,0);
 Result res;
 Sim(const Wave& w_,string a,Plan pl={},int config=40,int bank=8):w(w_),arm(a),plan(pl),setup(config),banklat(bank){
  res.getdone.assign(w.gets.size(),-1);
  res.timeline.assign(w.gets.size(),array<int,5>{-1,-1,-1,-1,-1});
  for(auto& f:w.flows)for(int off=0;off<f.bytes;off+=512){
   int n=min(512,f.bytes-off);add(f.s,f.d,0,n,-1,0);++moeremain;
  }
  expected=int(p.size())+int(w.gets.size())*2;
 }
 int add(int s,int d,int v,int bytes,int txn,int at){
  Packet m; m.s=s;m.d=d;m.v=v;m.bytes=bytes;m.nph=(bytes+32+7)/8;m.txn=txn;m.at=at;
  // GetS's 32B is its header, not a second 32B payload.
  if(v==1)m.nph=4;
  if(v==0)for(auto& path:plan)if(path.s==s&&path.d==d)m.hold=true;
  m.route=route(s,d,v);p.push_back(m); int id=int(p.size())-1;pending[s][v].push_back(id);return id;
 }
 vector<int> route(int s,int d,int v){
  if(v==0&&arm!="delay_control")for(auto& path:plan)if(path.s==s&&path.d==d){
   vector<int> r;for(int c:path.cs)r.push_back(48+c);r.push_back(64+d);return r;
  }
  if(arm=="hiband_GB"||arm=="hiband_LB"||arm=="hiband_FL"){
   if(abs(s%4-d%4)+abs(s/4-d/4)==1)return {16+s,16+d,64+d};
   if(arm=="hiband_FL")throw runtime_error("FULL_LOCAL cannot route non-neighbor traffic");
  }
  return graph.mesh(s,d,(arm=="dual"||arm=="proposed"||arm=="delay_control")&&v!=0?32:0);
 }
 int width(int node,int next){
  if(node>=64||next>=64)return 4;
  if(node<16){if(arm=="hiband_GB")return 2;if(arm=="hiband_LB")return 1;if(arm=="hiband_FL")return 0;}
  if(node>=16&&node<32){if(arm=="hiband_GB")return 2;if(arm=="hiband_LB")return 3;if(arm=="hiband_FL")return 4;}
  return 4;
 }
 int qid(int n,int in,int v)const{return (n*PORTS+in)*VN+v;}
 int wanted(const Phit& f){auto& m=p[f.p];return m.route[f.pos]>=64?0:graph.port(m.route[f.pos],m.route[f.pos+1]);}
 void admit(){
  while(nextget<int(w.gets.size())&&w.gets[nextget].at<=now){
   auto g=w.gets[nextget];add(g.s,g.d,1,0,nextget,g.at);++nextget;
  }
  for(int n=0;n<16;n++)for(int v=0;v<VN;v++){
   auto& a=pending[n][v];
   while(!a.empty()&&live[n][v]<SLOTS){
    int id=a.front();auto& m=p[id];
    if(v==1&&outstanding[n]>=16)break;
    a.pop_front();++live[n][v];active[n][v].push_back(id);
    if(v==1)++outstanding[n];
    if(v==0)jobs[n][0].push_back({id,(m.bytes+7)/8,now,0});
    else m.read=1;
   }
  }
 }
 void finish(int id){
  auto& m=p[id];if(m.done!=-1)throw runtime_error("duplicate completion");
  m.done=now;++complete;--rx[m.d][m.v];
  if(m.v==0){res.moe=max(res.moe,now);--moeremain;}
  if(m.v==2){res.gets=max(res.gets,now);res.getdone[m.txn]=now;--outstanding[m.d];}
 }
 void sram(){
  for(int n=0;n<16;n++){
   for(int turn=0;turn<VN;turn++){
    int v=(sramptr[n]+turn)%VN;auto& jq=jobs[n][v];
    if(jq.empty()||jq.front().ready>now)continue;
    auto& j=jq.front();
    if(j.kind==2&&j.left<=4&&int(pending[n][2].size())+live[n][2]>=SLOTS)continue;
    int used=min(4,j.left);j.left-=used;res.sram+=used;
    sramptr[n]=(v+1)%VN;
    if(j.left==0){
     int id=j.p,kind=j.kind;jq.pop_front();
     if(kind==0)p[id].read=1;
     else if(kind==1)finish(id);
     else{
      auto m=p[id];res.timeline[m.txn][2]=now;
      add(m.d,m.s,2,64,m.txn,now+1);finish(id);
     }
    }
    break;
   }
  }
 }
 void inject(vector<pair<int,Phit>>& arrivals,vector<int>& reserved){
  for(int n=0;n<16;n++)for(int turn=0;turn<VN;turn++){
   int v=(txptr[n]+turn)%VN;auto& a=active[n][v];if(a.empty())continue;
   auto& m=p[a.front()];if(!m.read||m.at>now)continue;
   if(m.hold&&now<setup)continue;
   int qi=qid(m.route[0],graph.port(m.route[0],64+n),v);
   int count=min({4,m.nph-m.sent,DEPTH-int(q[qi].size())-reserved[qi]});
   if(!count){++res.stalls[v];continue;}
   if(m.sent==0&&v!=0)res.timeline[m.txn][v==1?0:3]=now;
   for(int j=0;j<count;j++)arrivals.push_back({qi,{a.front(),0,m.sent++}});
   reserved[qi]+=count;res.tx+=count;txptr[n]=(v+1)%VN;
   if(m.sent==m.nph){--live[n][v];a.pop_front();}
   break;
  }
 }
 void network(vector<pair<int,Phit>>& arrivals,vector<int>& reserved){
  for(int node=0;node<NN;node++){
   int ports=int(graph.adj[node].size()),outs=node>=64?1:ports;
   array<int,PORTS*VN> used{};
   for(int outturn=0;outturn<outs;outturn++){
    int out=(now+outturn)%outs;
    int physical=node*PORTS+out,chosen=-1,key=-1;
    int next=node>=64?-1:graph.adj[node][out],cap=width(node,next);
    for(int vt=0;vt<VN&&chosen<0;vt++){
     int v=(vrr[physical]+vt)%VN, candidatekey=physical*VN+v;
     for(int j=0;j<ports;j++){
      int in=owner[candidatekey]>=0?owner[candidatekey]/VN:(rr[candidatekey]+j)%ports;
      int k=in*VN+v,candidate=node*PORTS*VN+k;
      if(!q[candidate].empty()&&used[in]<4){
       auto f=q[candidate].front();auto& m=p[f.p];
       if(wanted(f)==out){
        bool available;
        if(node>=64)available=f.seq!=0||rx[node-64][v]<SLOTS;
        else{
         int nq=qid(next,graph.port(next,node),v);
         available=int(q[nq].size())+reserved[nq]<DEPTH;
        }
        if(available){chosen=k;key=candidatekey;break;}
        ++res.stalls[m.v];
       }
      }
      if(owner[candidatekey]>=0)break;
     }
    }
    if(chosen<0)continue;
    int qi=node*PORTS*VN+chosen;
    owner[key]=chosen;vrr[physical]=(chosen%VN+1)%VN;
    for(int i=0;i<cap&&used[chosen/VN]<4&&!q[qi].empty();i++){
     auto f=q[qi].front();auto& m=p[f.p];
     if(wanted(f)!=out)break;
     if(node>=64){
      int ni=node-64;
      if(f.seq==0&&rx[ni][m.v]>=SLOTS){++res.stalls[m.v];break;}
      if(f.seq!=m.received)throw runtime_error("phit order or duplicated phit");
      if(f.seq==0){++rx[ni][m.v];res.maxrx=max(res.maxrx,rx[ni][m.v]);}
      ++m.received;
      if(f.seq==m.nph-1){
       m.assembled=true;
       if(m.v!=0)res.timeline[m.txn][m.v==1?1:4]=now;
       if(m.v==1)jobs[ni][1].push_back({f.p,8,now+banklat,2});
       else jobs[ni][m.v].push_back({f.p,(m.bytes+7)/8,now+1,1});
      }
     }else{
      int nq=qid(next,graph.port(next,node),m.v);
      if(int(q[nq].size())+reserved[nq]>=DEPTH){++res.stalls[m.v];break;}
      arrivals.push_back({nq,{f.p,f.pos+1,f.seq}});++reserved[nq];++res.wire;
      if(node>=48&&node<61)++res.cswire;
     }
     q[qi].pop_front();++used[chosen/VN];++res.phits;
     if(f.seq==m.nph-1){owner[key]=-1;rr[key]=(chosen/VN+1)%ports;break;}
    }
   }
  }
 }
 Result run(){
  for(now=0;now<500000;now++){
   admit();sram();
   vector<pair<int,Phit>> arrivals;vector<int> reserved(q.size());
   inject(arrivals,reserved);network(arrivals,reserved);
   for(auto [qi,f]:arrivals){q[qi].push_back(f);res.maxq=max(res.maxq,int(q[qi].size()));assert(q[qi].size()<=DEPTH);}
   if(complete==expected){
    for(auto& qu:q)if(!qu.empty())throw runtime_error("undrained queue");
    for(auto& m:p)if(m.received!=m.nph||m.done<0)throw runtime_error("lost packet");
    for(int t:res.getdone)if(t<0)throw runtime_error("lost reply");
    for(size_t i=0;i<res.timeline.size();i++){
     int prior=w.gets[i].at;
     for(auto stamp:res.timeline[i]){if(stamp<prior)throw runtime_error("noncausal transaction");prior=stamp;}
     if(res.getdone[i]<prior)throw runtime_error("response completed before data return");
    }
    res.finish=now;res.packets=int(p.size());return res;
   }
  }
  cerr<<"watchdog "<<arm<<" "<<w.stage<<" complete "<<complete<<" expected "<<expected<<" created "<<p.size()<<"\n";
  for(int ni=0;ni<16;ni++){
   cerr<<"NI "<<ni<<" outstanding "<<outstanding[ni];
   for(int v=0;v<VN;v++)cerr<<" v"<<v<<" pending "<<pending[ni][v].size()<<" active "<<active[ni][v].size()<<" rx "<<rx[ni][v]<<" jobs "<<jobs[ni][v].size();
   cerr<<"\n";
  }
  int shown=0;for(int n=0;n<NN;n++)for(int k=0;k<PORTS*VN;k++){
   auto& qu=q[n*PORTS*VN+k];if(qu.empty()||shown++>60)continue;auto f=qu.front();auto&m=p[f.p];
   cerr<<"queue node "<<n<<" input "<<k/VN<<" vn "<<k%VN<<" count "<<qu.size()<<" pid "<<f.p<<" seq "<<f.seq<<" of "<<m.nph<<" to "<<m.d<<" out "<<wanted(f)<<"\n";
  }
  throw runtime_error("simulation watchdog");
 }
};
long long volume(const Wave& w,const Plan& p){
 long long b=0;for(auto&f:w.flows)for(auto&x:p)if(f.s==x.s&&f.d==x.d){b+=f.bytes;break;}return b;
}
bool feasible(const Wave& w,const Plan& ps){
 int mask=0;for(auto& p:ps){if(mask&p.mask)return false;mask|=p.mask;}
 map<pair<int,int>,long long> load;array<long long,16> tx{},rx{},mem{};
 for(auto& f:w.flows){
  long long ph=(f.bytes+32*((f.bytes+511)/512))/8;
  tx[f.s]+=ph;rx[f.d]+=ph;mem[f.s]+=(f.bytes+7)/8;mem[f.d]+=(f.bytes+7)/8;
  vector<int> r=graph.mesh(f.s,f.d,0);
  for(auto& path:ps)if(path.s==f.s&&path.d==f.d){r.clear();for(int c:path.cs)r.push_back(48+c);r.push_back(64+f.d);break;}
  for(size_t k=1;k<r.size();k++)load[{r[k-1],r[k]}]+=ph;
 }
 for(auto&g:w.gets){tx[g.s]+=4;rx[g.d]+=4;tx[g.d]+=12;rx[g.s]+=12;mem[g.d]+=8;mem[g.s]+=8;}
 for(auto a:{tx,rx,mem})for(auto n:a)if(n>4LL*w.H)return false;
 for(auto [edge,n]:load)if(n>4LL*(w.H-40))return false;
 return true;
}
string planid(const Plan& p){
 vector<string> ids;for(auto&x:p){string s=to_string(x.s)+">"+to_string(x.d)+":";for(auto c:x.cs)s+=to_string(c)+",";ids.push_back(s);}
 sort(ids.begin(),ids.end());string s;for(auto&a:ids)s+=a+";";return s;
}
struct Planned {Plan plan;int constructed=0,evaluated=0,baseline_moe=0,baseline_join=0,max_gets_delta=0;Result result;};
Planned choose(const Wave& w,int config,int eta,int epsilon,int bank){
 Planned ans;Result base=Sim(w,"dual",{},config,bank).run();ans.result=base;ans.baseline_moe=base.moe;ans.baseline_join=base.finish;
 map<pair<int,int>,long long> vol;for(auto&f:w.flows)vol[{f.s,f.d}]+=f.bytes;
 Plan cur;vector<Plan> pool;set<string> seen;
 for(int round=0;round<13;round++){
  vector<pair<long long,pair<int,int>>> remaining;
  for(auto [sd,b]:vol)if(none_of(cur.begin(),cur.end(),[&](auto&p){return make_pair(p.s,p.d)==sd;}))remaining.push_back({-b,sd});
  sort(remaining.begin(),remaining.end());if(remaining.size()>4)remaining.resize(4);
  vector<Path> adds;for(auto entry:remaining){auto sd=entry.second;auto all=graph.paths(sd.first,sd.second);adds.insert(adds.end(),all.begin(),all.end());}
  vector<Plan> extensions;
  auto offer=[&](Plan p){if(feasible(w,p)&&seen.insert(planid(p)).second){extensions.push_back(p);pool.push_back(p);}};
  for(size_t i=0;i<adds.size();i++){
   auto p=cur;p.push_back(adds[i]);offer(p);
   for(size_t j=i+1;j<adds.size();j++)if(make_pair(adds[i].s,adds[i].d)!=make_pair(adds[j].s,adds[j].d)){
    p=cur;p.push_back(adds[i]);p.push_back(adds[j]);offer(p);
   }
  }
  if(extensions.empty())break;
  sort(extensions.begin(),extensions.end(),[&](auto&a,auto&b){
   if(volume(w,a)!=volume(w,b))return volume(w,a)>volume(w,b);
   int na=0,nb=0;for(auto&p:a)na+=int(p.cs.size());for(auto&p:b)nb+=int(p.cs.size());
   return make_pair(na,planid(a))<make_pair(nb,planid(b));
  });
  if(volume(w,extensions[0])<=volume(w,cur))break;
  cur=extensions[0];
 }
 ans.constructed=int(pool.size());
 sort(pool.begin(),pool.end(),[&](auto&a,auto&b){
  if(volume(w,a)!=volume(w,b))return volume(w,a)>volume(w,b);
  int na=0,nb=0;for(auto&p:a)na+=int(p.cs.size());for(auto&p:b)nb+=int(p.cs.size());
  return make_pair(na,planid(a))<make_pair(nb,planid(b));
 });
 for(auto& ps:pool){
  if(ans.evaluated>=8)break;
  ++ans.evaluated;
  auto r=Sim(w,"proposed",ps,config,bank).run();
  // These cases require both branches at the phase barrier. Improving only
  // MoE while delaying the join is not an accepted update.
  bool ok=r.finish+eta<base.finish&&r.moe<=base.moe;
  for(size_t i=0;i<r.getdone.size();i++)if(r.getdone[i]-base.getdone[i]+eta>epsilon)ok=false;
  if(ok){
   ans.plan=ps;ans.result=r;
   for(size_t i=0;i<r.getdone.size();i++)ans.max_gets_delta=max(ans.max_gets_delta,r.getdone[i]-base.getdone[i]);
   break;
  }
 }
 return ans;
}
vector<Wave> readfile(const string& file){
 ifstream f(file);int n;f>>n;vector<Wave> out;
 for(int i=0;i<n;i++){
  Wave w;int nf,ng;f>>w.stage>>nf>>ng>>w.H;
  for(int j=0;j<nf;j++){Flow x;f>>x.s>>x.d>>x.bytes;w.flows.push_back(x);}
  for(int j=0;j<ng;j++){Get x;f>>x.at>>x.s>>x.d;w.gets.push_back(x);}out.push_back(w);
 }
 if(!f)throw runtime_error("invalid input");
 return out;
}
int main(int argc,char**argv){
 try{
  if(argc==2&&string(argv[1])=="--selftest"){
   // Validate physical port table and channel-width service with one flow.
   Wave w;w.H=8192;w.flows={{0,1,4096}};
   auto fg=Sim(w,"hiband_FG").run(),gb=Sim(w,"hiband_GB").run(),lb=Sim(w,"hiband_LB").run();
   assert(fg.packets==8&&fg.maxq<=DEPTH&&fg.finish>0&&gb.finish>0&&lb.finish>0);
   Wave remote;remote.H=8192;remote.flows={{0,3,4096}};
   auto g4=Sim(remote,"hiband_FG").run(),g2=Sim(remote,"hiband_GB").run(),g1=Sim(remote,"hiband_LB").run();
   assert(g4.finish<g2.finish&&g2.finish<g1.finish);
   w.gets={{0,0,1},{1,2,1}};auto d=Sim(w,"dual").run();assert(d.packets==12);
   auto ps=graph.paths(0,1);assert(!ps.empty());ps.resize(1);
   auto cs=Sim(w,"proposed",ps,40).run();assert(cs.cswire>0&&cs.getdone.size()==2);
   bool rejected=false;try{Sim(remote,"hiband_FL").run();}catch(exception&){rejected=true;}assert(rejected);
   Wave hot;hot.H=4096;hot.flows={{5,8,8192}};for(int i=0;i<64;i++)hot.gets.push_back({i,0,8});
   auto guarded=choose(hot,40,0,32,8);
   assert(guarded.max_gets_delta<=32&&guarded.result.moe<=guarded.baseline_moe);
   cout<<"PASS topology, channel widths, causal replies, phit delivery, finite credits, CS path, FULL_LOCAL reachability\n";return 0;
  }
  if(argc<3)throw runtime_error("usage model CASE ARM [setup=40] [eta=0] [epsilon=32] [bank_latency=8]");
  int config=argc>3?stoi(argv[3]):40,eta=argc>4?stoi(argv[4]):0,epsilon=argc>5?stoi(argv[5]):32,bank=argc>6?stoi(argv[6]):8;
  auto waves=readfile(argv[1]);string arm=argv[2];
  auto start=chrono::steady_clock::now();cout<<"{\"scope\":\"architectural_screen\",\"arm\":\""<<arm<<"\",\"setup_cycles\":"<<config<<",\"eta\":"<<eta<<",\"epsilon\":"<<epsilon<<",\"bank_latency\":"<<bank<<",\"waves\":[";
  bool first=true;
  for(auto&w:waves){
   Planned pl;Result r;
   auto planstart=chrono::steady_clock::now();
   if(arm=="gets_only"||arm=="moe_only"){
    auto only=w;
    if(arm=="gets_only")only.flows.clear();else only.gets.clear();
    r=Sim(only,"mesh",{},config,bank).run();
   }
   else if(arm=="proposed"||arm=="delay_control"){
    pl=choose(w,config,eta,epsilon,bank);r=pl.result;
    if(arm=="delay_control")r=Sim(w,arm,pl.plan,config,bank).run();
   }
   else r=Sim(w,arm,{},config,bank).run();
   long long planner_ns=(arm=="proposed"||arm=="delay_control")?chrono::duration_cast<chrono::nanoseconds>(chrono::steady_clock::now()-planstart).count():0;
   vector<int> latency;for(size_t i=0;i<r.getdone.size();i++)latency.push_back(r.getdone[i]-w.gets[i].at);
   sort(latency.begin(),latency.end());double mean=latency.empty()?0:double(accumulate(latency.begin(),latency.end(),0LL))/latency.size();
   auto pct=[&](double v){return latency.empty()?0:latency[min(latency.size()-1,size_t(ceil(v*latency.size())-1))];};
   array<long long,6> breakdown{};
   for(size_t i=0;i<r.timeline.size();i++){
    int prior=w.gets[i].at;
    for(int j=0;j<5;j++){breakdown[j]+=r.timeline[i][j]-prior;prior=r.timeline[i][j];}
    breakdown[5]+=r.getdone[i]-prior;
   }
   if(!first)cout<<",";
   first=false;
   cout<<"{\"stage\":\""<<w.stage<<"\",\"finish\":"<<r.finish<<",\"moe\":"<<r.moe<<",\"gets\":"<<r.gets<<",\"gets_count\":"<<r.getdone.size()<<",\"gets_mean\":"<<mean<<",\"gets_p50\":"<<pct(.5)<<",\"gets_p99\":"<<pct(.99)<<",\"gets_max\":"<<pct(1)<<",\"packets\":"<<r.packets<<",\"max_input_phits\":"<<r.maxq<<",\"max_receive_packets\":"<<r.maxrx<<",\"tx_phits\":"<<r.tx<<",\"sram_phits\":"<<r.sram<<",\"link_phits\":"<<r.wire<<",\"cs_link_phits\":"<<r.cswire<<",\"constructed\":"<<pl.constructed<<",\"evaluated\":"<<pl.evaluated<<",\"selected_payload\":"<<volume(w,pl.plan)<<",\"paths\":[";
   for(size_t i=0;i<pl.plan.size();i++){if(i)cout<<",";auto&p=pl.plan[i];cout<<"{\"src\":"<<p.s<<",\"dst\":"<<p.d<<",\"cs\":[";for(size_t j=0;j<p.cs.size();j++){if(j)cout<<",";cout<<p.cs[j];}cout<<"]}";}
   cout<<"],\"gets_latency_component_sums\":[";
   for(int j=0;j<6;j++){if(j)cout<<",";cout<<breakdown[j];}
   cout<<"],\"planner_elapsed_ns\":"<<planner_ns<<",\"guard_baseline_moe\":"<<pl.baseline_moe<<",\"guard_baseline_join\":"<<pl.baseline_join<<",\"guard_max_gets_delta\":"<<pl.max_gets_delta<<",\"credit_stall_attempts\":["<<r.stalls[0]<<","<<r.stalls[1]<<","<<r.stalls[2]<<"]}";
  }
  auto ms=chrono::duration_cast<chrono::milliseconds>(chrono::steady_clock::now()-start).count();
  cout<<"],\"wall_ms\":"<<ms<<",\"status\":\"PASS_DELIVERY_AND_DRAIN\"}\n";
 }catch(exception&e){cerr<<e.what()<<'\n';return 1;}
}
