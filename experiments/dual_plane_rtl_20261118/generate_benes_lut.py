"""Five active ports in an eight-port fabric: 120 constant switch images.

The other three ports complete the identity permutation. The datapath remains
the canonical 8x8 Beneš. This avoids a large per-cycle graph-coloring circuit.
"""
from itertools import permutations
from pathlib import Path
def route(p):
    n=len(p)
    if n==2:return [int(p[0]!=0)]
    inv=[0]*n
    for i,x in enumerate(p):inv[x]=i
    color=[-1]*n
    for start in range(n):
        if color[start]>=0:continue
        color[start]=0;todo=[start]
        while todo:
            i=todo.pop()
            for j in [i^1,inv[p[i]^1]]:
                if color[j]<0:color[j]=1-color[i];todo.append(j)
                else:assert color[j]!=color[i]
    sub=[[0]*(n//2) for _ in range(2)]
    for i in range(n):sub[color[i]][i//2]=p[i]//2
    middle=[route(x) for x in sub]
    first=[color[2*i] for i in range(n//2)]
    last=[color[inv[2*i]] for i in range(n//2)]
    stages=len(middle[0])//(n//4)
    out=first
    for stage in range(stages):
        for i in range(n//4):
            for c in range(2):out.append(middle[c][stage*(n//4)+i])
    return out+last
def main():
    lines=['function automatic logic [19:0] route5(input logic [14:0] perm);',' case(perm)']
    for p5 in permutations(range(5)):
        p=list(p5)+[5,6,7];cfg=route(p);assert len(cfg)==20
        values=list(range(8))
        for stage,dist in enumerate([1,2,4,2,1]):
            for a in range(8):
                if a&dist:continue
                k=(a//(2*dist))*dist+a%dist
                if cfg[stage*4+k]:values[a],values[a+dist]=values[a+dist],values[a]
        assert all(values[p[i]]==i for i in range(8))
        key=sum(x<<(3*i) for i,x in enumerate(p5));image=sum(x<<i for i,x in enumerate(cfg))
        lines.append(f" 15'h{key:04x}:route5=20'h{image:05x};")
    lines+=[' default:route5=0;',' endcase','endfunction','']
    p=Path(__file__).resolve().parent/'rtl/benes5_lut.svh';p.write_text('\n'.join(lines),newline='\n')
    print('Verified and generated 120 five-port permutation images')
if __name__=='__main__':main()
