from pathlib import Path
import sys

root = Path(sys.argv[1])
driver = (root/'tools/run_coupled_layer.py').read_text()
start = driver.index('        layer=CoupledLayer')
stop = driver.index("    progress('finished')",start)
driver = driver[:start] + """
        sessions = {name: CoupledLayer(spec,config,store,native,transport,placement,dtype)
                    for name in ('request_a','request_b')}
        trace = []
        outputs = {}
        for pos, phase in enumerate(('prefill','decode')):
            jobs = {}
            for i, (name, layer) in enumerate(sessions.items()):
                hidden = native.encode(np.sin(np.arange(spec['hidden'],dtype='<f4')*.017
                                      + np.float32(pos)*.21 + np.float32(i)*.37)*.125,dtype)
                (out/(name+'_'+phase+'_input.bin')).write_bytes(hidden)
                jobs[name] = layer.forward_steps(hidden,[pos],[17 if i==0 else 19],request_id=name)
            while jobs:
                for name in list(jobs):
                    begin = backend.clock
                    try:
                        rank = next(jobs[name])
                        trace.append({'request':name,'phase':phase,'rank':rank,
                                      'begin_ns':begin,'end_ns':backend.clock})
                    except StopIteration as done:
                        del jobs[name]
                        raw = done.value
                        require(np.isfinite(native.decode(raw,dtype)).all(),'nonfinite output')
                        (out/(name+'_'+phase+'_output.bin')).write_bytes(raw)
                        outputs[name+'_'+phase] = hashlib.sha256(raw).hexdigest()
                    save('REQUEST_TRACE.json',trace)
            handles = set()
            for name, layer in sessions.items():
                require(len(layer.cache)==spec['tp'],'missing rank cache')
                for (which,rank), entry in layer.cache.items():
                    require(entry['length']==pos+1,'incorrect KV length')
                    for member in ('k','v'):
                        handle = entry[member]
                        require(handle not in handles,'aliased KV handle')
                        handles.add(handle)
                        raw = backend.get(handle)
                        (out/f'{name}_{phase}_L{which}_R{rank}_{member}.bin').write_bytes(raw)
                save(name+'_KV_EVENTS.json',layer.kv_events)
                save(name+'_PHASES.json',layer.phases)
        for layer in sessions.values():
            layer.close()
        native.close_weights()
        summary = backend.close()
        save('RESULT.json',{'status':'INTERLEAVED_RANK_PROBE_COMPLETE',
             'outputs':outputs,'summary':summary,'formal_performance':False,
             'p0_1b_complete':False,'independent_reference_verified':False})
""" + driver[stop:]
(root/'tools/run_interleaved.py').write_text(driver)
