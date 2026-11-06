"""Read source-only snapshots; never execute experiment code."""
import argparse,hashlib,json,os,re,tarfile,tempfile
from pathlib import Path

LOCAL_PREFIXES=('ca_','swe_qwen3_','swe_bmk_','lingbot_','mini_swe_operator_graph_','qwen15_p0_','qwen15_step2_','qwen3_30b_a3b_v3_6_experiment','qwen1_5_moe_a2_7b_v3_6')
REMOTE_PREFIXES=('ca_','swe_qwen3_','swe_v7_','lingbot_','qwen15_step4_','qwen3_30b_a3b_v3_6_experiment','qwen1_5_moe_a2_7b_v3_6')
EXT={'.py','.c','.cpp','.cc','.h','.hpp','.sh','.ps1','.md','.json','.yaml','.yml','.toml','.cfg','.ini','.cmake','.gv','.xml','.patch','.diff','.mk','.sha256'}
PRUNE={'.git','.ssh','.aws','.codex','.agents','env','venv','.venv','node_modules','__pycache__','site-packages','runs','run1','run2','case1','case2','build','build_04','remote_review','server_results','generated','data','weights','models','frozen_inputs','reference','logs','outputs','output'}
SECRET=re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----|AKIA[0-9A-Z]{16})')

def collect(root,remote=False):
 rows=[];excluded=[]
 for directory in sorted(root.iterdir()):
  if not directory.is_dir() or directory.is_symlink() or not directory.name.startswith(REMOTE_PREFIXES if remote else LOCAL_PREFIXES):continue
  for base,dirs,files in os.walk(directory,followlinks=False):
   dirs[:]=[d for d in dirs if d not in PRUNE and not (Path(base)/d).is_symlink() and not d.startswith(('proc_','case0','proc1'))]
   for name in sorted(files):
    p=Path(base)/name;rel=p.relative_to(root).as_posix()
    build_or_legal=name.lower().startswith(('license','copying','notice','requirements')) or name in ('Makefile','CMakeLists.txt')
    if p.is_symlink() or (p.suffix.lower() not in EXT and not build_or_legal):continue
    if any(t in name.lower() for t in ('consultation','chat_','conversation','credential','secret','token.json')):continue
    size=p.stat().st_size
    limit=524288 if p.suffix.lower()=='.json' else 2097152
    if size>limit:excluded.append({'path':rel,'reason':'size limit','bytes':size});continue
    b=p.read_bytes()
    if SECRET.search(b):excluded.append({'path':rel,'reason':'credential pattern'});continue
    rows.append((p,dict(path=rel,bytes=len(b),sha256=hashlib.sha256(b).hexdigest())))
 return rows,excluded

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--root',required=True);a.add_argument('--archive',required=True);a.add_argument('--remote',action='store_true');args=a.parse_args()
 root=Path(args.root).resolve();rows,excluded=collect(root,args.remote)
 with tarfile.open(args.archive,'w:gz') as tf:
  for p,row in rows:tf.add(p,arcname=row['path'],recursive=False)
  meta=json.dumps({'host':'113' if args.remote else 'local','root':str(root),'files':[r for _,r in rows],'excluded':excluded,'atomic_snapshot':False},ensure_ascii=False,indent=2).encode()
  import io
  info=tarfile.TarInfo('SOURCE_COLLECTION.json');info.size=len(meta);tf.addfile(info,io.BytesIO(meta))
 print(json.dumps({'files':len(rows),'bytes':sum(r['bytes'] for _,r in rows),'archive':str(args.archive),'excluded':len(excluded)}))
