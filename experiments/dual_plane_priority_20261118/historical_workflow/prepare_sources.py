"""Freeze common sources, add arbitration-only L2 policy, never touch origin."""
import hashlib,json,shutil
from pathlib import Path
R=Path(__file__).resolve().parent
baseline=json.loads((R.parent/'dual_plane_rtl_followup_20261118/REMOTE_SNAPSHOT.json').read_text(encoding='utf-8'))
b=json.loads(baseline['files']['CURRENT_BUILD.json']['text'])
dest=R/'package'
for name in b['source_sha256']:
    raw=baseline['files']['frozen_source/'+name]['text'].encode()
    assert hashlib.sha256(raw).hexdigest()==b['source_sha256'][name]
    p=dest/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)

def edit(name,old,new,count=1):
    p=dest/'rtl'/name;t=p.read_text(encoding='utf-8');assert t.count(old)==count,(name,old,t.count(old));p.write_text(t.replace(old,new),encoding='utf-8',newline='\n')
for name in ['typed_ni.sv','xy_router.sv']:
    old='DUAL_MODE=1)(' if name=='typed_ni.sv' else 'ACTIVE_VN=15)('
    new=old.replace(')(', ',TYPE_PRIORITY=0)(')
    edit(name,old,new,2)
    old='.DUAL_MODE(DUAL_MODE)) impl' if name=='typed_ni.sv' else '.ACTIVE_VN(ACTIVE_VN)) impl'
    edit(name,old,old.replace(')) impl', '),.TYPE_PRIORITY(TYPE_PRIORITY)) impl'))
edit('typed_ni.sv','automatic int v=(tx_first+vt)%4;','automatic int v=TYPE_PRIORITY?3-vt:(tx_first+vt)%4;')
edit('typed_ni.sv','automatic int v=(rx_first+vt)%4;','automatic int v=TYPE_PRIORITY?3-vt:(rx_first+vt)%4;')
edit('mesh.sv','ACTIVE_VN=15)(', 'ACTIVE_VN=15,TYPE_PRIORITY=0)(')
edit('mesh.sv','.ACTIVE_VN(ACTIVE_VN)) r', '.ACTIVE_VN(ACTIVE_VN),.TYPE_PRIORITY(TYPE_PRIORITY)) r')
edit('hiband_fabric.sv','parameter int DEPTH=2)(', 'parameter int DEPTH=2,TYPE_PRIORITY=0)(')
edit('hiband_fabric.sv','.BENES(1)) r', '.BENES(1),.TYPE_PRIORITY(TYPE_PRIORITY)) r')
edit('experiment_top.sv','DUAL=1,DEPTH=2)(', 'DUAL=1,DEPTH=2,TYPE_PRIORITY=0)(')
edit('experiment_top.sv','hiband_fabric #(.DEPTH(DEPTH)) fabric', 'hiband_fabric #(.DEPTH(DEPTH),.TYPE_PRIORITY(TYPE_PRIORITY)) fabric')
edit('experiment_top.sv','.ACTIVE_VN(DUAL==1?9:15)) m', '.ACTIVE_VN(DUAL==1?9:15),.TYPE_PRIORITY(TYPE_PRIORITY)) m')
edit('experiment_top.sv','.ACTIVE_VN(6)) c', '.ACTIVE_VN(6),.TYPE_PRIORITY(TYPE_PRIORITY)) c')
edit('experiment_top.sv','.DUAL_MODE(DUAL)) ni', '.DUAL_MODE(DUAL),.TYPE_PRIORITY(TYPE_PRIORITY)) ni')

# A VN-first scan is necessary: choosing an output first could allow a low-VN
# request to take a physical input before a higher-VN request to another output.
p=dest/'rtl/xy_router.sv';text=p.read_text(encoding='utf-8')
start=text.index('  // Rotate output priority')
end=text.index('\n end\n // Select wide payloads',start)
rr=text[start:end]
priority='''  // Fixed class order across all outputs: CONFIG, DataS, GetS, MoE.
  // Output and same-VN input arbitration retain their original round robin.
  for(int vt=0;vt<4;vt++)begin
   automatic int v=3-vt;
   for(int ot=0;ot<5;ot++)begin
    automatic int o=(out_first+ot)%5;
    for(int it=0;it<5;it++)begin
     automatic int i=locked[o][v]?owner[o][v]:(first[o][v]+it)%5;
     automatic logic [2:0] route=front[i][v][257]?xy(front[i][v][251:248]):body_route[i][v];
     if(!out_valid[o]&&!used[i]&&!empty[i][v]&&route==o&&out_credit[o][v])begin
      out_valid[o]=1;selected_input[o]=3'(i);selected_vn[o]=2'(v);
      pop[i][v]=1;used[i]=1;
     end
    end
   end
  end'''
text=text[:start]+'  if(TYPE_PRIORITY)begin\n'+priority+'\n  end else begin\n'+rr+'\n  end'+text[end:]
p.write_text(text,encoding='utf-8',newline='\n')

# L1: make physical NI-CS adjacency explicit in the wide data selector.
# The old run-time selector was functionally guarded by peer(c,p)==n, but
# still referenced data[c] with a dynamic index over all nine lower CSs.
edit('cs_fabric.sv','flit_t port_data[13][5];', 'flit_t ni_receive_data[16][9];\n flit_t port_data[13][5];')
edit('cs_fabric.sv'," assign busy=|occupied;assign ready=!busy;",''' for(genvar n=0;n<16;n++)for(genvar c=0;c<9;c++)begin:physical_ni_receive
  localparam bit CONNECTED=n==peer(c,0)||n==peer(c,1)||n==peer(c,2)||n==peer(c,3);
  if(CONNECTED)assign ni_receive_data[n][c]=data[c];
  else assign ni_receive_data[n][c]='0;
 end
 assign busy=|occupied;assign ready=!busy;''')
edit('cs_fabric.sv','rx_flit[n]=data[c];winner[n]', 'rx_flit[n]=ni_receive_data[n][c];winner[n]')
unit=dest/'tests/priority_unit_tb.sv';unit.parent.mkdir(exist_ok=True)
shutil.copyfile(R/'priority_unit_tb.sv',unit)
shutil.copyfile(R/'priority_router_main.cpp',dest/'sim/priority_router_main.cpp')

cases=json.loads(baseline['files']['CASES.json']['text'])
selected=[c for c in cases if c['name'].startswith('fit16_641103_')]
assert len(selected)==6
manifest=dict(base_commit='090a55d0',baseline_build=b['build_id'],image=b['image'],baseline_root=baseline['remote_path'],baseline_matrix=json.loads(baseline['files']['MATRIX.json']['text']),
    policy='CONFIG/CONFIG_ACK > DataS > GetS > MoE data/control; flit arbitration across independent VNs; same-VN RR and packet locks retained',
    exclusions=['No repeated existing RR/forced-CS/runtime/predictor runs','No synthesis or physical implementation','No change to queues, buffers, links, endpoint bandwidth or SRAM arbitration','C1-C4 remain with plan author'],
    cases=selected,baseline_source_sha256=b['source_sha256'])
manifest['source_sha256']={p.relative_to(dest).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for base in ['rtl','sim','tests'] for p in sorted((dest/base).rglob('*')) if p.is_file()}
manifest['source_digest']=hashlib.sha256(json.dumps(manifest['source_sha256'],sort_keys=True).encode()).hexdigest()[:16]
(dest/'SOURCE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('Prepared L2 source',manifest['source_digest'],'changed files:',[k for k,v in manifest['source_sha256'].items() if b['source_sha256'].get(k)!=v])
