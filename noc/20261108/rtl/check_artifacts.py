from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent
def main():
    data=json.loads((ROOT/'build/verification.json').read_text(encoding='utf-8'))
    assert data['all_passed'] and (ROOT/'build/runner.exit').read_text().strip()=='0'
    assert set(data['tests'])=={'tool_smoke','aux_router','transition','timeout','management'}
    assert data['negative_compiler_check']['rejected'] and data['negative_compiler_check']['returncode']!=0
    for name,test in data['tests'].items():
        log=(ROOT/'build'/f'{name}_simulation.log').read_text(encoding='utf-8')
        assert test['passed'] and log.strip()==test['output'] and f'PASS {name}' in log and 'FATAL' not in log
        assert test['compile_returncode']==0 and test['simulation_returncode']==0
        meta=test.get('compile_metadata',{})
        if meta:
            assert meta['ivlpp_returncode']==0 and meta['ivl_returncode']==0
            for field in ('config','preprocessed'):
                assert hashlib.sha256((ROOT/meta[field]).read_bytes()).hexdigest()==meta[field+'_sha256'],name
    for name,digest in data['sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    print(f"PASS audit: {len(data['sha256'])} source/test hashes, 5 HDL tests, actual_host={data['host']}")
if __name__=='__main__':main()
