"""Recover five published transport metadata files from the pinned Git commit.

Usage: python fetch_inputs.py --repo /path/to/cross-layer-optimization
These inputs are intentionally not added to the experiment commit.
"""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REF='073d3176733835eeafb4d5fdfbe7930c0a17945b'
BASE='experiments/qwen15_cc_dense_20261117/'
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',required=True);args=ap.parse_args()
    names=['fit4_161101','fit8_161101','fit16_641101','fit16_641102','fit16_641103']
    expected={}
    if (ROOT/'CASES.json').exists():
        for c in json.loads((ROOT/'CASES.json').read_text()):
            for name in names:
                if c['name'].startswith(name+'_'):expected[name]=c['input_sha256']
    manifest={}
    for name in names:
        rel=f'multitoken_results/remote_receipts/fits_v1/{name}/TRANSPORT.json'
        blob=subprocess.run(['git','-c','http.sslVerify=true','-C',args.repo,'show',REF+':'+BASE+rel],capture_output=True,check=True).stdout
        digest=hashlib.sha256(blob).hexdigest()
        if name in expected:assert digest==expected[name],name
        p=ROOT/'lyc_inputs'/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(blob)
        manifest[rel]=dict(sha256=digest,bytes=len(blob))
    (ROOT/'INPUT_PROVENANCE.json').write_text(json.dumps(dict(repository='https://github.com/yliu20279-sketch/cross-layer-optimization',commit=REF,files=manifest),indent=2))
    print('Recovered',len(manifest),'verified metadata files')
if __name__=='__main__':main()
