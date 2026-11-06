from pathlib import Path
import json
HERE=Path(__file__).resolve().parent
s=(HERE/'audit_local_stages.py').read_text()
s=s.replace("R=HERE/'unified_layers'", "R=HERE/'unified_layers_fifo_v2'")
s=s.replace("state='PASS_LIMITED_STAGE_AND_RECORDED_DEPENDENCY_AUDIT_CPU_ACCEPTANCE_FAILED'", "state='PASS_LIMITED_PHASE1_TWO_LAYER_CPU_RECEIPTS_VERIFIED'")
s=s.replace("assert cpu_missing==['decode'] and not out['CPU_PASS']", "assert cpu_missing==[] and out['CPU_PASS']\nfor phase in ['prefill','decode']:\n v=next(v for v in files if v['phase']==phase and v['layer']==1 and v['stage']=='output')\n assert (R/'cpu_data'/(phase+'_ACTUAL.bin')).read_bytes()==(D/v['path']).read_bytes()\nassert j(R/'cpu_data/CPU_PASS.json')['state']=='PASS_LAYER1_PREFILL_DECODE'\nassert 'abort due to EOF' not in (R/'run3/proc_r1_p1_t0/cpu.log').read_text()")
s=s.replace('First run numeric stage audit only. Decode FIFO EOF prevents CPU end-to-end acceptance.', 'FIFO v2 CPU prefill/decode receipts verified; phase2 remains pending.')
s=s.replace("HERE/'LOCAL_STAGE_AUDIT.json'", "HERE/'LOCAL_PHASE1_V2_AUDIT.json'")
exec(compile(s,str(HERE/'audit_local_stages.py'),'exec'),{'__file__':str(HERE/'audit_local_stages.py')})
