from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent
s=(R/'run_dispatch.py').read_text().replace("D=R/'attempt1'","D=R/'attempt2'").replace("R/'FREEZE.json'","R/'FREEZE_v2.json'")
needle="  reject(kind+'_TX_free_before_tail',lambda:pe[records[0]['src']].free(records[0]['tx']))"
assert needle in s
s=s.replace(needle,needle+"\n  for r in records:\n   sr=pe[r['src']];sr.need(r['tx']);r['stage_ready']=r['source_ready'];sr.service(r['tx']['bytes'],0,kind+'_TX_drain');r['source_ready']=sr.now")
(R/'run_dispatch_v2.py').write_text(s)
p=json.loads((R/'PROTOCOL.json').read_text());p['TX_SRAM_service']='Explicit source SRAM read/drain for every metadata and token frame, local or remote, before native NoC injection; readiness includes drain completion.'
p['amendment']='attempt1 payload/lifetime success retained but omitted TX drain service; attempt2 selected, at most300s; no old source/library overwrite'
(R/'PROTOCOL_v2.json').write_text(json.dumps(p,indent=2))
files={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in ['runtime.py','run_dispatch_v2.py','PROTOCOL_v2.json']}
(R/'FREEZE_v2.json').write_text(json.dumps(files,indent=2))
(R/'TX_SERVICE_AMENDMENT.json').write_text(json.dumps(dict(initial='attempt1 preserved: numerical and lifetimes passed, but TX SRAM read service omitted',correction='explicit drain reads before injection/local copy, include completion in source_ready; same payload and numeric acceptance',new_attempt='attempt2',files=files),indent=2))
