"""Report generic sequential-netlist counts; not mapped area or timing."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
def main():
    receipt=json.loads((R/'SYNTHESIS.json').read_text());build=json.loads((R/'CURRENT_BUILD.json').read_text())
    assert receipt['status']=='PASS_NO_LATCH_OR_COMBINATIONAL_CYCLE'
    root=Path(receipt['path']);variants={}
    for mode in [0,1,2]:
        p=root/f'netlist_{mode}.json';module=json.loads(p.read_text())['modules']['experiment_top'];bits={}
        for c in module['cells'].values():
            if 'dff' in c['type'].lower():
                width=c['parameters'].get('WIDTH','1');bits[c['type']]=bits.get(c['type'],0)+int(width,2)
        variants[str(mode)]=dict(generic_cells=len(module['cells']),state_bits=sum(bits.values()),state_bits_by_cell_type=bits,
            netlist_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    hardware={}
    for name,value in build['source_sha256'].items():
        if name.startswith('rtl/'):
            old=Path(receipt['source_path'])/name[4:] if receipt.get('source_path') else None
            if old is not None:assert hashlib.sha256(old.read_bytes()).hexdigest()==value
            hardware[name]=value
    data=dict(status='PASS_STRUCTURAL_CHECK',variants=variants,rtl_sha256=hardware,
        scope='Generic RTL cells and register bits after proc/flatten/memory_map/opt. No standard-cell mapping, placement or timing analysis; endpoint SRAM service and software controller are excluded.')
    (R/'STRUCTURE.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(variants,indent=2))
if __name__=='__main__':main()
