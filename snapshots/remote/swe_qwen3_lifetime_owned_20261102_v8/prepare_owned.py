"""Prepare an isolated candidate; never launches a native full-model run."""
import hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;V=R.parent/'swe_qwen3_lifetime_20261101_v6'
assert not (R/'CANDIDATE_PREPARED.json').exists()
for name in ['cpu_services.h','cpu_probe.cpp','preflight.py','cache_evict.h']:
 shutil.copy2(V/name,R/name)
p=R/'cpu_services.h';s=p.read_text();needle=' else throw std::runtime_error("unknown CPU software service");';assert needle in s
s=s.replace(needle,''' else if(kind==27||kind==28){if(!in.empty()||out.size()!=32)throw std::runtime_error("owner descriptor");lifetime_allocator.owner(a,b,kind==27,(U*)out.data());}
 else if(kind==29){if(!in.empty()||out.size()!=32)throw std::runtime_error("inspect descriptor");lifetime_allocator.inspect((U*)out.data());}
'''+needle);p.write_text(s)
s=(V/'host.cpp').read_text();needle=' SimRoiEnd();service_log.flush();';assert s.count(needle)==1
cleanup=''' // The final numeric result does not release KV session ownership.
 while(true){
  std::uint64_t h[8];receive(h,64);
  if(h[0]==6){
   std::uint64_t state[4];lifetime_allocator.inspect(state);
   if(h[1]!=0x51424d4bULL||state[0]||state[1]||state[2]||state[3]!=(208ULL<<20))throw std::runtime_error("teardown with live ownership");
   std::uint64_t ack[8]={6,0x51424d4bULL,0,0,0,208ULL<<20,0,0};send(ack,64);
   std::ofstream(out+"/CPU_TEARDOWN_PASS.json")<<"{\\"state\\":\\"PASS_EMPTY_ARENA_ACK\\"}";break;
  }
  if(h[0]!=5||(h[1]!=25&&h[1]!=26&&h[1]!=28&&h[1]!=29)||h[2]||h[3]>(128ULL<<20))throw std::runtime_error("non-cleanup command after final result");
  std::vector<char>in,outbuf(h[3]);service(h,in,outbuf);send(outbuf.data(),outbuf.size());
  service_log<<"{\\"kind\\":"<<h[1]<<",\\"input_bytes\\":0,\\"output_bytes\\":"<<h[3]<<"}\\n";
 }
'''
(R/'host.cpp').write_text(s.replace(needle,cleanup+needle))
s=(V/'gateway.cpp').read_text();needle=' std::uint64_t stop[8]={9};';assert s.count(needle)==1
cleanup=''' while(true){
  std::uint64_t h[8];w.receive(0,h,64);
  if(h[0]==6){
   if(h[1]!=0x51424d4bULL)throw std::runtime_error("teardown magic");
   w.send(48,h,64);std::uint64_t ack[8];w.receive(48,ack,64);
   if(ack[0]!=6||ack[1]!=h[1]||ack[2]||ack[3]||ack[4]||ack[5]!=(208ULL<<20)||ack[6]||ack[7])throw std::runtime_error("teardown acknowledgement");
   w.send(0,ack,64);break;
  }
  if(h[0]!=5||(h[1]!=25&&h[1]!=26&&h[1]!=28&&h[1]!=29)||h[2]||h[3]>(128ULL<<20))throw std::runtime_error("invalid post-result command");
  w.send(48,h,64);w.forward(48,0,h[3]);
 }
'''
(R/'gateway.cpp').write_text(s.replace(needle,cleanup+needle))
subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','owner_controls.cpp','-o','owner_controls'],cwd=R,check=True)
with (R/'OWNER_CONTROLS.log').open('w') as f:subprocess.run([str(R/'owner_controls')],stdout=f,cwd=R,check=True)
state=dict(state='SOURCE_CANDIDATE_OWNER_CONTROLS_PASSED_NOT_NATIVE',CPU_services=[24,25,26,27,28,29],native_runs=0,full_steps_1_7=False,remaining=['root bridge finalize binding','full CPU replay and independent ownership audit','positive and negative native endpoint smoke','full run after portable baseline passes'])
(R/'CANDIDATE_PREPARED.json').write_text(json.dumps(state,indent=2));print(json.dumps(state))
