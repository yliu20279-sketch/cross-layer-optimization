import json,ast,hashlib
from pathlib import Path
BASE=Path(__file__).resolve().parent;R=BASE.parent/'swe_qwen3_continuous_lowering_20261031_v3'
p=R/'integrated_adapter.py';s=p.read_text();store='self.ck(self.um.um_store(320*2**20,xf.ctypes.data,xf.nbytes));'
assert s.count(store)==1;s=s.replace(store,'');s=s.replace("xf=self.codec.decode(xx).numpy();wf=",'xf=self.codec.decode(xx).numpy();'+store+'wf=');ast.parse(s);p.write_text(s)
p=R/'validate_lowering.py';s=p.read_text();needle="assert len(all_lower)==759";assert needle in s
s=s.replace(needle,'''assert len(all_lower)==759
 gates=[json.loads(line) for line in (D/'IMMEDIATE_FP32_GATES.jsonl').read_text().splitlines()];assert len(gates)==759 and all(v['exact'] for v in gates) and [v['sequence'] for v in gates]==list(range(1,760))
 io_count=0;io_cycles=0
 for rank in range(16):
  Q=D if rank==0 else D/('N%02d'%rank);io=list(csv.DictReader((Q/'IO_SRAM_GATES.csv').open()));assert io
  previous=0
  for v in io:
   n,start,done=map(int,[v['bytes'],v['start'],v['complete']]);assert 0<n<=65536 and previous<=start and done-start==(n+255)//256;previous=done;io_count+=1;io_cycles+=done-start
 big=[v for v in services if v['input_bytes']+v['output_bytes']+196608>4*2**20];assert big and all(v.get('streamed_HB') and v.get('max_staging_bytes')==65536 for v in big)
 root_tx=list(csv.DictReader((D/'npusim_dram_transactions_0_0.csv').open()));labels={v['label'] for v in root_tx};assert {'streamed_original_BF16_weight','BF16_weight_codec_actual_HB_reader','CPU_expanded_weight_streamed_HB'}<=labels
''')
s=s.replace("CPU_software_calls=len(services),", "CPU_software_calls=len(services),immediate_FP32_gates=len(gates),IO_SRAM_gates=io_count,IO_SRAM_cycles=io_cycles,");ast.parse(s);p.write_text(s)
protocol=json.loads((R/'PROTOCOL.json').read_text());protocol['previous_state']='STOPPED_FOR_SRAM_STREAMING_AMENDMENT';(R/'PROTOCOL.json').write_text(json.dumps(protocol,indent=2))
for n in ['peer.py','integrated_adapter.py','validate_lowering.py']:ast.parse((R/n).read_text())
out=dict(state='BUILT_STREAMED_HB_CANDIDATE',CPU_binary_sha256=hashlib.sha256((R/'host').read_bytes()).hexdigest(),CPU_software_unchanged=True,FP32_primitive_header_sha256=hashlib.sha256((R/'sram_matrix.h').read_bytes()).hexdigest(),stream_bytes_max=65536,SRAM_max_compute_plus_IO_control=3653632,SRAM_capacity=4194304,immediate_FP32_gate=True)
(R/'STREAM_CANDIDATE_READY.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
