from pathlib import Path
import json,re,hashlib,csv,numpy as np
R=Path(__file__).resolve().parent;B=R.parent
ref=np.load(B/'lingbot_step4_vae_20261105_v1/frames_FP32.npy',mmap_mode='r')[0];rows=[];outputs=[]
log=(R/'RUN.log').read_text();statuses=[int(v) for v in re.findall(r'terminate with status = (\d+)',log)]
assert len(statuses)==8 and all(v==0 for v in statuses)
assert json.loads((R/'RUN_EXIT.json').read_text())['returncode']==0
for k in (1,2):
 D=R/f'case{k}';events=json.loads((D/'N00/EVENTS.json').read_text());assert [e['op'] for e in events]==[0,1]
 assert all(e['start_ns']<=e['receive_done_ns']<=e['consumer_ns'] for e in events)
 assert events[0]['consumer_ns']<=events[1]['start_ns']
 data=(D/'N00/output1.bin').read_bytes();a=np.frombuffer(data,np.float32).reshape(ref.shape);assert np.array_equal(a.view(np.uint32),ref.view(np.uint32))
 assert data==(D/'service1/output.bin').read_bytes()
 outputs.append(data)
 n=len((D/'delayInfo.txt').read_text().splitlines());assert n>0
 feedback=list(csv.DictReader((R/f'run/noc_feedback_round{k}.csv').open()));assert len(feedback)==n
 if k==2:assert all(int(f['profile_applied'])==1 for f in feedback)
 domain=list(csv.DictReader((R/f'run/domain_service_round{k}.csv').open()));assert domain and all(int(d['ready'])<=int(d['start'])<=int(d['complete']) for d in domain)
 rows.append(dict(round=k,VAE_raw_fp32_differences=0,VAE_uint8_differences=0,VAE_values=a.size,CFG_scheduler_next_latent='actor hard assertion passed; 2048 values per stage',events=events,NoC_feedback_records=n,all_previous_feedback_applied=(k==2),domain_completion_order_checks=len(domain)))
assert outputs[0]==outputs[1]
assert f"Load {rows[0]['NoC_feedback_records']} delay records." in log
receipt=dict(state='PASS_LIMITED_REPAIRED_CPU_VAE_TARGET_BOUNDARY_CHAIN',rounds=rows,subprocesses_zero=8,target_GPU_calls=0,reference_output_used_for_computation=False,reference_injections=['frozen cond/uncond prediction and scheduler input tile','frozen final latent first temporal slice; remaining39DiTsteps omitted'],uncovered_costs=['CPU native service duration not in target clock','PCIe DMA timing in this target chain','CPU cache/writeback timing','complete operator ISA/perMAC','other120output frames','remaining39DiTsteps'],promotion=False,formal_PK=False,CA_ablation=False)
(R/'ACCEPTANCE_RECEIPT.json').write_text(json.dumps(receipt,indent=2));(R/'STATUS.json').write_text(json.dumps(dict(state=receipt['state'],promotion=False),indent=2))
print(json.dumps(receipt,indent=2))
