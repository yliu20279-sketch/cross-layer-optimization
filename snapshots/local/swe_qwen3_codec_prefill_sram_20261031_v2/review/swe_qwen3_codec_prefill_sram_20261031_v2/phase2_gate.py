import os,sys,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/('case'+os.environ['SWE_RUN_ROUND']);run=Path.cwd().parent
assert json.loads((D/'CPU_PASS.json').read_text())['state']=='PASS_ACTUAL_CPU_CODEC_BF16_GATE'
assert json.loads((D/'N00/RESULT.json').read_text())['state']=='PASS_CPU_EXPANSION_CONSUMED_AND_FP32_RETURNED'
assert (D/'CPU_RAW_FP32.bin').read_bytes()==(D/'N00/actual_fp32.bin').read_bytes()
for n in ['bench.txt','transport_bench.txt','domain_service_round'+os.environ['SWE_RUN_ROUND']+'.csv','noc_feedback_round'+os.environ['SWE_RUN_ROUND']+'.csv']:shutil.copy2(run/n,D/n)
assert (D/'bench.txt').stat().st_size>0
rc=subprocess.run(sys.argv[1:]).returncode
assert rc==0,rc
shutil.copy2(run/'delayInfo.txt',D/'delayInfo.txt');shutil.copy2(Path.cwd()/'routing_xy.csv',D/'routing_xy.csv')
assert len((D/'bench.txt').read_text().splitlines())==len((D/'delayInfo.txt').read_text().splitlines())
(D/'PHASE2_PASS.json').write_text(json.dumps(dict(state='PASS_LIMITED_CODEC_GATE_SRAM_REPLAY',round=int(os.environ['SWE_RUN_ROUND']))))
