import json,pathlib,csv,re,sqlite3
R=pathlib.Path(__file__).resolve().parent
checks=[]
for k,branch in [(1, 'cond'), (2, 'cond')]:
 D=R/f'case{k}';N=D/'N00'
 assert json.loads((D/'CPU_PASS.json').read_text())['state'].startswith('PASS')
 gate=json.loads((N/'GATE.json').read_text())
 assert gate['identity']['cfg']==branch
 assert gate['consumer_start_ns']>=max(gate['completed'].values())
 for typ,ref in [('F32','F32_reference'),('BF16','GPU')]:
  assert (N/f'K_{typ}.bin').read_bytes()==(D/f'CPU_K_{typ}.bin').read_bytes()==(R/'data'/branch/f'K_{ref}.bin').read_bytes()
 clocks=list(csv.DictReader((R/'run'/f'clock_round{k}.csv').open()))
 domains=list(csv.DictReader((R/'run'/f'domain_service_round{k}.csv').open()))
 assert any(float(x['clock_ratio'])==2.5 for x in clocks)
 assert domains and all(float(x['complete'])>=float(x['start'])>=float(x['ready']) for x in domains)
 db=sqlite3.connect(D/'sim.stats.sqlite3')
 db.close()
 checks.append(dict(branch=branch,fp32_elements=128,bf16_gpu_elements=128,
                    clock_records=len(clocks),domain_records=len(domains),gate=gate))
codes=[int(x) for x in re.findall(r'terminate with status = (\d+)',(R/'RUN.log').read_text())]
assert len(codes)==10 and all(x==0 for x in codes),codes
result=dict(state='PASS_LIMITED_DUAL_CFG_K_SERVICE',branches=checks,
 limits=['single K projection per branch','CPU and writeback completion acknowledged at receiver time; exact issue time retained in Sniper log',
         'PCIe model custom serialized queue0, configured deterministic service',
         'NoC live receive uses domain synchronization and second-pass PopNet feedback; no packet-level physical PCIe validation'],
 whole_step5=False)
(R/'INDEPENDENT_AUDIT.json').write_text(json.dumps(result,indent=2))
print(result['state'])
