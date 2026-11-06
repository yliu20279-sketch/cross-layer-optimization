"""Fetch only two pre-registered public holdout images; identities only, verify all registry hashes.
Build Docker-load archives locally because 113's registry connection is refused.
No registry token is printed or persisted. Images are not executed locally.
"""
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parent
CACHE=ROOT.parent/'swe_qwen3_step3_gpu_20261026_v1/registry_cache';CACHE.mkdir(exist_ok=True)
TASKS=['astropy__astropy-12907','astropy__astropy-14182']
TOKEN_CACHE={}
def public_token(repo):
    value=json.load(urllib.request.urlopen('https://auth.docker.io/token?service=registry.docker.io&scope=repository:'+repo+':pull',timeout=20))['token']
    TOKEN_CACHE[repo]=value;return value
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for c in iter(lambda:f.read(8*1024*1024),b''):h.update(c)
    return h.hexdigest()

def fetch(url,path,expected,token,expected_bytes=None):
    if path.is_file() and sha(path)==expected:return
    part=path.with_suffix('.partial')
    repo=url.split('/v2/')[1].split('/blobs/')[0]
    for attempt in range(3):
        try:
            request=urllib.request.Request(url,headers={'Authorization':'Bearer '+TOKEN_CACHE.get(repo,token)})
            with urllib.request.urlopen(request,timeout=40) as r,part.open('wb') as f:
                shutil.copyfileobj(r,f,8*1024*1024)
            if expected_bytes is not None and part.stat().st_size!=expected_bytes:raise RuntimeError('Blob byte count mismatch')
            if sha(part)!=expected:raise RuntimeError('Blob digest mismatch')
            part.rename(path);return
        except Exception as error:
            if getattr(error,'code',None)==401:public_token(repo)
            if attempt==2:raise
            time.sleep(1)

def main():
    if shutil.disk_usage(ROOT).free<12*2**30:raise RuntimeError('Local free space budget failed')
    records=[]
    for task in TASKS:
        repo=('swebench/sweb.eval.x86_64.'+task).replace('__','_1776_').lower()
        token=public_token(repo)
        req=urllib.request.Request('https://registry-1.docker.io/v2/'+repo+'/manifests/latest',headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.docker.distribution.manifest.v2+json'})
        with urllib.request.urlopen(req,timeout=30) as r:
            raw=r.read();digest=r.headers.get('Docker-Content-Digest')
        assert digest=='sha256:'+hashlib.sha256(raw).hexdigest()
        manifest=json.loads(raw);index_digest=None
        if 'manifests' in manifest:
            index_digest=digest
            matches=[x for x in manifest['manifests'] if x.get('platform',{}).get('architecture')=='amd64' and x.get('platform',{}).get('os')=='linux']
            assert len(matches)==1
            (CACHE/(task+'.index.json')).write_bytes(raw)
            selected=matches[0]['digest']
            req=urllib.request.Request('https://registry-1.docker.io/v2/'+repo+'/manifests/'+selected,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'})
            with urllib.request.urlopen(req,timeout=30) as r:raw=r.read();digest=r.headers.get('Docker-Content-Digest')
            assert digest==selected=='sha256:'+hashlib.sha256(raw).hexdigest()
            manifest=json.loads(raw)
        size=sum(x['size'] for x in manifest['layers'])
        if size>3*2**30:raise RuntimeError('Dev image exceeds predeclared3 GiB compressed budget')
        prior=CACHE/(task+'.manifest.json')
        if prior.exists() and prior.read_bytes()!=raw:raise RuntimeError('Official latest tag changed; refusing silent image revision')
        prior.write_bytes(raw)
        print('MANIFEST_VERIFIED',task,size,digest,flush=True)
        config=manifest['config'];cid=config['digest'].split(':')[1];config_path=CACHE/(cid+'.json')
        fetch('https://registry-1.docker.io/v2/'+repo+'/blobs/'+config['digest'],config_path,cid,token,config['size'])
        image_config=json.loads(config_path.read_text());diff_ids=image_config['rootfs']['diff_ids']
        layers=[];uncompressed=0
        for i,layer in enumerate(manifest['layers']):
            value=layer['digest'].split(':')[1];blob=CACHE/(value+'.blob')
            fetch('https://registry-1.docker.io/v2/'+repo+'/blobs/'+layer['digest'],blob,value,token,layer['size'])
            diff=diff_ids[i].split(':')[1];plain=CACHE/(diff+'.layer.tar')
            if not plain.is_file() or sha(plain)!=diff:
                with gzip.open(blob,'rb') as src,plain.open('wb') as dst:
                    copied=0
                    while True:
                        b=src.read(8*1024*1024)
                        if not b:break
                        copied+=len(b)
                        if copied>6*2**30:raise RuntimeError('Layer decompression budget failed')
                        dst.write(b)
                if sha(plain)!=diff:raise RuntimeError('Uncompressed diffID mismatch')
            uncompressed+=plain.stat().st_size
            if uncompressed>8*2**30:raise RuntimeError('Uncompressed image budget failed')
            layers.append((plain,diff+'/layer.tar'))
            print('LAYER_VERIFIED',task,i+1,len(manifest['layers']),layer['size'],flush=True)
        archive=ROOT/(task+'.docker.tar.gz')
        dm=[{'Config':cid+'.json','RepoTags':[repo+':latest'],'Layers':[name for _,name in layers]}]
        encoded=json.dumps(dm).encode()
        with tarfile.open(archive,'w:gz',compresslevel=1) as tar:
            tar.add(config_path,arcname=cid+'.json')
            for plain,name in layers:tar.add(plain,arcname=name)
            info=tarfile.TarInfo('manifest.json');info.size=len(encoded);tar.addfile(info,io.BytesIO(encoded))
        records.append(dict(task=task,repository=repo,registry_manifest_digest=digest,registry_index_digest=index_digest,config_digest='sha256:'+cid,
            compressed_layer_bytes=size,uncompressed_layer_bytes=uncompressed,archive=archive.name,archive_bytes=archive.stat().st_size,archive_sha256=sha(archive),
            scope='Official public image, all compressed layer digests and uncompressed diffIDs verified; no local execution'))
        (ROOT/'HOLDOUT_IMAGE_ARCHIVES.json').write_text(json.dumps(records,indent=2))
        print('ARCHIVE_VERIFIED',task,archive.stat().st_size,flush=True)

if __name__=='__main__':main()
