"""Read-only fixed-path evidence retrieval after remote gated pipeline seals its package."""
import json,subprocess,time,hashlib,tarfile,datetime
from pathlib import Path
L=Path(__file__).resolve().parent;P='/mnt/sda1/h3240101068/'
DEVELOPMENT='swe_qwen3_step3_progress_20261027_v4';ACCEPTANCE='swe_qwen3_step3_acceptance_20261027_v1'
def probe(root,name):
    try:
        p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','myserver-113','cat '+P+root+'/'+name],capture_output=True,text=True,timeout=30)
        return json.loads(p.stdout) if p.returncode==0 else None
    except (subprocess.TimeoutExpired,json.JSONDecodeError):return None
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while chunk:=f.read(8*1024*1024):h.update(chunk)
    return h.hexdigest()
def collect(root,delivery):
    out=L.parent/root;out.mkdir(exist_ok=True)
    archive=out/'EVIDENCE.tar.gz';temporary=out/'EVIDENCE.download'
    if archive.exists():assert digest(archive)==delivery['archive_sha256'],'Preserve existing distinct archive'
    else:
        subprocess.run(['scp','myserver-113:'+P+root+'/EVIDENCE.tar.gz',str(temporary)],check=True,timeout=3600)
        assert temporary.stat().st_size==delivery['archive_bytes'] and digest(temporary)==delivery['archive_sha256']
        temporary.rename(archive)
    count=0;total=0;manifest=None;seen=set()
    with tarfile.open(archive,'r|gz') as tar:
        for member in tar:
            assert member.isfile(),'Unexpected non-file member'
            stream=tar.extractfile(member)
            if member.name=='FILE_MANIFEST.json':manifest={x['path']:x for x in json.load(stream)};continue
            assert manifest is not None and member.name in manifest and member.name not in seen
            h=hashlib.sha256();size=0
            while chunk:=stream.read(8*1024*1024):h.update(chunk);size+=len(chunk)
            row=manifest[member.name];assert row['bytes']==size and row['sha256']==h.hexdigest(),member.name
            seen.add(member.name);count+=1;total+=size
    assert seen==set(manifest) and count==delivery['payload_files'] and total==delivery['payload_bytes']
    receipt=dict(state='PASS_ALL_DELIVERED_MEMBERS_SHA256',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        archive_sha256=delivery['archive_sha256'],archive_bytes=delivery['archive_bytes'],payload_files=count,payload_bytes=total,
        scope='local byte integrity only; no new numerical/NPU certification')
    (out/'LOCAL_EVIDENCE_VERIFICATION.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    for name in ['REPORT.md','FINAL_STATUS.json','DELIVERY.json','DEVELOPMENT_GATE.json','BACKEND_EQUIVALENCE.json',
                 'OFFICIAL_EVALUATION.json','FREEZE.json','PROBLEM_ACCESS.json','CAPTURE_AUDIT_ALL.json','FROZEN_METHOD_VERIFICATION.json']:
        # Optional metadata may not exist for the other branch. Package remains canonical.
        subprocess.run(['scp','-q','myserver-113:'+P+root+'/'+name,str(out/name)],capture_output=True,timeout=120)
    print(json.dumps(dict(root=root,verification=receipt)),flush=True)
    return receipt
def main():
    deadline=time.monotonic()+12*3600
    while time.monotonic()<deadline:
        waiting=probe(DEVELOPMENT,'WAIT_STATUS.json')
        (L/'COLLECTION_STATUS.json').write_text(json.dumps(dict(state='WAITING_FOR_REMOTE_GATE_OR_PACKAGE',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),remote_wait=waiting),indent=2),encoding='utf-8')
        if waiting and waiting['state']=='PREVIOUS_METHOD_PASSED_CANDIDATE_SKIPPED':
            (L/'COLLECTION_STATUS.json').write_text(json.dumps(dict(state='PREVIOUS_METHOD_PASSED_CANDIDATE_SKIPPED'),indent=2));return
        delivery=probe(DEVELOPMENT,'DELIVERY.json')
        if delivery:
            receipts={DEVELOPMENT:collect(DEVELOPMENT,delivery)}
            additional=probe(ACCEPTANCE,'DELIVERY.json')
            if additional:receipts[ACCEPTANCE]=collect(ACCEPTANCE,additional)
            (L/'LOCAL_COLLECTION_COMPLETE.json').write_text(json.dumps(receipts,indent=2),encoding='utf-8');return
        failure=probe(DEVELOPMENT,'PIPELINE_FAILURE.json') or probe(DEVELOPMENT,'WAIT_FAILURE.json')
        if failure:
            (L/'REMOTE_PIPELINE_FAILURE.json').write_text(json.dumps(failure,indent=2),encoding='utf-8');raise RuntimeError(failure)
        time.sleep(30)
    raise RuntimeError('Read-only collection twelve-hour deadline exceeded')
if __name__=='__main__':main()
