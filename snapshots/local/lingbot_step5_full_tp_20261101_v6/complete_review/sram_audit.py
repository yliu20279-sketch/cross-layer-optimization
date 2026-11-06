import pathlib,json,sys,time,math,traceback
R=pathlib.Path(sys.argv[1]);deadline=time.monotonic()+92000
while time.monotonic()<deadline:
 if (R/'DAG_AUDIT.json').exists():break
 if (R/'STATUS.json').exists() and json.loads((R/'STATUS.json').read_text())['state'].startswith('STOPPED'):raise RuntimeError('production failed, no SRAM promotion')
 time.sleep(5)
else:raise TimeoutError('audit wait budget')
checks=[];summary=[]
def ck(n,b):checks.append(dict(name=n,passed=bool(b)));assert b,n
for case in sorted(R.glob('case*')):
 for rank in range(16):
  D=case/('N%02d'%rank);s=json.loads((D/'SRAM_SUMMARY.json').read_text());events=json.loads((D/'EVENTS.json').read_text());sizes=[e['bytes'] for e in events if e['kind']=='HB'];ck('capacity_geometry',s['array_capacity']==4194304 and s['Banks']==8 and s['stripe_bytes']==32 and s['shared_ports_per_bank']==1);ck('bytes',s['read_bytes']==s['write_bytes']==sum(sizes));ck('chunks',s['chunks']==sum((n+65535)//65536 for n in sizes));ck('bank_cycles',s['bank_service_cycles']==sum(2*((n+255)//256) for n in sizes));ck('peak',s['actual_peak_staging_bytes']==min(65536,max(sizes)) and s['actual_peak_staging_bytes']<=4194304);summary.append(dict(case=case.name,rank=rank,bank_service_cycles=s['bank_service_cycles'],read_bytes=s['read_bytes'],write_bytes=s['write_bytes'],peak=s['actual_peak_staging_bytes']))
r=dict(state='PASS_LIMITED_ACTUAL_HB_SRAM_STAGING_BANK_ACCOUNTING',checks=checks,check_count=len(checks),summary=summary,scope='DMA staging into actual SRAM and readback only, no per-MAC/complete software-op cost',research_configuration='32B stripes, bank=(address/32)%8, one shared read/write port per bank; not established canonical port geometry',whole_step5=False);(R/'SRAM_INDEPENDENT_AUDIT.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k not in ['checks','summary']}))
