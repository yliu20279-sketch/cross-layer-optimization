#pragma once
#include <array>
#include <vector>
#include <cstring>
#include <fstream>
#include <algorithm>
#include <stdexcept>
template<class Runtime> class SramMatrix {
 using U=unsigned long long;
 Runtime&r;std::vector<unsigned char>mem;
 std::array<U,8>free{},reads{},writes{};U banks=0,cycles=0,events=0,muls=0,adds=0,reduces=0,last=0,version=0;
 static constexpr U X=0,W=524288,A=2097152,T=A+512,Y=3145728;
 void access(const std::vector<std::pair<U,U>>&q,bool wr){U issue=r.chipCycle(),done=issue;for(auto p:q){if(!p.second||p.first>=mem.size()||p.second>mem.size()-p.first)throw std::runtime_error("SRAM capacity");for(U l=p.first/32;l<=(p.first+p.second-1)/32;l++){unsigned b=l%8;U st=std::max(issue,free[b]);free[b]=st+1;done=std::max(done,st+1);(wr?writes[b]:reads[b])++;}}banks+=done-issue;r.chipCycle()=done;}
 float get(U a){float v;memcpy(&v,mem.data()+a,4);return v;}void put(U a,float v){memcpy(mem.data()+a,&v,4);}
 void op(U n,bool red=false){NPUSim::NpuEventRecorder rec;if(red)rec.reduceCompute(3,n);else rec.vectorCompute(1,n);U before=r.chipCycle();auto s=r.scheduleProgram(rec.events());events+=s.entries.size();cycles+=r.chipCycle()-before;}
 void reduce(U a,int width){for(int half=width/2;half;half/=2)for(int off=0;off<half;off+=16){int n=std::min(16,half-off);access({{a+off*4ULL,n*4ULL},{a+(off+half)*4ULL,n*4ULL}},false);float v[16];for(int j=0;j<n;j++)v[j]=get(a+(off+j)*4ULL)+get(a+(off+half+j)*4ULL);op(n,true);reduces+=n;access({{a+off*4ULL,n*4ULL}},true);for(int j=0;j<n;j++)put(a+(off+j)*4ULL,v[j]);}}
 void zero(U a,int n){access({{a,n*4ULL}},true);memset(mem.data()+a,0,n*4);}
public:
 explicit SramMatrix(Runtime&rt):r(rt),mem(4194304){}
 void binary(U xhb,U whb,U yhb,U n,bool mul,U job,const char*dir){
  if(!n||n*4>W||n*4>mem.size()-Y)throw std::runtime_error("vector SRAM capacity");U begin=r.chipCycle();r.load(xhb,mem.data()+X,n*4,"vector_X_SRAM");access({{X,n*4}},true);r.load(whb,mem.data()+W,n*4,"vector_B_SRAM");access({{W,n*4}},true);
  for(U i=0;i<n;i+=16){U count=std::min<U>(16,n-i);access({{X+i*4,count*4},{W+i*4,count*4}},false);last=r.chipCycle();float v[16];for(U j=0;j<count;j++)v[j]=mul?get(X+(i+j)*4)*get(W+(i+j)*4):get(X+(i+j)*4)+get(W+(i+j)*4);op(count);(mul?muls:adds)+=count;access({{Y+i*4,count*4}},true);for(U j=0;j<count;j++)put(Y+(i+j)*4,v[j]);}
  access({{Y,n*4}},false);r.store(yhb,mem.data()+Y,n*4,"vector_FP32_commit");std::ofstream out(std::string(dir)+"/VECTOR_LOWERING.jsonl",std::ios::app);out<<"{\"job\":"<<job<<",\"n\":"<<n<<",\"mul\":"<<(mul?1:0)<<",\"begin\":"<<begin<<",\"last_reader\":"<<last<<",\"complete\":"<<r.chipCycle()<<",\"events\":"<<events<<",\"bank_cycles\":"<<banks<<"}\n";
 }
 // FP16 execution contract: increasing K within 64-element partial dots,
 // then increasing-K FP32 addition of those partials. The BF16 FDA64 path
 // below is preserved separately; dtype must never select it implicitly.
 void run_fp16(U xhb,U whb,U yhb,int M,int N,int K,U job,const char*dir){
  if(M<1||M>19||N<1||N>4096||K<1||K>4096||M*K*4ULL>W||M*N*4ULL>mem.size()-Y)throw std::runtime_error("unsupported FP16 matrix/capacity");
  U begin=r.chipCycle();r.load(xhb,mem.data()+X,M*K*4ULL,"CPU_expanded_FP16_X_to_SRAM");access({{X,M*K*4ULL}},true);
  std::ofstream rows(std::string(dir)+"/MATRIX_TILES.csv",std::ios::app);
  for(int n0=0;n0<N;n0+=64){int nn=std::min(64,N-n0);if(r.chipCycle()<last)throw std::runtime_error("FP16 weight overwrite before reader");
   ++version;U start=r.chipCycle();r.load(whb+n0*K*4ULL,mem.data()+W,nn*K*4ULL,"CPU_expanded_FP16_W_to_SRAM");access({{W,nn*K*4ULL}},true);U ready=r.chipCycle();
   for(int m=0;m<M;++m)for(int sub=0;sub<nn;sub+=16){int lanes=std::min(16,nn-sub);zero(T,lanes);
    for(int k0=0;k0<K;k0+=64){zero(A,lanes);
     for(int k=k0;k<std::min(K,k0+64);++k){
      std::vector<std::pair<U,U>> q{{X+(m*K+k)*4ULL,4},{A,lanes*4ULL}};
      for(int j=0;j<lanes;++j)q.push_back({W+((sub+j)*K+k)*4ULL,4});
      access(q,false);last=r.chipCycle();float products[16],sums[16];
      for(int j=0;j<lanes;++j){products[j]=get(X+(m*K+k)*4ULL)*get(W+((sub+j)*K+k)*4ULL);sums[j]=get(A+j*4ULL);}
      op(lanes);muls+=lanes;
      for(int j=0;j<lanes;++j)sums[j]=sums[j]+products[j];op(lanes);adds+=lanes;
      access({{A,lanes*4ULL}},true);for(int j=0;j<lanes;++j)put(A+j*4ULL,sums[j]);
     }
     access({{A,lanes*4ULL},{T,lanes*4ULL}},false);float sums[16];
     for(int j=0;j<lanes;++j)sums[j]=get(T+j*4ULL)+get(A+j*4ULL);op(lanes);adds+=lanes;
     access({{T,lanes*4ULL}},true);for(int j=0;j<lanes;++j)put(T+j*4ULL,sums[j]);
    }
    access({{T,lanes*4ULL}},false);float sums[16];for(int j=0;j<lanes;++j)sums[j]=get(T+j*4ULL);
    access({{Y+(m*N+n0+sub)*4ULL,lanes*4ULL}},true);for(int j=0;j<lanes;++j)put(Y+(m*N+n0+sub+j)*4ULL,sums[j]);
   }
   rows<<job<<','<<version<<','<<n0<<','<<start<<','<<ready<<','<<last<<','<<r.chipCycle()<<'\n';
  }
  access({{Y,M*N*4ULL}},false);r.store(yhb,mem.data()+Y,M*N*4ULL,"FP16_contract_FP32_SRAM_commit");
  std::ofstream out(std::string(dir)+"/LOWERING.jsonl",std::ios::app);
  out<<"{\"job\":"<<job<<",\"M\":"<<M<<",\"N\":"<<N<<",\"K\":"<<K<<",\"begin\":"<<begin<<",\"complete\":"<<r.chipCycle()<<",\"last_reader\":"<<last<<",\"mul_ops\":"<<muls<<",\"add_ops\":"<<adds<<",\"reduce_ops\":"<<reduces<<",\"events\":"<<events<<",\"compute_cycles\":"<<cycles<<",\"bank_cycles\":"<<banks<<",\"weight_versions\":"<<version<<",\"arithmetic\":\"FP16_contract_K64_partial_FP32\"}\n";
 }
 void run(U xhb,U whb,U yhb,int M,int N,int K,U job,const char*dir){
  if(M<1||M>19||N<1||N>4096||K<1||K>4096||M*K*4ULL>W||M*N*4ULL>mem.size()-Y)throw std::runtime_error("unsupported matrix/capacity");
  U begin=r.chipCycle();r.load(xhb,mem.data()+X,M*K*4ULL,"CPU_expanded_X_to_SRAM");access({{X,M*K*4ULL}},true);
  std::ofstream rows(std::string(dir)+"/MATRIX_TILES.csv",std::ios::app);
  for(int n0=0;n0<N;n0+=64){int nn=std::min(64,N-n0);if(r.chipCycle()<last)throw std::runtime_error("SRAM weight overwrite before last reader");version++;U start=r.chipCycle();r.load(whb+n0*K*4ULL,mem.data()+W,nn*K*4ULL,"CPU_expanded_W_to_SRAM");access({{W,nn*K*4ULL}},true);U ready=r.chipCycle();
   if(M==1){for(int n=0;n<nn;n++){
    zero(A,64);int aligned=K/64*64;
    for(int k=0;k<aligned;k+=16){U xa=X+k*4ULL,wa=W+(n*K+k)*4ULL,aa=A+(k%64)*4ULL;access({{xa,64},{wa,64},{aa,64}},false);last=r.chipCycle();float p[16],v[16];for(int j=0;j<16;j++){p[j]=get(xa+j*4)*get(wa+j*4);v[j]=get(aa+j*4);}op(16);muls+=16;for(int j=0;j<16;j++)v[j]+=p[j];op(16);adds+=16;access({{aa,64}},true);for(int j=0;j<16;j++)put(aa+j*4,v[j]);}
    if(aligned)reduce(A,64);
    zero(T,8);int vec=K/16*16;
    for(int k=aligned;k<vec;k+=16)for(int half=0;half<2;half++){U xa=X+(k+half*8)*4ULL,wa=W+(n*K+k+half*8)*4ULL;access({{xa,32},{wa,32},{T,32}},false);last=r.chipCycle();float p[8],v[8];for(int j=0;j<8;j++){p[j]=get(xa+j*4)*get(wa+j*4);v[j]=get(T+j*4);}op(8);muls+=8;for(int j=0;j<8;j++)v[j]+=p[j];op(8);adds+=8;access({{T,32}},true);for(int j=0;j<8;j++)put(T+j*4,v[j]);}
    if(vec>aligned)reduce(T,8);access({{A,4},{T,4}},false);float sum=get(A)+get(T);op(1);adds++;
    for(int k=vec;k<K;k++){access({{X+k*4ULL,4},{W+(n*K+k)*4ULL,4}},false);last=r.chipCycle();float p=get(X+k*4ULL)*get(W+(n*K+k)*4ULL);op(1);muls++;sum+=p;op(1);adds++;}
    access({{Y+(n0+n)*4ULL,4}},true);put(Y+(n0+n)*4ULL,sum);
   }}else{
    int bk=K<=384?K:(K<1536?(K+1)/2:768);
    for(int m=0;m<M;m++)for(int sub=0;sub<nn;sub+=16){int lanes=std::min(16,nn-sub);bool first=true;
     for(int k0=0;k0<K;k0+=bk){zero(A,lanes);int end=std::min(K,k0+bk);
      for(int kk=k0;kk<end;kk+=2)for(int parity=1;parity>=0;parity--){int k=kk+parity;if(k>=end)continue;std::vector<std::pair<U,U>>q{{X+(m*K+k)*4ULL,4},{A,lanes*4ULL}};for(int j=0;j<lanes;j++)q.push_back({W+((sub+j)*K+k)*4ULL,4});access(q,false);last=r.chipCycle();float p[16],v[16];for(int j=0;j<lanes;j++){p[j]=get(X+(m*K+k)*4ULL)*get(W+((sub+j)*K+k)*4ULL);v[j]=get(A+j*4);}op(lanes);muls+=lanes;for(int j=0;j<lanes;j++)v[j]+=p[j];op(lanes);adds+=lanes;access({{A,lanes*4ULL}},true);for(int j=0;j<lanes;j++)put(A+j*4,v[j]);}
      access({{A,lanes*4ULL}},false);float v[16];for(int j=0;j<lanes;j++)v[j]=get(A+j*4);if(!first){access({{T,lanes*4ULL}},false);for(int j=0;j<lanes;j++)v[j]=get(T+j*4)+v[j];op(lanes);adds+=lanes;}access({{T,lanes*4ULL}},true);for(int j=0;j<lanes;j++)put(T+j*4,v[j]);first=false;
     }
     access({{T,lanes*4ULL}},false);float v[16];for(int j=0;j<lanes;j++)v[j]=get(T+j*4);access({{Y+(m*N+n0+sub)*4ULL,lanes*4ULL}},true);for(int j=0;j<lanes;j++)put(Y+(m*N+n0+sub+j)*4ULL,v[j]);
    }
   }
   rows<<job<<','<<version<<','<<n0<<','<<start<<','<<ready<<','<<last<<','<<r.chipCycle()<<'\n';
  }
  access({{Y,M*N*4ULL}},false);r.store(yhb,mem.data()+Y,M*N*4ULL,"matrix_FP32_SRAM_commit");
  std::ofstream out(std::string(dir)+"/LOWERING.jsonl",std::ios::app);out<<"{\"job\":"<<job<<",\"M\":"<<M<<",\"N\":"<<N<<",\"K\":"<<K<<",\"begin\":"<<begin<<",\"complete\":"<<r.chipCycle()<<",\"last_reader\":"<<last<<",\"mul_ops\":"<<muls<<",\"add_ops\":"<<adds<<",\"reduce_ops\":"<<reduces<<",\"events\":"<<events<<",\"compute_cycles\":"<<cycles<<",\"bank_cycles\":"<<banks<<",\"weight_versions\":"<<version<<"}\n";
 }
};
