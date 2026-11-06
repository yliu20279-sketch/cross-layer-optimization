import pathlib,json,numpy as np,csv,math,sqlite3,re
R=pathlib.Path(__file__).resolve().parent;results=[]
for k in [1,2]:
 D=R/('case%d'%k);assert json.loads((D/'N00/PASS.json').read_text())['state'].startswith('PASS');assert json.loads((D/'CPU_PASS.json').read_text())['state'].startswith('PASS');ev=json.loads((D/'N00/EVENTS.json').read_text());prev=0
 for e in ev:assert e['done']>=e['start']>=prev;prev=e['done']
 for name,N in [('K',128),('V',128),('Ocarry',2048)]:
  for typ,ref in [('F32','F32_reference'),('BF16','GPU')]:assert (D/'N00'/(name+'_'+typ+'.bin')).read_bytes()==(D/('CPU_'+name+'_'+typ+'.bin')).read_bytes()==(R/'data'/(name+'_'+ref+'.bin')).read_bytes()
 clocks=list(csv.DictReader((R/'run'/('clock_round%d.csv'%k)).open()));domains=list(csv.DictReader((R/'run'/('domain_service_round%d.csv'%k)).open()));groups={};rates={}
 for c in clocks:
  src,dst=int(c['src']),int(c['dst']);rate=float(c['clock_ratio']);ns=float(c['global_ns']);assert rate in ([1,2.5] if 48 in (src,dst) else [1]);assert round(ns*rate)==int(float(c['native_ticks']));groups.setdefault((src,dst,int(c['descriptor'])),[]).append(ns);rates.setdefault((src,dst,int(c['descriptor'])),[]).append(rate)
 used={}
 for d in domains:
  key=(int(d['src']),int(d['dst']),int(d['descriptor']));i=used.get(key,0);assert float(d['ready'])==math.ceil(max(groups[key][2*i:2*i+2]));assert sorted(rates[key][2*i:2*i+2])==([1.0,2.5] if 48 in key[:2] else [1.0,1.0]);used[key]=i+1;assert float(d['complete'])>=float(d['start'])>=float(d['ready'])
 feedback=list(csv.DictReader((R/'run'/('noc_feedback_round%d.csv'%k)).open()));assert all(int(v['profile_applied'])==(k-1) for v in feedback)
 results.append(dict(round=k,clock_observations=len(clocks),domain_records=len(domains),horizontal_messages=len(feedback),all_previous_feedback_applied=k==2,CPU_raw_and_BF16_elements=2304,NPU_consumer_after_actual_CPU_return=True))
text=(R/'RUN.log').read_text();codes=[int(x) for x in re.findall(r'terminate with status = (\d+)',text)];assert len(codes)==10 and all(v==0 for v in codes)
r=dict(state='PASS_LIMITED_ACTUAL_CPU_TO_NPU_SERVICE_TWO_ROUNDS',rounds=results,all10children_zero=True,target_GPU_count=0,full_step5=False,limits=['one query K/V and Ocarry only','initial input placement and full model not executed','CPU cache coherence/cache-maintenance timing not certified','not full-layer cost replacement']);(R/'INDEPENDENT_AUDIT.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
