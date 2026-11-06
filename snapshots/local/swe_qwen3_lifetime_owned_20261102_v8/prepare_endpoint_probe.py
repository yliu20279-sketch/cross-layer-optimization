import json,shutil,subprocess,os,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;V=B/'swe_qwen3_continuous_portable_20261101_v7';P=R/'endpoint_positive'
P.mkdir(exist_ok=False)
for name in ['libfull.so','endpoint_probe.py','noc_v3_6.gv']:
 src=(V if name=='noc_v3_6.gv' else R)/name;shutil.copy2(src,P/name)
(P/'data').mkdir()
for name in ['shards.txt','parameters.txt','prefill_cos.bin','prefill_sin.bin','decode_cos.bin','decode_sin.bin']:
 os.symlink(str(V/'data'/name),str(P/'data'/name))
for name in ['EXP16_ALL_FP32.bin','SILU_ALL_BF16.bin']:os.symlink(str(V/name),str(P/name))
for phase in ['prefill','decode']:
 for suffix in ['input','gold']:(P/'data'/(phase+'_'+suffix+'.bin')).write_bytes(bytes(range(32)))
s=(R/'host.cpp').read_text().replace('PASS_FULL_TWO_LAYER_PREFILL_DECODE','PASS_ENDPOINT_SMOKE_ONLY')
(P/'host.cpp').write_text(s)
s=(R/'gateway.cpp').read_text().replace('std::uint64_t stop[8]={9};for(int i=1;i<16;i++)w.send(i,stop,64);','// Endpoint smoke: only root/CPU/gateway and one HB are instantiated.')
assert 'for(int i=1;i<16;i++)' not in s
(P/'gateway.cpp').write_text(s.replace('PASS_FULL_LAYER_SERVICE','PASS_ENDPOINT_GATEWAY_SMOKE'))
for name in ['CPU','GATEWAY']:
 cmd=json.loads((R/(name+'_BUILD_COMMAND.json')).read_text())
 # Keep includes and allocator source resolving to the reviewed parent candidate.
 cmd=[str(P/'host.cpp') if x==str(R/'host.cpp') else str(P/'gateway.cpp') if x==str(R/'gateway.cpp') else str(P/'host') if x==str(R/'host') else str(P/'gateway') if x==str(R/'gateway') else x for x in cmd]
 cmd.insert(1,'-I'+str(R))
 with (P/(name+'_BUILD.log')).open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=600)
cfg=json.loads((V/'unified_full.yml').read_text());cfg['phase1']=cfg['phase1'][:4]
for task in cfg['phase1']:
 task['cmd']=task['cmd'].replace(str(V),str(P));task['args']=[x.replace(str(V),str(P)).replace(str(P/'worker.py'),str(P/'endpoint_probe.py')) for x in task['args']]
task=cfg['phase2'][0];task['cmd']=task['args'][1];task['args']=task['args'][2:];task['args']=[x.replace(str(V),str(P)) for x in task['args']]
(P/'probe.yml').write_text(json.dumps(cfg,indent=2))
(P/'PROBE_FREEZE.json').write_text(json.dumps({n:hashlib.sha256((P/n).read_bytes()).hexdigest() for n in ['host.cpp','gateway.cpp','host','gateway','libfull.so','endpoint_probe.py','probe.yml']},indent=2))
print('PREPARED_ENDPOINT_ONLY',P)
