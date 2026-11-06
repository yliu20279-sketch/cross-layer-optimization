"""Isolated natural full-block experiment. Never mutates historical directories."""
import collections,csv,hashlib,importlib.util,json,os,random,re,shutil,subprocess,sys,time,traceback
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;B=Path('/mnt/sda1/h3240101068');SRC=B/'selector_all_moe_formula_20261022_v1';NATIVE=B/'selector_fp16_joint_native_20261020_v1/native_joint'
FILES=('regions.txt','rr_map.txt','identity.txt','timing.txt','sram.txt');DESC=('RR4','RR16','RR64','PHASE4','HASH4','XOR4');P=json.loads((R/'EXECUTION_PROTOCOL.json').read_text());START=time.monotonic();COUNT=0
MASK=(1<<64)-1

def read(p):return json.loads(Path(p).read_text())
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.writing');tmp.write_text(json.dumps(x,indent=2)+'\n');os.replace(tmp,p)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8388608),b''):h.update(b)
 return h.hexdigest()
def guard():assert time.monotonic()-START<P['total_seconds'],'total budget'
def bank(f):return ((int(f)>>2)&3)*4+((int(f)>>4)&3)
def splitmix(q):
 q=(q+0x9e3779b97f4a7c15)&MASK;q=((q^(q>>30))*0xbf58476d1ce4e5b9)&MASK;q=((q^(q>>27))*0x94d049bb133111eb)&MASK;return q^(q>>31)
def clean():return {k:v for k,v in os.environ.items() if not k.startswith(('HB_','POPNET_','LD_','RAMULATOR','COMMAND_TRACE'))}
def source(model,layer,group):return SRC/('matrix_target_fp16' if model=='qwen3' else 'matrix')/model/('layer_%02d'%layer)/group
def key(model,layer,group):return f'{model}_l{layer:02d}_{group}'
def table(p):
 a=np.loadtxt(p,dtype=np.int64);return {(int(k),int(v)):int(f) for k,v,f in a}
def write_table(p,q):
 with Path(p).open('w') as f:
  for (k,v),d in sorted(q.items()):f.write(f'{k} {v} {d}\n')
def model_data(model,layer):
 src=source(model,layer,'N_DEV');asset=src/'assets'/model;objs=read(asset/'objects_complete.json')['objects'];weights=[o for o in objs if o['role']=='FP16_weight' and not o['name'].startswith('router_')]
 keys=[];tensors=[];byid={};ranks=[]
 for o in weights:
  start=len(keys);n=(o['reserved_bytes']+4095)//4096;ids=list(range(start,start+n));keys.extend((o['partition'],o['address']//4096+i) for i in range(n));tensors.append(ids);byid[o['id']]=len(tensors)-1;ranks.extend([o['partition']]*n)
 inv={k:i for i,k in enumerate(keys)};h=np.zeros(len(keys),dtype=np.int64);bindings=read(asset/'tile_bindings.json');dag=read(asset/'canonical_DAG.json');depth={}
 for n in dag['nodes']:depth[n['id']]=0
 for _ in range(len(depth)):
  changed=False
  for a,b in dag['edges']:
   v=depth[a]+1
   if depth[b]<v:depth[b]=v;changed=True
  if not changed:break
  assert _<len(depth)-1,'DAG cycle'
 waves=collections.defaultdict(list)
 for t in bindings:
  if t['weight_object'] in byid:
   idx=byid[t['weight_object']];h[tensors[idx]]+=1;waves[depth[t['original_weight_read_node']]].append(idx)
 pairs=collections.Counter()
 for ids in waves.values():
  for a in range(len(ids)):
   for b in range(a+1,len(ids)):
    if ids[a]!=ids[b] and ranks[tensors[ids[a]][0]]==ranks[tensors[ids[b]][0]]:pairs[tuple(sorted((ids[a],ids[b])))]+=1
 # Sparse page pairs at same tensor-local page offset, structural proxy only.
 adj=[[] for _ in keys]
 for (a,b),w in pairs.items():
  for u,v in zip(tensors[a],tensors[b]):adj[u].append((v,w));adj[v].append((u,w))
 pools=collections.defaultdict(list)
 for k,p in keys:pools[k].append(p)
 capacities={k:collections.Counter(bank(f) for f in frames) for k,frames in pools.items()}
 return dict(model=model,layer=layer,src=src,asset=asset,objects=objs,keys=keys,tensors=tensors,ranks=np.array(ranks),h=h,adj=adj,pools=pools,capacity=capacities)
def score(d,labels,ca=True):
 loads=collections.Counter()
 for i,b in enumerate(labels):loads[int(d['ranks'][i]),int(b)]+=int(d['h'][i])
 heat=sum(v*v for v in loads.values());conf=sum(w for i,es in enumerate(d['adj']) for j,w in es if j>i and labels[i]==labels[j]);return (conf,heat) if ca else (heat,)
def materialize(d,labels,base):
 q=base.copy();free=collections.defaultdict(list);need=collections.defaultdict(list)
 for i,k in enumerate(d['keys']):
  if bank(base[k])!=int(labels[i]):free[k[0],bank(base[k])].append(base[k]);need[k[0],int(labels[i])].append(k)
 for k,ks in need.items():
  if len(ks)>len(free[k]):return None
  for p,f in zip(ks,sorted(free[k])):q[p]=f
 assert set(q)=={(k,f) for (k,p),f in q.items()};assert len(set(q.values()))<=len(q)
 return q
def labels_of(d,q):return np.array([bank(q[k]) for k in d['keys']],dtype=np.int16)
def descriptor(d,rule,param):
 labels=np.zeros(len(d['keys']),dtype=np.int16)
 for t,ids in enumerate(d['tensors']):
  pp=np.arange(len(ids));
  if rule.startswith('RR'):v=(pp//(int(rule[2:])//4))%16
  elif rule=='PHASE4':v=(pp+param[t])%16
  elif rule=='HASH4':v=np.array([splitmix(param^(t<<32)^int(p))%16 for p in pp])
  else:v=(pp^(pp>>param))%16
  labels[ids]=v
 return labels
def choose_descriptors(d,base):
 result={};notes={};phase=[0]*len(d['tensors']);v=descriptor(d,'PHASE4',phase)
 # all phases visited, two rounds; score evaluated by tensor-edge histogram and weighted load
 for rnd in range(2):
  for t,ids in enumerate(d['tensors']):
   best=None;old=v[ids].copy()
   for ph in range(16):
    cand=(np.arange(len(ids))+ph)%16;v[ids]=cand
    # incident adjacency only; heat load unaffected for equal-length divisible16 tensors
    val=sum(w for i in ids for j,w in d['adj'][i] if v[i]==v[j])
    item=(val,ph)
    if best is None or item<best:best=item
   phase[t]=best[1];v[ids]=(np.arange(len(ids))+phase[t])%16
 notes['phase']=phase
 for rule in DESC:
  params=([None] if rule.startswith('RR') else [phase] if rule=='PHASE4' else P['seeds'] if rule=='HASH4' else [1,2,4]);options=[]
  for param in params:
   lab=descriptor(d,rule,param);q=materialize(d,lab,base)
   if q is not None:options.append((score(d,lab),str(param),q,param))
  if options:
   pick=min(options,key=lambda x:(x[0],x[1]));result[rule]=pick[2];notes[rule]={'parameter':pick[3],'proxy':pick[0]}
  else:notes[rule]={'status':'INFEASIBLE_CAPACITY_NO_REPAIR'}
 return result,notes
def coarse_start(d,base,g):
 lab=np.empty(len(d['keys']),dtype=np.int16);units=[];left={k:dict(v) for k,v in d['capacity'].items()}
 for ids in d['tensors']:
  for off in range(0,len(ids),g):
   u=ids[off:off+g];rank=int(d['ranks'][u[0]]);votes=collections.Counter(bank(base[d['keys'][i]]) for i in u);legal=[b for b in range(16) if left[rank].get(b,0)>=len(u)]
   if not legal:return None,None
   b=min(legal,key=lambda b:(-votes[b],-left[rank].get(b,0),b));lab[u]=b;left[rank][b]-=len(u);units.append(u)
 return materialize(d,lab,base),units
def optimize(d,base,g,ca):
 begin=time.monotonic()
 if g==1:start=base;units=[[i] for i in range(len(d['keys']))]
 else:start,units=coarse_start(d,base,g)
 if start is None:return None,{'status':'INFEASIBLE_COARSE_PROJECTION'}
 original=labels_of(d,start);rankunits=collections.defaultdict(list)
 for u in units:rankunits[int(d['ranks'][u[0]]),len(u)].append(u)
 groups=[v for v in rankunits.values() if len(v)>1];runs=[];best=None;maxm=int(P['move_fraction']*len(original))
 for seed in P['seeds']:
  t0=time.monotonic();rng=random.Random(seed);lab=original.copy();loads=collections.Counter()
  for i,b in enumerate(lab):loads[int(d['ranks'][i]),int(b)]+=int(d['h'][i])
  moved=set();accepted=0;ev=0
  for ev in range(P['swap_evaluations']):
   if time.monotonic()-t0>P['swap_seconds']:break
   group=rng.choice(groups);u,v=rng.sample(group,2);a,b=int(lab[u[0]]),int(lab[v[0]])
   if a==b:continue
   change=u+v;newm=len(moved)+sum((b if i in u else a)!=original[i] and i not in moved for i in change)-sum((b if i in u else a)==original[i] and i in moved for i in change)
   if newm>maxm:continue
   rank=int(d['ranks'][u[0]]);hu=sum(int(d['h'][i]) for i in u);hv=sum(int(d['h'][i]) for i in v);la,lb=loads[rank,a],loads[rank,b];dh=(la-hu+hv)**2+(lb-hv+hu)**2-la*la-lb*lb;delta=0
   if ca:
    oldcost=newcost=0;us=set(u);vs=set(v)
    for i in change:
     ni=b if i in us else a
     for j,w in d['adj'][i]:
      if j in us or j in vs:
       if i>j:continue
      nj=b if j in us else a if j in vs else int(lab[j]);oldcost+=w*(lab[i]==lab[j]);newcost+=w*(ni==nj)
    delta=newcost-oldcost
   if ((delta,dh)<(0,0) if ca else dh<0):
    lab[u]=b;lab[v]=a;loads[rank,a]=la-hu+hv;loads[rank,b]=lb-hv+hu;accepted+=1
    for i in change:
     if lab[i]!=original[i]:moved.add(i)
     else:moved.discard(i)
  q=materialize(d,lab,start);assert q is not None;val=score(d,lab,ca);rec={'seed':seed,'evaluations':ev+1,'accepted':accepted,'changed_pages_from_optimization_start':len(moved),'seconds':time.monotonic()-t0,'score':val};runs.append(rec)
  if best is None or (val,seed)<(best[0],best[1]):best=(val,seed,q)
 return best[2],{'runs':runs,'selected_seed':best[1],'total_seconds':time.monotonic()-begin,'projection_changed_pages_from_Dstar':sum(start[k]!=base[k] for k in base)}
def randmap(base,treat,seed):
 q=treat.copy();changed=[k for k in base if base[k]!=treat[k]];rng=random.Random(seed)
 for rank in range(16):
  ks=[k for k in changed if k[0]==rank];vals=[treat[k] for k in ks];rng.shuffle(vals);bad=[i for i,k in enumerate(ks) if vals[i]==base[k]]
  if len(bad)>1:
   old=[vals[i] for i in bad]
   for j,i in enumerate(bad):vals[i]=old[(j+1)%len(old)]
  elif bad:
   i=bad[0];j=next((j for j in range(len(ks)) if j!=i and vals[j]!=base[ks[i]] and vals[i]!=base[ks[j]]),None)
   if j is None:return treat.copy(),{'status':'DEGENERATE_NO_ALTERNATIVE'}
   vals[i],vals[j]=vals[j],vals[i]
  for k,v in zip(ks,vals):q[k]=v
 assert {k for k in base if q[k]!=base[k]}==set(changed)
 assert collections.Counter((k[0],q[k]) for k in changed)==collections.Counter((k[0],treat[k]) for k in changed)
 return q,{'status':'CONDITIONAL_BIASED_SHUFFLE_ALL_SEEDS_REPORTED','changed_pages':len(changed)}

def preflight():
 assert sha(NATIVE)==P['native_sha256'];txt=subprocess.check_output(['ldd',str(NATIVE)],text=True,env=clean());assert 'not found' not in txt
 libs={m.group(1):sha(m.group(1)) for m in re.finditer(r'=>\s+(/\S+)',txt)};assert [h for p,h in libs.items() if p.endswith('/libramulator.so')]==[P['ram_library_sha256']]
 assert shutil.disk_usage(R).free>60*2**30
 save(R/'PREFLIGHT.json',{'ldd':txt,'libraries':libs,'free_bytes':shutil.disk_usage(R).free,'loadavg':Path('/proc/loadavg').read_text(),'one_worker':True,'native_sha256':sha(NATIVE)})
 return libs

def prepare_case(model,layer,group):
 s=source(model,layer,group);c=key(model,layer,group);root=R/'inputs'/c;root.mkdir(parents=True,exist_ok=False);asset=s/'assets'/model
 shutil.copyfile(asset/'lowering.json',root/'lowering.json');shutil.copyfile(asset/'objects_complete.json',root/'objects_complete.json');save(root/'SOURCE.json',{'path':str(s),'hashes':{f:sha(s/'candidates/rr'/f) for f in FILES},'objects_sha256':sha(asset/'objects_complete.json'),'lowering_sha256':sha(asset/'lowering.json')})
 refs=read(s/'REFERENCE_RESULTS.json');ref=Path(refs['rr']['source']);launch=read(ref/'launch.json');assert launch['binary_sha256']==P['native_sha256'];assert sha(launch['environment']['HB_RAM_CONFIG'])==P['ram_config_sha256']
 assert all(sha(Path(launch['environment']['HB_GRAPH'])/f)==sha(s/'candidates/rr'/f) for f in FILES), 'Historical input identity';save(root/'HISTORICAL.json',{'ref':str(ref),'launch':launch,'summary':read(ref/'summary.json'),'source_map':str(s/'candidates/rr/rr_map.txt')});return c

def put(case,layout,q,meta):
 root=R/'inputs'/case;src=Path(read(root/'SOURCE.json')['path'])/'candidates/rr';dest=root/layout;dest.mkdir();start=time.monotonic();base=table(src/'rr_map.txt');assert set(base)==set(q);assert set(base)=={(k,f) for (k,p),f in q.items()}
 objects=read(root/'objects_complete.json')['objects'];move={(x['partition'],x['address']//4096+j) for x in objects if x['role']=='FP16_weight' and not x['name'].startswith('router_') for j in range((x['reserved_bytes']+4095)//4096)};assert all(q[k]==base[k] for k in base if k not in move)
 write_table(dest/'rr_map.txt',q)
 for f in FILES:
  if f!='rr_map.txt':os.link(src/f,dest/f)
 rec={'metadata':meta,'hashes':{f:sha(dest/f) for f in FILES},'changed_pages_vs_historical_RR':sum(q[k]!=base[k] for k in q),'state_u32_bytes':len(move)*4,'write_and_validate_seconds':time.monotonic()-start}
 save(dest/'FROZEN.json',rec);return rec

# Audit implementation inherited read-only; bind new inputs root, never call its runner.
sp=importlib.util.spec_from_file_location('audit_parent',B/'page_management_stage1_step5_execution_20261023_v1/run_natural.py');AUD=importlib.util.module_from_spec(sp);sp.loader.exec_module(AUD);AUD.R=R
RESULT={};PROJ={};LIBS={}
def run(case,layout,identity=False,repeat=False):
 global COUNT
 guard();out=R/'runs'/(case+'__'+layout+('__identity' if identity else '__repeat' if repeat else ''));out.mkdir(parents=True);(out/'tmp').mkdir();(out/'empty.trace').write_text('');root=R/'inputs'/case;hist=read(root/'HISTORICAL.json');frozen=read(root/layout/'FROZEN.json')
 assert all(sha(root/layout/f)==h for f,h in frozen['hashes'].items());assert sha(NATIVE)==P['native_sha256'];assert all(sha(p)==h for p,h in LIBS.items())
 env=clean();env.update(hist['launch']['environment']);env.update(HB_GRAPH=str(root/layout),HB_OUT=str(out),POPNET_STATS_DIR=str(out),TMPDIR=str(out/'tmp'),TMP=str(out/'tmp'),TEMP=str(out/'tmp'),HB_IDENTITY='0',HB_OFFLINE='0');cmd=hist['launch']['command'].copy();cmd[0]=str(NATIVE);cmd[cmd.index('-I')+1]=str(out/'empty.trace')
 COUNT+=1;assert COUNT<=P['max_native'];save(R/'PROGRESS.json',{'status':'RUNNING_NATIVE','current':out.name,'native_started':COUNT,'time':time.time()});save(out/'launch.json',{'command':cmd,'environment':{k:v for k,v in env.items() if k.startswith(('HB_','POPNET_'))},'cwd':str(out),'input_hashes':frozen['hashes'],'binary_sha256':sha(NATIVE)})
 t=time.monotonic()
 with (out/'stdout.log').open('w') as log:subprocess.run(cmd,env=env,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=min(P['per_run_seconds'],P['total_seconds']-(time.monotonic()-START)))
 if case not in PROJ:PROJ[case]=AUD.project_issues(Path(hist['ref'])/'events.csv',Path(hist['source_map']))
 val=AUD.audit(case,out,layout,PROJ[case]);summary=read(out/'summary.json')
 for f in ('transactions','callbacks','read_bytes','write_bytes','tiles','packets','backend'):assert summary[f]==hist['summary'][f],(case,f)
 if identity:assert all(sha(out/f)==sha(Path(hist['ref'])/f) for f in ('events.csv','nodes.csv','summary.json'))
 result={'cycles':summary['cycles'],'summary':summary,'path':str(out),'seconds_native_audit':time.monotonic()-t,'frozen_hashes':frozen['hashes'],'audit':val}
 if not identity and not repeat:RESULT.setdefault(case,{})[layout]=result;save(R/'RESULTS.json',RESULT)
 print('DONE',out.name,summary['cycles'],flush=True);return result

def main():
 global LIBS
 assert not (R/'STARTED.json').exists();save(R/'STARTED.json',{'pid':os.getpid(),'time':time.time(),'script_sha256':sha(Path(__file__)),'protocol_sha256':sha(R/'EXECUTION_PROTOCOL.json')});LIBS=preflight();cases=[];data={};notes={}
 for model,layers in P['models'].items():
  for layer in layers:
   for group in P['groups']:cases.append(prepare_case(model,layer,group))
   d=model_data(model,layer);data[model,layer]=d;base=table(d['src']/'candidates/rr/rr_map.txt');t=time.monotonic();maps,note=choose_descriptors(d,base);notes[f'{model}_{layer}']={'descriptor_selection_seconds':time.monotonic()-t,'notes':note}
   for group in P['groups']:
    c=key(model,layer,group);targetbase=table(source(model,layer,group)/'candidates/rr/rr_map.txt')
    for name,q in maps.items():
     target=targetbase.copy();target.update({k:q[k] for k in d['keys']});put(c,name,target,notes[f'{model}_{layer}'])
 save(R/'DESCRIPTOR_FREEZE.json',notes)
 for model in P['models']:
  c=key(model,0,'N_DEV');base=table(Path(read(R/'inputs'/c/'SOURCE.json')['path'])/'candidates/rr/rr_map.txt');put(c,'HIST_RR',base,{'identity_only':True});run(c,'HIST_RR',identity=True)
 for model,layers in P['models'].items():
  for layer in layers:
   c=key(model,layer,'N_DEV')
   for desc in DESC:
    if (R/'inputs'/c/desc).exists():run(c,desc)
 stars={}
 for model,layers in P['models'].items():
  legal=[s for s in DESC if all(s in RESULT[key(model,l,'N_DEV')] for l in layers)];stars[model]=min(legal,key=lambda s:(sum(RESULT[key(model,l,'N_DEV')][s]['cycles'] for l in layers),DESC.index(s)))
 save(R/'DSTAR_FREEZE.json',{'stars':stars,'before_test_references':True,'time':time.time()})
 for (model,layer),d in data.items():
  dev=key(model,layer,'N_DEV');base=table(R/'inputs'/dev/stars[model]/'rr_map.txt');new={}
  for g in (1,4,16):
   for strategy in ('HEAT','CA'):
    q,note=optimize(d,base,g,strategy=='CA');name=strategy+str(g*4)
    if q is not None:new[name]=(q,note)
  for name in ('HEAT4','CA4'):
   if name in new:
    for i,seed in enumerate(P['seeds'],1):new[f'RAND_{name}_{i}']=randmap(base,new[name][0],seed)
  for group in P['groups']:
   c=key(model,layer,group);targetbase=table(source(model,layer,group)/'candidates/rr/rr_map.txt')
   for name,(q,note) in new.items():
    target=targetbase.copy();target.update({k:q[k] for k in d['keys']});put(c,name,target,note)
   save(R/'inputs'/c/'ROW_ATTRIBUTION.json',{'status':'NOT_IDENTIFIABLE','reason':'No certified independent row/Bank recombination materializer for full resident weight domain; slots retained as missing, not replaced'})
 save(R/'ALL_CANDIDATES_FROZEN.json',{'time':time.time(),'before_test_references':True,'files':{str(p.relative_to(R)):sha(p) for p in (R/'inputs').rglob('FROZEN.json')}})
 for c in cases:
  seen={json.dumps(v['frozen_hashes'],sort_keys=True):s for s,v in RESULT.get(c,{}).items()}
  for layout in DESC+('HEAT16','CA16','HEAT64','CA64','HEAT4','CA4')+tuple(f'RAND_{s}_{i}' for s in ('HEAT4','CA4') for i in (1,2,3)):
   f=R/'inputs'/c/layout/'FROZEN.json'
   if not f.exists() or layout in RESULT.get(c,{}):continue
   fp=json.dumps(read(f)['hashes'],sort_keys=True)
   if fp in seen:RESULT.setdefault(c,{})[layout]={**RESULT[c][seen[fp]],'equivalent_to':seen[fp]};save(R/'RESULTS.json',RESULT)
   else:run(c,layout);seen[fp]=layout
 for model in P['models']:
  c=key(model,0,'N_DEV');rep=run(c,stars[model],repeat=True);old=RESULT[c][stars[model]];assert all(sha(Path(rep['path'])/f)==sha(Path(old['path'])/f) for f in ('summary.json','events.csv','nodes.csv'))
 save(R/'FINAL_STATUS.json',{'status':'COMPLETE_NATURAL_DEVELOPMENT_SCOPED','native_runs':COUNT,'cases':len(cases),'elapsed_seconds':time.monotonic()-START,'row_attribution':'NOT_IDENTIFIABLE','new_independent_sources':0,'deployment_cost':'NET_UNVERIFIED'})
 print('COMPLETE',COUNT,flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:save(R/'FAILED.json',{'error':repr(e),'traceback':traceback.format_exc(),'native_started':COUNT,'time':time.time()});raise
