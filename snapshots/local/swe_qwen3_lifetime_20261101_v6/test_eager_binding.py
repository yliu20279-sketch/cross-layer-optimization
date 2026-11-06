import json,subprocess,sqlite3,os,sys
from pathlib import Path
R=Path(__file__).resolve().parent;S=R/'sniper_isa_candidate';tunable=json.loads((R/'GLIBC_XSAVE_AUDIT.json').read_text())['GLIBC_TUNABLES'];results=[];suffix=sys.argv[1] if len(sys.argv)>1 else ''
for mode in ['positive','negative']:
 D=R/('isa_eager_'+mode+suffix);D.mkdir(exist_ok=False);args=[str(R/('isa_'+mode))]+([str(R)] if mode=='positive' else [])+[str(D/'FUNCTIONAL_PASS.txt')]
 cmd=[str(S/'run-sniper'),'-n','4','-c','gainestown','-c',str(R.parent/'swe_qwen3_host_boundary_20261027_v1/cpu_overlay.cfg'),'--roi','--no-cache-warming','-d',str(D),'--']+args
 with (R/('ISA_EAGER_'+mode.upper()+suffix+'.log')).open('w') as f:c=subprocess.run(cmd,env=dict(os.environ,GLIBC_TUNABLES=tunable,LD_BIND_NOW='1'),stdout=f,stderr=subprocess.STDOUT,timeout=180)
 assert c.returncode==0 and (D/'FUNCTIONAL_PASS.txt').exists()
 db=sqlite3.connect(str(D/'sim.stats.sqlite3'));rows=db.execute("select n.objectname,n.metricname,v.value from [values] v join names n using(nameid) join prefixes p using(prefixid) where p.prefixname='roi-end' and v.core=0 and n.objectname in ('decoded_isa_nehalem_ok','decoded_isa_nehalem_rejected')").fetchall();db.close();assert rows
 results.append(dict(mode=mode,rejected=[dict(name=n,count=v) for obj,n,v in rows if obj=='decoded_isa_nehalem_rejected' and v],supported=sum(v for obj,n,v in rows if obj=='decoded_isa_nehalem_ok')))
passed=not results[0]['rejected'] and any(v['name']=='AVX_VXORPS' for v in results[1]['rejected'])
out=dict(state='PASS_LIMITED_PORTABLE_ROI_ISA_AND_AVX_REJECTION' if passed else 'NOT_PROMOTED_EAGER_BINDING',GLIBC_TUNABLES=tunable,LD_BIND_NOW='1',results=results,scope='steady-state ROI; dynamic binding is explicit setup before ROI, as model/math mmap setup already was; no claim for all pre-ROI ISA or startup latency',full_steps_1_7=False)
(R/('EAGER_BINDING_AUDIT'+suffix+'.json')).write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
