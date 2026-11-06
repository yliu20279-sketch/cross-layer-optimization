"""Native vector engineering diagrams, no generated raster art."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

P=Path(__file__).resolve().parent
plt.rcParams.update({'font.family':'DejaVu Sans','svg.fonttype':'none','font.size':10})
BLUE='#dbeafe'; GREEN='#d1fae5'; ORANGE='#ffedd5'; GRAY='#f1f5f9'; RED='#fee2e2'

def canvas(title,subtitle,w=16,h=10):
    fig,ax=plt.subplots(figsize=(w,h));ax.set_xlim(0,16);ax.set_ylim(0,10);ax.axis('off')
    ax.text(.35,9.7,title,fontsize=20,weight='bold',va='top',color='#0f172a')
    ax.text(.35,9.18,subtitle,fontsize=10,va='top',color='#475569')
    return fig,ax

def box(ax,x,y,w,h,label,color=BLUE,fs=10):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.025,rounding_size=.10',fc=color,ec='#64748b',lw=1))
    ax.text(x+w/2,y+h/2,label,ha='center',va='center',fontsize=fs,color='#0f172a')
    return (x,y,w,h)

def arrow(ax,a,b,label='',style='-',color='#475569',rad=0):
    ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=12,lw=1.3,color=color,linestyle=style,connectionstyle=f'arc3,rad={rad}'))
    if label:ax.text((a[0]+b[0])/2,(a[1]+b[1])/2+.10,label,ha='center',fontsize=8,color=color)

def finish(fig,name):
    fig.savefig(P/(name+'.svg'),bbox_inches='tight',pad_inches=.15)
    fig.savefig(P/(name+'.png'),dpi=150,bbox_inches='tight',pad_inches=.15)
    plt.close(fig)

def task():
    fig,ax=canvas('01  Agent task graph: conditional control flow','SOURCE-GROUNDED TEMPLATE | not an observed task trace | loop counts, routes and durations unknown')
    top=[(.5,'Issue / repo\nbase commit',GRAY),(4.3,'History / template\ntokenizer',GRAY),(8.1,'Uncached prefill\n48 decoder layers',BLUE),(11.9,'LM head / sample\nfirst output token',BLUE)]
    for x,label,col in top:box(ax,x,7.0,3.0,1.1,label,col)
    for x in [.5,4.3,8.1]:arrow(ax,(x+3,7.55),(x+3.8,7.55))
    box(ax,11.9,4.7,3,1.2,'Decode forward + sample\nT=1; KV cache state',BLUE)
    arrow(ax,(13.4,7),(13.4,5.9),'more tokens')
    arrow(ax,(14.9,5.6),(14.9,5.0),'repeat',style='--',rad=-1.2)
    box(ax,8.1,4.7,3,1.2,'Action parse / stop\nformat and budget checks',GRAY)
    arrow(ax,(11.9,5.3),(11.1,5.3))
    arrow(ax,(12.0,7),(10.9,5.9),'or complete',style='--')
    box(ax,4.3,4.7,3,1.2,'Read / search / edit / test\nexternal CPU + container',ORANGE)
    arrow(ax,(8.1,5.3),(7.3,5.3))
    box(ax,.5,4.7,3,1.2,'Observation / exit code\nstdout / stderr / timing',ORANGE)
    arrow(ax,(4.3,5.3),(3.5,5.3))
    arrow(ax,(2,5.9),(5.8,7),'next turn; no early release',style='--',rad=-.2)
    box(ax,8.1,2.3,3,1.0,'Final patch + harness\nexternal evaluation',GREEN)
    arrow(ax,(9.6,4.7),(9.6,3.3),'submit')
    box(ax,12,2.3,3,1.0,'Failure / timeout / limit\nretain unsuccessful runs',RED)
    arrow(ax,(11.1,4.8),(13.4,3.3),'conditional exit',style='--')
    ax.text(.5,2.4,'NPU candidate: model arithmetic only\nCPU/container: agent orchestration, tools and evaluation\nTransfer/callback gates join both domains',fontsize=11,va='top')
    ax.text(.5,.65,'Dashed edges are conditional recurrence. Unroll each observed turn/token into unique IDs before DAG execution.\nThe agent is not guaranteed to read, edit and test in that order; command contents remain runtime data.',fontsize=10,color='#475569')
    finish(fig,'01_task_control')

def block():
    fig,ax=canvas('02  One Qwen3 decoder layer (repeat 48 times)','Prefill: T uncached tokens, P cached | Decode: T=1 | source BF16; target BF16 arithmetic support UNVERIFIED',h=11)
    specs=[(.45,7.65,2.6,.75,'X [T,2048]',GRAY),(.45,6.4,2.6,.85,'RMSNorm\nshared scale [2048]',GREEN),
           (4.1,7.35,3,.85,'Q: 2048 -> 4096\n32 query heads',BLUE),(4.1,5.95,3,.85,'K,V: each 2048 -> 512\n4 KV heads',BLUE),
           (8.0,7.35,3.05,.85,'Q RMSNorm + RoPE\nhead dim 128',GREEN),(8.0,5.95,3.05,.85,'K RMSNorm + RoPE\nK/V cache append/read',GREEN),
           (12,6.45,3.3,1.5,'Tiled QK -> mask/softmax\n-> probability x V (GQA)\nfull score not materialized',BLUE),
           (12,4.85,3.3,.85,'O projection + TP sum\n4096 -> 2048',BLUE),
           (8,4.85,3.05,.85,'Attention residual\n+ MoE RMSNorm',GREEN),
           (4.1,4.6,3,1.35,'Router 2048 -> 128\nFP32 softmax -> Top8\nrenorm -> hidden dtype',GREEN),
           (.45,4.6,2.6,1.35,'Pack + dispatch\nactual route IDs\n8 assignments/token',ORANGE),
           (.45,2.45,3.15,1.25,'Active expert residency gate\nmiss: fetch / evict / commit\nowner p_l(e); m_e > 0',ORANGE),
           (4.35,2.45,3.8,1.25,'Expert: gate & up 2048 -> 768\nSiLU(gate) * up\ndown 768 -> 2048',BLUE),
           (8.9,2.45,3.0,1.25,'Multiply route weight\nreturn -> index_add\nsum_e m_e = 8*T',GREEN),
           (12.6,2.45,2.7,1.25,'Hidden synchronization\nMoE residual\nnext layer',ORANGE)]
    for x,y,w,h,l,col in specs:box(ax,x,y,w,h,l,col,fs=9)
    for a,b in [((1.75,7.65),(1.75,7.25)),((3.05,6.9),(4.1,7.75)),((3.05,6.7),(4.1,6.4)),((7.1,7.75),(8,7.75)),((7.1,6.4),(8,6.4)),((11.05,7.75),(12,7.4)),((11.05,6.4),(12,6.7)),((13.65,6.45),(13.65,5.7)),((12,5.27),(11.05,5.27)),((8,5.27),(7.1,5.27)),((4.1,5.27),(3.05,5.27)),((1.75,4.6),(1.75,3.7)),((3.6,3.08),(4.35,3.08)),((8.15,3.08),(8.9,3.08)),((11.9,3.08),(12.6,3.08))]:arrow(ax,a,b)
    ax.plot([1.75,1.75,7.6,7.6],[8.4,8.65,8.65,5.85],ls='--',color='#475569',lw=1.3)
    arrow(ax,(7.6,5.85),(8.15,5.7),style='--')
    ax.text(4.6,8.72,'attention residual skip',ha='center',fontsize=9,color='#475569')
    arrow(ax,(8.3,4.85),(13.95,3.7),'MoE skip (before norm)',style='--',rad=.07)
    ax.text(.5,1.45,'Blue = matrix work | Green = vector/reduce | Orange = memory / communication gates\nExpert node is a conditional loop over 128 experts, not execution of all experts for every token.\nQ/K norm learned scales are [128] each, shared across heads; no Qwen1.5 shared-expert branch.',fontsize=11,va='top')
    ax.text(.5,.35,'MAC and vector placement is a lowering proposal. No measured cycles, allocation, route trace or native BF16 certification.',fontsize=10,color='#9a3412')
    finish(fig,'02_decoder_layer')

def architecture():
    fig,ax=canvas('03  Proposed V3.6 placement: TP16 + EP16','16 NPU/CH pairs | each NPU: 4 MiB SRAM, FP16 MAC/FP32 accumulation + FP32 vector | 32 B DRAM transactions',h=11)
    box(ax,.4,7.6,4.6,.9,'Host CPU / agent / tools / tokenizer\n8 GiB target host RAM; container fit unverified',GRAY,9)
    box(ax,5.55,7.6,4.9,.9,'PCIe 5 x16 -> gateway router 16\n55.04 GB/s/direction model; callbacks required',ORANGE,9)
    box(ax,11.05,7.6,4.5,.9,'Backing storage / BF16 arithmetic\nUNRESOLVED deployment gates',RED,9)
    arrow(ax,(5,8.05),(5.55,8.05));arrow(ax,(10.45,8.05),(11.05,8.05),style='--')
    colors=['#dbeafe','#dcfce7','#fef3c7','#ede9fe']
    centers={}
    for r in range(16):
        row,col=divmod(r,4);x=.55+col*3.9;y=5.65-row*1.35
        box(ax,x,y,3.15,1.0,f'N{r}  Q heads {2*r},{2*r+1} | KV head {r//4}\nCH{r}: 512 MiB, one vertical port\nexperts e mod16={r}; 8/layer',colors[row],8.5)
        centers[r]=(x+1.575,y+.5)
    for r,(x,y) in centers.items():
        if r%4<3:ax.add_patch(FancyArrowPatch((x+1.575,y),(centers[r+1][0]-1.575,y),arrowstyle='<->',mutation_scale=10,color='#475569'))
        if r<12:ax.add_patch(FancyArrowPatch((x,y-.5),(x,centers[r+4][1]+.5),arrowstyle='<->',mutation_scale=10,color='#475569'))
    arrow(ax,(7.8,7.6),(centers[1][0],6.65),'mesh + gateway',style='--')
    ax.text(.55,1.05,'Attention: 2 Q heads/rank. Every four adjacent ranks duplicate one KV head (4x KV storage/projection).\nMoE: baseline owner e mod16; Sem-MoE changes legal expert placement, not model topology.\nReplicated hidden is dispatched ONCE per token assignment; collectives and router metadata are not free.',fontsize=10,va='top')
    ax.text(.55,.08,'61.06 GB unique weight payload cannot fit 8 GiB HB + 8 GiB host. No bandwidth multiplier from 4 logical Banks.',fontsize=10,color='#9a3412')
    finish(fig,'03_target_mapping')

if __name__=='__main__':
    task();block();architecture()
    body='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>mini-SWE 算子图与架构映射</title><style>body{max-width:1500px;margin:30px auto;font:16px system-ui;color:#172033;background:#f8fafc}section{background:white;padding:20px;margin:24px 0;border:1px solid #ddd}img{width:100%;height:auto}a{color:#175bc2}h1{font-size:27px}</style><h1>mini-SWE + Qwen3：源码级任务图与目标映射</h1><p>静态结构交付；不是已采集轨迹、可执行IR或性能验证。实际任务次数、路由、地址与时序未知。</p><p><a href="REPORT.md">拆分报告</a> · <a href="REPRODUCTION_STEPS_V2.md">按结构重排的后续计划</a> · <a href="OPERATOR_INVENTORY.csv">算子清单</a> · <a href="MAPPING.json">机器映射</a></p>'''
    for name,title in [('01_task_control','任务控制流：工具完成后才释放下一轮'),('02_decoder_layer','模型算子：48层展开，专家循环由真实路由决定'),('03_target_mapping','目标架构：TP16/EP16候选与KV四倍复制')]:
        body+=f'<section><h2>{title}</h2><img src="{name}.svg"><p><a href="{name}.png">PNG</a> · <a href="{name}.svg">SVG</a></p></section>'
    (P/'index.html').write_text(body+'</html>',encoding='utf-8')
    print('3 SVG + 3 PNG diagrams and local viewer generated.')
