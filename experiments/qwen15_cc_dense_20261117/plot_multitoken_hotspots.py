"""Plot the recorded 16-token traffic and reproduce the circuit scoring."""
import json
import os
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

base = Path(__file__).resolve().parent
sys.path.insert(0, str(base.parent/'swe_scenario1_dense_20261117'))
from planner import EVAL_LIMIT, compatible, wired_paths, xy

out = base/'multitoken_results'
os.chdir(out)
trace = json.loads((out/'PROJECT_TRANSPORT_16.json').read_text())
paths = wired_paths()
labels = ['Attn SRS','Dispatch','Combine','Shared input','Shared reduce','SAG']
records = []
for wave in trace['waves']:
    volume, send, recv, edges = Counter(), Counter(), Counter(), Counter()
    for m in trace['events'][wave['first']:wave['first']+wave['count']]:
        s,d = m['src'],m['dst']
        flits = (m['bytes']+31)//32
        volume[s,d] += flits
        send[s] += flits
        recv[d] += flits
        edges.update({edge:flits for edge in xy(s,d)})
    peak = max(edges.values())
    endpoint = max(max(send.values()),max(recv.values()))
    pairs = sorted(volume,key=lambda p:(-max(edges[e] for e in xy(*p)),-volume[p],p))
    single = [p for pair in pairs[:4] for p in paths.get(pair,())[:2]]
    candidates = ([(p,) for p in single]+[c for c in combinations(single,2) if compatible(c)])[:EVAL_LIMIT]
    scores, residual_peaks = [], []
    for candidate in candidates:
        remaining = edges.copy()
        circuit = 0
        for p in candidate:
            v = volume[p.src,p.dst]
            remaining.subtract({e:v for e in xy(p.src,p.dst)})
            circuit = max(circuit,40+len(p.switches)+v)
        residual_peaks.append(max(remaining.values()))
        scores.append(max(endpoint,circuit,residual_peaks[-1]))
    decision = wave['policy_decision']
    assert len(scores)==decision['evaluated'] and max(endpoint,peak)==decision['mesh_bound']
    best = min(scores)
    assert decision['circuits']==[] and max(endpoint,peak)-best<=1
    records.append((wave['stage'],edges,decision['mesh_bound'],endpoint,best,len(scores)))
    print(wave['stage'], 'link peak', peak, 'min residual link peak', min(residual_peaks),
          'endpoint floor',endpoint,'best CS',best,'candidates',len(scores))

links = sorted(set().union(*(r[1].keys() for r in records)))
values = np.array([[r[1][e] for e in links] for r in records])
plt.rcParams.update({'font.size': 9, 'svg.fonttype': 'none'})
fig, (ax, bx) = plt.subplots(2,1,figsize=(10.3,6.1),height_ratios=(1,1.05),layout='constrained')
fig.suptitle('16-token Qwen1.5-MoE | Where the Mesh decision comes from',fontsize=14)
im = ax.imshow(values,aspect='auto',cmap='cividis',vmin=0,vmax=2048)
ax.set_xticks(range(len(links)),[f'{s}→{d}' for s,d in links],rotation=45,ha='right')
ax.set_yticks(range(6),labels)
ax.set_title('a   Offered flits mapped onto directed XY links',loc='left')
fig.colorbar(im,ax=ax,label='32 B flits per wave',shrink=.86)
for i,j in zip(*np.where(values==values.max(axis=1,keepdims=True))):
    ax.text(j,i,str(values[i,j]),ha='center',va='center',color='#101010',fontsize=7,fontweight='bold')
pos = np.arange(6)
for shift,name,field,color in [(-.25,'Mesh score',2,'#495569'),(0,'Endpoint floor',3,'#0072B2'),
                                (.25,'Best evaluated CS score',4,'#D55E00')]:
    bx.bar(pos+shift,[r[field] for r in records],width=.22,label=name,color=color)
bx.set_xticks(pos,labels)
bx.set_ylim(0,2500)
bx.set_ylabel('Score / floor (cycles)')
bx.set_title('b   Scoring terms by communication wave',loc='left')
bx.legend(ncols=3,loc='upper center',frameon=False)
bx.spines[['top','right']].set_visible(False)
for i,r in enumerate(records):
    bx.text(i+.25,r[4]+28,str(r[4]),ha='center',va='bottom',fontsize=8)
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
bounds = fig.bbox
for artist in fig.findobj(plt.Text):
    if artist.get_visible() and artist.get_text():
        box = artist.get_window_extent(renderer)
        assert bounds.contains(box.x0,box.y0) and bounds.contains(box.x1,box.y1), artist.get_text()
for ext in ('png','svg','pdf'):
    fig.savefig(out/f'mesh_decision_16.{ext}',dpi=300)
print([(name,peak,endpoint,best,count) for name,_,peak,endpoint,best,count in records])
