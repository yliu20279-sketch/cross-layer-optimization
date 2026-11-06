import json,sys
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent
sys.path.insert(0,str(B/'swe_qwen3_bf16_functional_v1_20261026'))
sys.path.insert(0,str(B/'swe_qwen3_host_boundary_20261027_v1'));from boundary_service_v2 import Link,FS_NS
from coupled_adapter_v2 import CompactLink
old=Link();new=CompactLink();comparisons=[]
for i,n in enumerate([1,31,32,128,255,256,257,4096,65535,65536]*2):
 direction='H2D' if i%2==0 else 'D2H';ready=i*137*FS_NS;payload=bytes([i])*n;a=old.issue(direction,ready,payload,i);b=new.issue(direction,ready,payload,i)
 for key in ['id','direction','queue','credit','lease','ready_fs','issue_fs','iommu_done_fs','arrival_fs','bytes','sha256']:assert a[key]==b[key],(i,key,a[key],b[key])
 old.commit(a,a['arrival_fs']+700*FS_NS);new.commit(b,b['arrival_fs']+700*FS_NS);assert old.credits==new.credits and old.free==new.free;comparisons.append(dict(bytes=n,direction=direction,exact=True))
assert len(old.packets)==new.packet_count
negative=[]
for kind,cls in [('enumerated',Link),('compact',CompactLink)]:
 x=cls()
 for i in range(64):x.issue('H2D',0,b'x',i)
 try:x.issue('H2D',0,b'x',64)
 except RuntimeError:negative.append(kind+'_credit65_rejected')
 else:raise AssertionError('pending credit overwritten')
 x=cls();a=x.issue('H2D',0,b'x'*257,1)
 try:x.commit(a,a['arrival_fs']-1)
 except RuntimeError:negative.append(kind+'_early_commit_rejected')
 else:raise AssertionError('early commit accepted')
import torch
view=torch.arange(6,dtype=torch.float32).reshape(2,3).T;packed=view.contiguous();wrong=torch.as_strided(packed,view.shape,view.stride());assert not torch.equal(wrong,view) and torch.equal(packed,view)
out=dict(state='PASS_ADAPTATION_CONTRACTS',packet_run_vs_enumerated_descriptor_checks=len(comparisons),packets=len(old.packets),negative_controls=negative,view_bug_counterexample_different=int((wrong!=view).sum()),correct_contiguous_view_exact=True,scope='proxy equivalence and layout regression, not new workload execution or timing calibration')
(R/'ADAPTATION_CHECKS.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
