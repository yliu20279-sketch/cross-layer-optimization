from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent;B=R.parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
checks=[]
for name in ['PRE_RUN_FREEZE.json','COUPLED_FREEZE.json','COUPLED_FREEZE_v2.json']:
 frozen=json.loads((R/name).read_text())
 for path,h in frozen.items():
  actual=sha(R/path);assert actual==h;checks.append(dict(freeze=name,path=path,sha256=actual))
binding=json.loads((R/'attempt1/SOURCE_BINDING.json').read_text())
SN=Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim')
for key,p in [('source_sha256',R/'codec_roi.cpp'),('binary_sha256',R/'attempt1/codec_roi'),('overlay_sha256',R/'cpu_overlay.cfg'),('base_config_sha256',SN/'config/gainestown.cfg'),('sniper_launcher_sha256',SN/'run-sniper'),('codec_header_sha256',B/'olmoearth_v3_6_integration_20261025_v1/source/NPUSim/npusim_tensor_codec.h')]:
 assert sha(p)==binding[key]
old=json.loads((B/'swe_qwen3_native_router_fragment_20261027_v1/attempt2/PRE_RUN_BINDING.json').read_text())
for path,item in old['files'].items():assert sha(path)==item['sha256']
report=dict(state='PASS_FROZEN_CODE_AND_REUSED_NATIVE_SOURCE_IDENTITIES',frozen_files=checks,old_bound_files_unchanged=len(old['files']),CPU_binary_and_overlay_unchanged=True)
(R/'SOURCE_VERIFICATION.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(state=report['state'],frozen_files=len(checks))))
