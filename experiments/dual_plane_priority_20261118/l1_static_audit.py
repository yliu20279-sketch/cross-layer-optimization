"""Source-level physical graph and Beneš routing audit, never synthesizes."""
import csv,hashlib,itertools,json,re
from pathlib import Path
R=Path(__file__).resolve().parent;src=R/'package/rtl'
cs=(src/'cs_fabric.sv').read_text(encoding='utf-8')
case=cs.split('case(5*s+p)',1)[1].split('endcase',1)[0]
fixed={int(k):eval(expr,{'__builtins__':{}},{}) for k,expr in re.findall(r'(\d+):return ([\d+* ]+);',case)}
def peer(s,p):return 4*(s//3)+s%3+(4 if p>=2 else 0)+p%2 if s<9 and p<4 else fixed.get(5*s+p,-1)
edges=[];ni=[]
for s in range(13):
 for p in range(5):
  other=peer(s,p)
  if other<0:continue
  if other<16:ni.append((s,p,other))
  else:
   t,q=divmod(other-16,5);assert peer(t,q)==16+5*s+p,(s,p,t,q)
   edges.append((s,p,t,q))
assert len(ni)==36
assert all(peer(s,p)<0 for s in range(9,13) for p in [3,4])
degrees={n:sum(x[2]==n for x in ni) for n in range(16)}
assert sorted(degrees.values())==[1]*4+[2]*8+[4]*4
assert 'if(CONNECTED)assign ni_receive_data[n][c]=data[c];' in cs
assert 'else assign ni_receive_data[n][c]=\'0;' in cs
lut=(src/'benes5_lut.svh').read_text(encoding='utf-8')
configs={int(a,16):int(b,16) for a,b in re.findall(r"15'h([0-9a-fA-F]+):route5=20'h([0-9a-fA-F]+)",lut)}
assert len(configs)==120
for perm in itertools.permutations(range(5)):
 key=sum(v<<(3*i) for i,v in enumerate(perm));cfg=configs[key];wires=list(range(8))
 for stage,distance in enumerate([1,2,4,2,1]):
  nxt=wires.copy()
  for p in range(8):
   if p&distance:continue
   index=p//(2*distance)*distance+p%distance
   if (cfg>>(4*stage+index))&1:nxt[p],nxt[p+distance]=wires[p+distance],wires[p]
  wires=nxt
 for i,o in enumerate(perm):assert wires[o]==i,(perm,cfg,wires)
 assert wires[5:]==[5,6,7]
table=[
 ['共享物理通道','Fig.6/§4：同一链路划分global/local，原图四条512-bit','split_width_link：4条64-bit lane由global_lanes分配，两域和恒为4','缩放到256-bit是平台假设；没有复制两组256-bit链路','source_checked'],
 ['192-bit连续打包','local-biased为3/1通道比例','按64-bit单位跨flit队列推进moved计数，不对每个256-bit flit单独向上取整','序列化及重组缓存DEPTH8单列；原RR split自测回执复用','source_checked_existing_regression'],
 ['NA与local路径','§4：NA内相邻阵列一跳直达','near()：同一行连续4rank且Manhattan距离<=1；其余global XY','TP4/行分组是本平台映射，非作者32阵列完整布局','explicit_mapping_assumption'],
 ['Beneš数据通路','Fig.6：8x8 split-Beneš','五级、每级4个2x2；本实现每域5个有效端口，5..7置零','120种5端口排列已独立逐级检查；不声称完整作者split-Beneš','120_permutations_checked'],
 ['NI-CS物理连接','项目9下层+4上层CS几何','36条NI-下层CS附着；16条有向CS-CS附着互反；上层仅端口0..2','旧动态宽索引有综合结构疑虑；本版静态屏蔽非邻接宽输入，未综合验证面积','static_connectivity_checked'],
 ['配置与版本','项目暂停/排空/安装协议','active commit断言ready&&legal；top要求pause/ack、CS idle、全部stage版本；NI校验installed_version','新优先版本共用回归排空/失败保持，等待BUILD回执','source_checked_regression_pending'],
 ['DRAM直连','Fig.6黄色DRAM Direct Link与NoC不同','未加为第二条邻接NoC，端点Bank/SRAM由共同服务模型提供','没有复现原HB-DRAM执行器及其专用直接带宽','scope_difference'],
 ['动态模式与广播','§5按阶段/计算步骤选择模式','主表静态4/0、2/2、1/3；仅unicast','phase-best免费事后择优是分析界；原作者动态策略/广播不在复现范围','scope_difference'],
]
status_path=R/'LATEST_STATUS.json'
if status_path.exists():
 status=json.loads(status_path.read_text(encoding='utf-8'));build=json.loads(status['files'].get('BUILD.json','{}'))
 if build.get('status')=='PASS':table[5][-1]='source_and_common_cpp_regression_passed'
with (R/'L1_PAPER_IMPLEMENTATION_MAPPING.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.writer(f);w.writerow(['item','paper_or_design','implementation','assumption_or_limit','status']);w.writerows(table)
audit=dict(status='PASS_STATIC_GRAPH_AND_120_BENES_PERMUTATIONS',ni_cs_attachments=36,ni_degrees=degrees,directed_cs_cs_attachments=len(edges),undirected_cs_cs_links=len(edges)//2,unused_upper_ports=8,benes_permutations=120,
 source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in src.glob('*.sv')},
 scope='Source/static graph only, no synthesis, no area/timing/power certification. Functional new-version regression reported separately in BUILD.json.',
 sources=['HiBand Fig.6 and sections4-5, DOI10.1145/3770743.3803944','tmp/pdfs/hiband/DAC_2026_Draft_Proceedings/papers/282_Camera_Ready_Paper.pdf','090a55d0 frozen RTL and this package source'])
(R/'L1_STATIC_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in audit.items() if k!='source_sha256'},ensure_ascii=False,indent=2))
