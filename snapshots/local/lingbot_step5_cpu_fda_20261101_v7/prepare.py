import os,pathlib,json,hashlib,importlib.util,sys,subprocess,numpy as np,torch,shutil
R=pathlib.Path(__file__).resolve().parent;B=R.parent;P=B/'lingbot_step4_bitexact_20261029_v4';G=B/'lingbot_step3_capture_20261028_v1';V=B/'lingbot_step5_full_tp_20261101_v6';sys.path.insert(0,str(V));from math_local import tc,rb,rms
sys.path.insert(0,str(P/'upstream'));from tc_profiles import get_profile
spec=importlib.util.spec_from_file_location('generator',P/'tc_emulator_simd.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);source=mod._generate_c_source(get_profile('H100','bf16','fp32'));assert 'double ' not in source;(R/'portable.c').write_text(source)
from safetensors import safe_open
refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references']
def w(n):
 r=next(x for x in refs if x['name']=='blocks.0.'+n)
 with safe_open(r['canonical_file'],framework='pt',device='cpu') as f:return f.get_tensor(r['name']).float().numpy()
x=torch.load(G/'fixtures/full_on_s00_cond_L00_block_input.pt',weights_only=True)[0,:1].float().numpy();temb=torch.load(G/'fixtures/full_on_s00_cond_L00_temb6_constant_row.pt',weights_only=True).float().numpy();mods=torch.from_numpy(temb+w('scale_shift_table')).chunk(6,-1);inp=rb(rms(x,w('norm1.weight'))*(1+mods[1].numpy())+mods[0].numpy());gpuinp=torch.load(P/'external_attention_attempt1/cond_input.pt',weights_only=True)[0,:1].float().numpy();assert np.array_equal(inp.view(np.uint32),gpuinp.view(np.uint32))
def bits(a):return (a.view(np.uint32)>>16).astype('<u2')
for key,name in [('K','to_k'),('V','to_v')]:
 ww=w('attn.'+name+'.weight')[:128].copy();inp.astype('<f4');bits(inp).tofile(R/(key+'_x.bin'));bits(ww).tofile(R/(key+'_w.bin'));raw=tc.matmul(inp,ww.T);raw.astype('<f4').tofile(R/(key+'_F32_reference.bin'));gold=torch.load(P/'external_attention_attempt1'/('cond_'+name+'.pt'),weights_only=True)[0,:1,:128].float().numpy();bits(gold).tofile(R/(key+'_GPU.bin'));assert np.array_equal(rb(raw).view(np.uint32),gold.view(np.uint32))
A=B/'lingbot_step5_coupled_20261031_v4/case1';core=np.load(A/'N15/cond_core.npy')[:1];carry=np.load(A/'N14/cond_carry.npy')[:1];ow=w('attn.to_out.weight')[:,1920:2048].T.copy();bits(core).tofile(R/'Ocarry_x.bin');bits(ow).tofile(R/'Ocarry_w.bin');carry.astype('<f4').tofile(R/'Ocarry_initial.bin');bits(w('attn.to_out.bias')).tofile(R/'Ocarry_bias.bin');gold=torch.load(G/'fixtures/full_on_s00_cond_L00_attention_output.pt',weights_only=True)[0,:1].float().numpy();bits(gold).tofile(R/'Ocarry_GPU.bin');raw=carry.copy()
for k in range(0,128,16):raw=tc.block_fma_batch(raw,core[:,k:k+16].copy(),ow[k:k+16].copy())
assert np.array_equal(raw.view(np.uint32),np.load(A/'N15/cond_carry.npy')[:1].view(np.uint32));raw.astype('<f4').tofile(R/'Ocarry_F32_reference.bin');assert np.array_equal(rb(raw+w('attn.to_out.bias')).view(np.uint32),gold.view(np.uint32))
S=pathlib.Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim');flags=['-O2','-march=nehalem','-mno-avx','-mno-fma','-ffp-contract=off','-fno-fast-math'];commands=[['gcc',*flags,'-c',str(R/'portable.c'),'-o',str(R/'portable.o')],['g++',*flags,'-std=c++17','-I'+str(S/'include'),str(R/'kernel.cpp'),str(R/'portable.o'),'-lm','-o',str(R/'kernel')]]
for c in commands:subprocess.run(c,check=True,timeout=60)
for n in ['LICENSE','LICENSE.txt']:
 q=P/'upstream'/n
 if q.exists():shutil.copy2(q,R/'UPSTREAM_LICENSE');break
manifest=[dict(file=q.name,bytes=q.stat().st_size,sha256=hashlib.sha256(q.read_bytes()).hexdigest()) for q in sorted(R.iterdir()) if q.is_file() and q.suffix in ['.bin','.cpp','.c']];(R/'INPUT_BINDING.json').write_text(json.dumps(dict(inputs=manifest,commands=commands,source='fresh CPU norm/mod input matches stored GPU input; original weights; actual prior native head14 carry and head15 core',reference='raw FP32 SIMD software profile and original GPU BF16 outputs',full_target_timing=False),indent=2));print('PREPARED')
