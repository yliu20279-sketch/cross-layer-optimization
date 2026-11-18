"""Convert the exact RTL snapshot and check its flattened sequential netlist."""
import concurrent.futures,hashlib,json,re,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent
SOURCES=['noc_pkg.sv','fifo.sv','benes8.sv','width_link.sv','split_width_link.sv','xy_router.sv','mesh.sv','hiband_fabric.sv','typed_ni.sv','cs_fabric.sv','configuration_sequencer.sv','experiment_top.sv']
def main():
    build=json.loads((R/'CURRENT_BUILD.json').read_text());src=Path(build['path'])/'source/rtl'
    script_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    out=R/'synthesis'/(build.get('build_id',build['source_digest'])+'_'+script_sha[:8]);out.mkdir(parents=True,exist_ok=True)
    image=build['image'];tool=R/'tools/sv2v';tool.chmod(0o755)
    docker=['docker','run','--rm','--network','none','--cpus','2','--memory','12g','--mount',f'type=bind,src={R},dst=/work','-w','/work',image]
    rel=lambda p:'/work/'+p.relative_to(R).as_posix()
    ledger=dict(status='converting',script_sha256=script_sha,source_path=str(src),rtl_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in src.iterdir() if p.is_file()},rtl_digest=build['source_digest'],sv2v_sha256=hashlib.sha256(tool.read_bytes()).hexdigest(),image=image,variants={})
    def save():(out/'RECEIPT.json').write_text(json.dumps(ledger,indent=2));(R/'SYNTHESIS.json').write_text(json.dumps(dict(path=str(out),**ledger),indent=2))
    save();start=time.time()
    with (out/'converted.v').open('w') as f,(out/'CONVERSION.log').open('w') as log:
        p=subprocess.run(docker+[rel(tool),'--top=experiment_top','-I',rel(src),*map(lambda n:rel(src/n),SOURCES)],stdout=f,stderr=log,timeout=300)
    if p.returncode:ledger['status']='CONVERSION_FAILED';save();raise RuntimeError((out/'CONVERSION.log').read_text()[-3000:])
    # sv2v emits explicit sensitivity lists containing unpacked array names.
    # Yosys 0.23 rejects those names. @* is the Verilog equivalent for these
    # combinational blocks; sequential edge-sensitive blocks are untouched.
    converted=out/'converted.v';raw=converted.read_text()
    ledger['raw_converted_sha256']=hashlib.sha256(raw.encode()).hexdigest()
    normalized,count=re.subn(r'always @\((?!posedge |negedge )[^\n]*\) begin', 'always @* begin',raw)
    converted.write_text(normalized);ledger['combinational_sensitivity_normalizations']=count
    ledger['status']='checking';ledger['conversion_seconds']=time.time()-start;ledger['converted_sha256']=hashlib.sha256((out/'converted.v').read_bytes()).hexdigest();save()
    def check_variant(mode):
        net=out/f'netlist_{mode}.json'
        # Yosys 0.23 can re-elaborate a parameter-renamed top twice under -defer.
        # Set the equivalent top-level default before frontend elaboration.
        text=(out/'converted.v').read_text();start_top=text.index('module experiment_top')
        suffix,n=re.subn(r'(parameter\s+[^;\n]*\bDUAL\s*=\s*)[^;]+;',lambda m:m.group(1)+str(mode)+';',text[start_top:],count=1)
        assert n==1,'DUAL top parameter was not found'
        variant=out/f'variant_{mode}.v';variant.write_text(text[:start_top]+suffix)
        script=f'''read_verilog -defer {rel(variant)}
hierarchy -check -top experiment_top
proc
opt -fast
memory_map
opt -fast
flatten
opt -fast
check -assert
select -assert-none t:$dlatch t:$adlatch
scc -expect 0
stat
write_json {rel(net)}
'''
        path=out/f'check_{mode}.ys';path.write_text(script);start=time.time()
        with (out/f'CHECK_{mode}.log').open('w') as f:p=subprocess.run(docker+['yosys','-Q','-T','-s',rel(path)],stdout=f,stderr=subprocess.STDOUT,timeout=1800)
        result=dict(returncode=p.returncode,seconds=time.time()-start,elaboration_sha256=hashlib.sha256(variant.read_bytes()).hexdigest())
        if p.returncode:
            result['error']=(out/f'CHECK_{mode}.log').read_text()[-3000:]
            return mode,result
        data=json.loads(net.read_text());mod=data['modules']['experiment_top'];types={}
        for cell in mod['cells'].values():types[cell['type']]=types.get(cell['type'],0)+1
        result.update(cell_count=len(mod['cells']),cell_types=types,netlist_sha256=hashlib.sha256(net.read_bytes()).hexdigest())
        return mode,result
    # Two independent variants can be checked concurrently. Fast optimization
    # propagates constants and removes dead state without expensive mux-tree
    # minimization, which is unnecessary for structural correctness checks.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        pending={pool.submit(check_variant,mode):mode for mode in [0,1,2]}
        for f in concurrent.futures.as_completed(pending):
            mode=pending[f]
            try:mode,result=f.result()
            except Exception as e:result=dict(returncode=-1,error=repr(e))
            ledger['variants'][str(mode)]=result;save()
            print('structural',mode,result['returncode'],flush=True)
    ledger['status']='PASS_NO_LATCH_OR_COMBINATIONAL_CYCLE' if all(v['returncode']==0 for v in ledger['variants'].values()) else 'CHECK_FAILED'
    save()
    if ledger['status']=='CHECK_FAILED':raise RuntimeError('structural variant check failed; see receipt')
if __name__=='__main__':main()
