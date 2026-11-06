#!/usr/bin/env python3
"""Build owner-propagation micro-DAGs before contention attribution exists."""
import argparse,csv,json
from pathlib import Path

FIELDS=['id','kind','task','phase','pe','bytes','sample_bytes','address','cycles','src','dst','scope','rank','inference_request_id']
def write(path,rows,fields):
    with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    cases={
      # RoBaRaCoCh with 256-byte transactions: 0x40000 advances Row while
      # preserving channel/rank/bank-group/bank for this frozen LPDDR5 config.
      'different_owner_same_bank_overlap':[(0,0x0000,101),(0,0x40000,202)],
      'same_owner_same_bank_overlap':[(0,0x0000,101),(0,0x40000,101)],
      'different_owner_different_partition':[(0,0x0000,101),(1,0x0000,202)],
      'single_owner_row_switch':[(0,0x0000,101),(0,0x40000,101)]}
    for name,items in cases.items():
      d=a.out/name;d.mkdir(exist_ok=True);ops=[]
      for i,(pe,address,owner) in enumerate(items):ops.append(dict(id=i,kind='LOAD',task=f'{name}_{i}',phase='COMPUTE',pe=pe,bytes=4096,sample_bytes=4096,address=address,cycles=0,src=-1,dst=-1,scope='local',rank=pe,inference_request_id=owner))
      write(d/'ops.csv',ops,FIELDS);write(d/'deps.csv',[],['src','dst']);write(d/'modes.csv',[dict(mode=m,local_bytes_per_cycle=l,global_bytes_per_cycle=g) for m,l,g in [('FULL_LOCAL',1536,0),('LOCAL_BIAS',1024,512),('GLOBAL_BIAS',512,1024),('FULL_GLOBAL',0,1536)]],['mode','local_bytes_per_cycle','global_bytes_per_cycle'])
      (d/'graph_manifest.json').write_text(json.dumps({'status':'OWNER_MICROTEST','operations':2,'misses':0,'page_operations':[],'limitations':['owner propagation only; not yet a strict contention metric']},indent=2)+'\n')
    print(json.dumps({'status':'PASS','cases':list(cases)},indent=2))
if __name__=='__main__':main()
