"""Structural concurrency audit; does not claim realized timing overlap."""
import argparse,csv,json,re
from collections import defaultdict,deque
from pathlib import Path
PAT=re.compile(r'S(\d+)L(\d+)W(\d+)')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--graph',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    with (a.graph/'ops.csv').open(newline='') as f:ops={int(r['id']):r for r in csv.DictReader(f)}
    children=defaultdict(list)
    with (a.graph/'deps.csv').open(newline='') as f:
        for r in csv.DictReader(f):children[int(r['src'])].append(int(r['dst']))
    bsa=defaultdict(list);bga=defaultdict(list)
    for i,o in ops.items():
        m=PAT.search(o['task'])
        if not m:continue
        key=(int(m[1]),int(m[2]),int(o['pe']));wave=int(m[3])
        if o['phase']=='COMPUTE_BSA':bsa[key,wave].append(i)
        if o['phase']=='COMPUTE_BGA':bga[key,wave].append(i)
    def reaches(src,targets):
        q=deque([src]);seen={src}
        while q:
            x=q.popleft()
            for y in children[x]:
                if y in targets:return True
                if y not in seen:seen.add(y);q.append(y)
        return False
    candidates=ordered=0;examples=[]
    keys={(s,l,p) for (s,l,p),w in bsa}
    for key in sorted(keys):
        for w1 in range(1,32):
            left=bsa.get((key,w1),[]);right=bga.get((key,w1-1),[])
            for x in left:
                for y in right:
                    candidates+=1
                    if reaches(x,{y}) or reaches(y,{x}):ordered+=1
                    elif len(examples)<8:examples.append({'bsa':ops[x]['task'],'bga':ops[y]['task'],'npu':key[2]})
    assert candidates>0 and ordered==0
    report={'status':'PASS','cross_wave_same_npu_pairs':candidates,'causally_ordered_pairs':ordered,'structurally_concurrent_pairs':candidates-ordered,'examples':examples,'claim':'DAG permits BSA/BGA concurrency; realized overlap remains a separate timing gate'}
    a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
