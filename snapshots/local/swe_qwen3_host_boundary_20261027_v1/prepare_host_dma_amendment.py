from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent
s=(R/'boundary_service.py').read_text()
s+='''
class HostDMAService:
 def __init__(self):self.free_fs=0;self.rows=[]
 def serve(self,direction,ready,payload_bytes):
  # Explicit constant-host-DRAM proxy inherited from the CPU overlay.
  # One shared read/write serializer,12.8B/ns,60ns access latency per chunk.
  start=max(ready,self.free_fs);service=ceildiv(payload_bytes*10000000,128)
  done=start+60*FS_NS+service;self.free_fs=done
  self.rows.append(dict(direction=direction,bytes=payload_bytes,ready_fs=ready,start_fs=start,service_fs=service,done_fs=done,latency_fs=60*FS_NS))
  return done
'''
(R/'boundary_service_v2.py').write_text(s)
s=(R/'run_coupled.py').read_text().replace("D=R/'coupled_attempt1'","D=R/'coupled_attempt2'").replace('from boundary_service import Link,LeasePool,negative_controls,FS_NS,ceildiv','from boundary_service_v2 import Link,LeasePool,negative_controls,FS_NS,ceildiv,HostDMAService').replace("R/'COUPLED_FREEZE.json'","R/'COUPLED_FREEZE_v2.json'")
s=s.replace('link=Link();pool=LeasePool();host_events=[]','link=Link();pool=LeasePool();host_events=[];host_dma=HostDMAService()')
s=s.replace("descriptor=link.issue('H2D',ready,chunk,lease)","source_ready=host_dma.serve('DMA_host_read',ready,len(chunk));descriptor=link.issue('H2D',source_ready,chunk,lease)")
s=s.replace("rt.sync_fs(desc['arrival_fs'],'D2H_packets_arrived')","rt.sync_fs(desc['arrival_fs'],'D2H_packets_arrived');destination_ready=host_dma.serve('DMA_host_write',rt.now*FS_NS,512);rt.sync_fs(destination_ready,'D2H_host_DRAM_committed')")
s=s.replace("dump(D/'LINK_DESCRIPTORS.json',link.descriptors)","dump(D/'HOST_DMA_MEMORY.json',host_dma.rows);dump(D/'LINK_DESCRIPTORS.json',link.descriptors)")
s=s.replace("stats=rt.finish();assert not torch.cuda.is_initialized()","np.save(D/'new_router_FP32.npy',value.numpy());np.save(D/'new_router_BF16_bits.npy',encoded.view(torch.uint16).numpy());stats=rt.finish();assert not torch.cuda.is_initialized()")
s=s.replace("timing_scope='gainestown-derived cold ROI plus configured PCIe proxy and native N0/CH0; not physically calibrated or full router'","host_DMA_memory='shared12.8GB/s60ns/chunk constant proxy from explicit CPU overlay',timing_scope='gainestown-derived cold ROI plus host DMA DRAM proxy plus PCIe and native N0/CH0; not physically calibrated or full router'")
(R/'run_coupled_v2.py').write_text(s)
amendment=dict(reason='First coupling omitted host DMA source/read and destination/write DRAM service; original results preserved, not complete boundary certification',
 policy='Add shared12.8GB/s60ns/chunk explicit experimental host DRAM proxy; CPU overlay unchanged; not a V3.6 measured fact',
 new_attempt='coupled_attempt2, max300s, same input/output and strict comparison, no extra GPU/agent',
 files={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in ['PROTOCOL.json','boundary_service_v2.py','run_coupled_v2.py']})
(R/'HOST_DMA_AMENDMENT.json').write_text(json.dumps(amendment,indent=2))
(R/'COUPLED_FREEZE_v2.json').write_text(json.dumps(amendment['files'],indent=2))
