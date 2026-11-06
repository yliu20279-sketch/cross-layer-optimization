"""One tiny real-backend control probe, never a model/performance comparison."""
from pathlib import Path
import csv
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'control_probe_02'
assert not D.exists(),'preserve prior attempts'
D.mkdir();G=D/'graph';G.mkdir();O=D/'out';O.mkdir()
def write(n,text):(G/n).write_text(text)
write('objects.txt','2\n0 0 0 8192 0 1\n1 15 0 4096 0 0\n')
write('requests.txt','1\n0 diagnostic_probe\n')
write('rr_map.txt','0 0 0\n0 1 1\n15 0 0\n')
write('ca_map.txt','0 0 1\n0 1 0\n15 0 0\n')
write('sram.txt','4194304\n'*16);write('timing.txt','1 1\n')
write('empty.trace','')
def region(i,rank,kind,parents,segments,src=-1,dst=-1,nbytes=0):
    fields=[i,rank,0,kind,-1,src,dst]+[0]*9+[i,0,nbytes,len(parents)]+parents+[len(segments)]+[x for s in segments for x in s]
    return ' '.join(map(str,fields))
rows=[region(0,0,0,[],[[4090,6,0,0],[4104,16,0,0]]),
      region(1,0,2,[0],[],0,1,1600),region(2,0,2,[0],[],0,15,1500),
      region(3,15,0,[1,2],[[0,32,1,1]])]
write('regions.txt','4\n'+'\n'.join(rows)+'\n')
original=json.loads((ROOT/'evidence/NATIVE_SOURCE_INPUTS.json').read_text())
launch=json.loads(next(x['text'] for x in original if x['path'].endswith('backend_launch.json')))
binary=ROOT/'runtime/build_02/native_live'
cmd=list(launch['command']);cmd[0]=str(binary);cmd[cmd.index('-I')+1]=str(G/'empty.trace')
env={'PATH':'/usr/bin:/bin','POPNET_COUPLED':'1','POPNET_STATS_DIR':str(O),'POPNET_STATS_WINDOW_CYCLES':'100000',
     'HB_GRAPH':str(G),'HB_OUT':str(O),'HB_RAM_CONFIG':launch['controls']['HB_RAM_CONFIG'],
     'P0_OBJECTS':str(G/'objects.txt'),'P0_REQUESTS':str(G/'requests.txt'),'P0_MODEL_DTYPE':'F16',
     'P0_TRACE_CLASS':'eval','P0_CA_MAP':str(G/'ca_map.txt'),'P0_LINK_CONTROL':'project_dynamic',
     'P0_LINK_INTERVAL_NS':'10','P0_LINK_SWITCH_NS':'3'}
(D/'LAUNCH.json').write_text(json.dumps({'command':cmd,'environment':env,'scope':'tiny diagnostic only'},indent=2))
with (D/'stdout.log').open('w') as out,(D/'stderr.log').open('w') as err:
    process=subprocess.run(cmd,env=env,cwd=D,stdout=out,stderr=err,timeout=45)
assert process.returncode==0,('backend probe failed; inspect preserved stderr',process.returncode)
summary=json.loads((O/'summary.json').read_text());control=json.loads((O/'live_controls.json').read_text())
events=list(csv.DictReader((O/'events.csv').open()))
issued=[e for e in events if e['event']=='DRAM_ISSUE']
assert sorted((int(e['address']),int(e['bytes'])) for e in issued if e['write']=='0')==[(8,16),(8186,6)]
assert summary['transactions']==summary['callbacks']==3 and summary['regions']==4
assert control['mapped_transactions']==3 and control['link_switches']>=1 and control['injection_bytes']>=3100
receipt={'status':'PASS_REAL_RAMULATOR_POPNET_CONTROL_PROBE_ONLY','returncode':process.returncode,
         'summary':summary,'controls':control,'actual_read_addresses':[[8,16],[8186,6]],
         'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
         'artifacts':{str(p.relative_to(D)):hashlib.sha256(p.read_bytes()).hexdigest() for p in D.rglob('*') if p.is_file()},
         'native_control_probe_runs':1,'model_forwards':0,'formal_performance_runs':0,
         'no_author_HiBand_equivalence':True,'no_numeric_payload_in_this_timing_probe':True}
(ROOT/'evidence/REAL_CONTROL_PROBE_02.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps({'status':receipt['status'],'transactions':summary['transactions'],'switches':control['link_switches'],'formal_performance_runs':0}))
