import pathlib,json
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_completion_20261028_v3')
r=json.loads((P/'primitive_attempt2_singlethread/RESULT.json').read_text());assert r['independent_C_CPU_failed']==0
m=json.loads((P/'primitive_attempt2_singlethread/METRICS.json').read_text())
g=set()
for x in m:
 if 'independent C' not in x['scope']:continue
 stage=x['name'].rsplit('_',1)[-1]
 if stage in ['gate','up']:g.add((x['shape'][0],768,2048))
 elif stage=='down':g.add((x['shape'][0],2048,768))
(P/'CERTIFIED_GEOMETRIES.json').write_text(json.dumps(dict(BF16_bias_free_MNK=sorted(g),scope='only observed singlethread LingBot expert geometries; not generic GEMM/GPU certificate'),indent=2))
