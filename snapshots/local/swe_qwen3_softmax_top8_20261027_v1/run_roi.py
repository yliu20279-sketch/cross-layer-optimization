import hashlib,json,os,subprocess,traceback
from pathlib import Path
R=Path(__file__).resolve().parent;O=R/'roi_attempt1';O.mkdir(exist_ok=False);A=R/'attempt1'
SN=Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim')
overlay=R.parent/'swe_qwen3_host_boundary_20261027_v1/cpu_overlay.cfg'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2))
try:
 frozen=json.loads((R/'ROI_FREEZE.json').read_text());assert all(sha(R/n)==h for n,h in frozen.items())
 cmd=['g++','-std=c++17','-O2','-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize','-mno-avx','-mno-avx2',str(R/'route_roi.cpp'),str(R/'route_kernel.cpp'),'-I'+str(SN/'include'),'-o',str(O/'route_roi')]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=60);dump(O/'BUILD.json',dict(command=cmd,returncode=p.returncode,stderr=p.stderr));p.check_returncode()
 dump(O/'SOURCE_BINDING.json',dict(files={str(p):sha(p) for p in [overlay,R/'route_kernel.cpp',R/'route_roi.cpp',SN/'run-sniper',SN/'config/gainestown.cfg',A/'real_logits_BF16.bin']},binary_sha256=sha(O/'route_roi')))
 cmd=[str(SN/'run-sniper'),'-n','4','-c','gainestown','-c',str(overlay),'--roi','--no-cache-warming','-d',str(O/'sim'),'--',str(O/'route_roi'),str(A/'real_logits_BF16.bin'),str(O/'IDs.bin'),str(O/'weights.bin')]
 with (O/'console.log').open('w') as log:p=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=180)
 dump(O/'COMMAND.json',dict(command=cmd,returncode=p.returncode));p.check_returncode()
 assert (O/'IDs.bin').read_bytes()==(A/'gold_IDs.bin').read_bytes()==(A/'new_IDs.bin').read_bytes()
 assert (O/'weights.bin').read_bytes()==(A/'gold_weights_BF16.bin').read_bytes()==(A/'new_weights_BF16.bin').read_bytes()
 dump(O/'STATUS.json',dict(state='PASS_LIMITED_TARGET_CPU_SOFTWARE_ROUTE_ROI',tokens=759,IDs_bits_exact=True,BF16_weights_bits_exact=True,
  scope='explicit host CPU fallback under gainestown-derived cold ROI proxy; no native NPU exp/TopK or transfer timing certification'))
 print('PASS: Sniper output IDs and weights exact to all759 captured tokens',flush=True)
except Exception:dump(O/'FAILURE.json',dict(error=traceback.format_exc()));raise
