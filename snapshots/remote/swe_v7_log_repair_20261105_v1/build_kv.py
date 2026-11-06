import subprocess,json
from pathlib import Path
r=Path(__file__).resolve().parent
cmds=json.loads((r/"kv_build_commands.json").read_text())
with (r/"kv_build.log").open("w") as f:
 for c in cmds:
  p=subprocess.run(c,cwd='/mnt/sda1/h3240101068/qwen3_30b_a3b_v3_6_experiment/results/expert_page_layout_v1/toolchain/popnet_layout/build_page',stdout=f,stderr=subprocess.STDOUT,timeout=120)
  if p.returncode:break
(r/"KV_BUILD_EXIT.json").write_text(json.dumps({"returncode":p.returncode}))
