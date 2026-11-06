#pragma once
#include <map>
#include <cstdint>
#include <stdexcept>
#include <vector>
// First-fit CPU allocator for the explicit32..240MiB activation arena.
// Remaining reader counts are a preregistered finite-DAG contract, not a predictor.
class LifetimeAllocator {
 using U=std::uint64_t;
 struct Live {U address,bytes,version,remaining,pins;};
 std::map<U,U> free_blocks{{32ULL<<20,208ULL<<20}};
 std::map<U,Live> live;
 U generation=0,live_bytes=0,peak_bytes=0;
public:
 void allocate(U bytes,U id,U readers,U*y){
  if(!bytes||bytes>(208ULL<<20)||live.count(id))throw std::runtime_error("allocator size or duplicate node");
  bytes=(bytes+31)&~U(31);auto block=free_blocks.begin();while(block!=free_blocks.end()&&block->second<bytes)++block;
  if(block==free_blocks.end())throw std::runtime_error("activation arena exhausted");
  U address=block->first,left=block->second-bytes;free_blocks.erase(block);if(left)free_blocks[address+bytes]=left;
  Live v{address,bytes,++generation,readers,0};live[id]=v;live_bytes+=bytes;if(live_bytes>peak_bytes)peak_bytes=live_bytes;
  y[0]=address;y[1]=v.version;y[2]=live_bytes;y[3]=peak_bytes;
 }
 void read_complete(U id,U version,U zero_reader_commit,U*y){
  auto it=live.find(id);if(it==live.end()||it->second.version!=version)throw std::runtime_error("stale allocation version");
  auto&v=it->second;
  if(zero_reader_commit){if(v.remaining)throw std::runtime_error("premature release");}
  else{if(!v.remaining)throw std::runtime_error("extra reader");--v.remaining;}
  y[0]=v.address;y[1]=v.version;y[2]=v.remaining;y[3]=0;
 }
 void barrier(U capacity,U*y){
  std::vector<U> ids;for(auto&v:live)if(!v.second.remaining&&!v.second.pins)ids.push_back(v.first);
  if(ids.size()>capacity)throw std::runtime_error("barrier output capacity");
  y[0]=ids.size();U j=0;
  for(U id:ids){
   auto it=live.find(id);auto v=it->second;y[4+2*j]=id;y[5+2*j++]=v.version;
   U a=v.address,n=v.bytes;live_bytes-=n;live.erase(it);auto next=free_blocks.lower_bound(a);
   if(next!=free_blocks.begin()){auto prev=std::prev(next);if(prev->first+prev->second==a){a=prev->first;n+=prev->second;free_blocks.erase(prev);}}
   next=free_blocks.lower_bound(a);if(next!=free_blocks.end()&&a+n==next->first){n+=next->second;free_blocks.erase(next);}free_blocks[a]=n;
  }y[1]=live_bytes;y[2]=peak_bytes;y[3]=generation;
 }
 void owner(U id,U version,bool retain,U*y){
  auto it=live.find(id);if(it==live.end()||it->second.version!=version)throw std::runtime_error("stale owner version");
  auto&v=it->second;
  if(retain){if(v.pins==~U(0))throw std::runtime_error("owner overflow");++v.pins;}
  else{if(!v.pins)throw std::runtime_error("owner underflow");--v.pins;}
  y[0]=v.address;y[1]=v.version;y[2]=v.pins;y[3]=0;
 }
 void inspect(U*y){
  U pins=0,total=0,end=32ULL<<20;for(auto&v:live)pins+=v.second.pins;
  for(auto&b:free_blocks){if(b.first<end||b.first+b.second>(240ULL<<20))throw std::runtime_error("free arena overlap");end=b.first+b.second;total+=b.second;}
  if(total+live_bytes!=(208ULL<<20))throw std::runtime_error("arena accounting");
  if(live.empty()&&(free_blocks.size()!=1||free_blocks.begin()->first!=(32ULL<<20)))throw std::runtime_error("arena not coalesced");
  y[0]=live.size();y[1]=live_bytes;y[2]=pins;y[3]=total;
 }
};
static LifetimeAllocator lifetime_allocator;
