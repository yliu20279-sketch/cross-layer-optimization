import os,json,pathlib,hashlib,subprocess,concurrent.futures,time,traceback,urllib.parse
ROOT=pathlib.Path('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe')
os.umask(0o022)
manifest=json.loads((ROOT/'DOWNLOAD_MANIFEST.json').read_text())
def save(name,value):
 p=ROOT/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(value,indent=2));os.chmod(str(t),0o644);os.replace(str(t),str(p))
def verify(p,item):
 if p.stat().st_size!=item['size']:raise ValueError('size '+item['path'])
 h=hashlib.sha256();g=hashlib.sha1();g.update(('blob %d\0'%item['size']).encode())
 with p.open('rb') as f:
  while True:
   b=f.read(8*1024*1024)
   if not b:break
   h.update(b);g.update(b)
 if item['sha256'] and h.hexdigest()!=item['sha256']:raise ValueError('sha256 '+item['path'])
 if item['git_blob'] and g.hexdigest()!=item['git_blob']:raise ValueError('git_blob '+item['path'])
 return dict(path=item['path'],size=item['size'],sha256=h.hexdigest(),git_blob=g.hexdigest(),matched=True)
def task(item):
 p=ROOT/item['path'];p.parent.mkdir(parents=True,exist_ok=True)
 if not p.exists():
  tmp=p.with_name(p.name+'.partial')
  if item['path'].startswith('source/'):
   raise RuntimeError('Source must be preloaded: '+item['path'])
  rel=item['path'][6:]
  mirror=json.loads((ROOT/'MODELSCOPE_METADATA.json').read_text())
  entry=next((x for x in mirror['Data']['Files'] if x['Path']==rel and x['Type']=='blob'),None)
  if not entry or entry['Size']!=item['size'] or (item['sha256'] and item['sha256']!=entry['Sha256']):
   raise RuntimeError('Mirror identity not matched: '+rel)
  url='https://modelscope.cn/models/robbyant/lingbot-video-moe-30b-a3b/resolve/057a08df568ddbd91efaf49944e8604ba3172a3a/'+urllib.parse.quote(rel,safe='/')
  for attempt in range(60):
   resume=['-C','-'] if item['size']>100000000 else []
   r=subprocess.run(['curl','-fL','--connect-timeout','20','--max-time','14400','--speed-limit','1024','--speed-time','90']+resume+['-o',str(tmp),url],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
   if r.returncode==0:break
   print('RETRY %s attempt %d curl %d'%(item['path'],attempt+1,r.returncode),flush=True)
   time.sleep(min(120,5*(attempt+1)))
  if r.returncode:raise RuntimeError('curl failed %s code %d: %s'%(item['path'],r.returncode,r.stderr.decode(errors='replace')[-300:]))
  row=verify(tmp,item);os.chmod(str(tmp),0o644);os.replace(str(tmp),str(p))
 else:row=verify(p,item)
 os.chmod(str(p),0o644);print('VERIFIED '+item['path'],flush=True);return row
try:
 save('DOWNLOAD_STATUS.json',dict(transport='SERVER_DIRECT_MODELSCOPE_NO_LOCAL_RELAY',status='DOWNLOADING',started=time.time(),files=len(manifest),bytes=sum(i['size'] for i in manifest)))
 rows=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
  for result in ex.map(task,manifest):
   rows.append(result);save('VERIFIED_FILES.json',rows)
 # Independent final verification of every payload, permissions, and index closure.
 rows=[verify(ROOT/x['path'],x) for x in manifest]
 for d,ds,fs in os.walk(str(ROOT)):
  os.chmod(d,0o755)
  for f in fs:os.chmod(os.path.join(d,f),0o644)
 bad=[]
 for d,ds,fs in os.walk(str(ROOT)):
  if (os.stat(d).st_mode&0o777)!=0o755:bad.append(d)
  for f in fs:
   q=os.path.join(d,f)
   if (os.stat(q).st_mode&0o777)!=0o644:bad.append(q)
 closure=[]
 for ix in (ROOT/'model').rglob('*.index.json'):
  j=json.loads(ix.read_text())
  for v in set(j.get('weight_map',{}).values()):
   if not (ix.parent/v).is_file():raise ValueError('index missing '+v)
  closure.append(str(ix.relative_to(ROOT)))
 assert not (ROOT/'model/refiner').exists()
 assert not bad
 save('VERIFIED_FILES.json',rows)
 save('FINAL_VERIFICATION.json',dict(status='PASS_DOWNLOAD_INTEGRITY_AND_UNIX_PERMISSION',files=len(rows),bytes=sum(x['size'] for x in rows),indices=closure,refiner_present=False,directory_mode='0755',file_mode='0644',permission_failures=bad,source_commit='dd5c231e793406c6a8893e9e4307008a9c2adfe4',weight_revision='f2e538f64afe00cc4ae674db2aeb52e2945edfd5',inference_run=False,finished=time.time()))
 save('DOWNLOAD_STATUS.json',dict(status='COMPLETE',finished=time.time()))
 print('COMPLETE',flush=True)
except Exception:
 save('DOWNLOAD_STATUS.json',dict(status='FAILED',error=traceback.format_exc(),finished=time.time()));raise
