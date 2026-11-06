from pathlib import Path
p=Path('tools/run_interleaved.py')
s=p.read_text()
marker="        for layer in sessions.values():\n            layer.close()"
patch="""            if phase=='prefill':
                layout,generation=backend.layout()
                require(len(layout)>=20 and layout[0,0]==layout[1,0],'invalid migration probe domain')
                candidate=layout[:,:3].copy()
                candidate[0,2],candidate[1,2]=candidate[1,2],candidate[0,2]
                before=backend.clock
                backend.install_layout(candidate,generation,10)
                after=backend.clock
                actual,new_generation=backend.layout()
                require(new_generation==generation+1 and np.array_equal(actual[:,:3],candidate),'mapping commit mismatch')
                save('DUAL_REQUEST_MIGRATION.json',{'before_ns':before,'after_ns':after,
                    'generation_before':generation,'generation_after':new_generation,
                    'prefill_complete_ns':{name:layer.phases[-1]['complete'] for name,layer in sessions.items()},
                    'fixed_diagnostic_swap':True,'cpu_pcie_cache_cost_verified':False})
        migration=read(out/'DUAL_REQUEST_MIGRATION.json')
        require(max(migration['prefill_complete_ns'].values())<=migration['before_ns']
                <=migration['after_ns']<=min(layer.phases[-1]['start'] for layer in sessions.values()),
                'migration escaped dual-request dependency window')
"""
assert marker in s
p.write_text(s.replace(marker,patch+marker))
