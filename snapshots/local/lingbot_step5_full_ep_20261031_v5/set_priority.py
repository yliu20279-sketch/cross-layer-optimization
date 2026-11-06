import pathlib,os,json
roots=['/mnt/sda1/h3240101068/lingbot_step5_coupled_20261031_v4','/mnt/sda1/h3240101068/lingbot_step5_full_ep_20261031_v5'];changed=[]
for q in pathlib.Path('/proc').iterdir():
 if not q.name.isdigit():continue
 try:
  if q.stat().st_uid!=os.getuid():continue
  argv=[x.decode() for x in (q/'cmdline').read_bytes().split(b'\0') if x]
  if not argv:continue
  scoped=any(any(v.startswith(root+'/') for v in argv) for root in roots)
  allowed=pathlib.Path(argv[0]).name in ['python','python3','interchiplet','ramulator2']
  if scoped and allowed:
   pid=int(q.name);os.setpriority(os.PRIO_PROCESS,pid,10);changed.append(dict(pid=pid,nice=os.getpriority(os.PRIO_PROCESS,pid)))
 except (FileNotFoundError,ProcessLookupError,PermissionError):pass
pathlib.Path(__file__).with_name('PRIORITY_RECEIPT.json').write_text(json.dumps(changed,indent=2));print('priority updated for scoped own processes',len(changed))
