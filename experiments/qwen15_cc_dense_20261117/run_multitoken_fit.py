"""Measure prefix scaling through the same real-weight layer and native backend."""

import json
import time
import traceback

import numpy as np

import run_multitoken_calibration as cal


def sample():
    tokens, seed = cal.TOKENS, cal.SEED
    assert tokens in (4,8,16,32) and cal.ARM=='hiband_reference'
    root, out, binary = cal.ROOT, cal.OUT, cal.BINARY
    out.mkdir()
    source = cal.read(root/'contracts/qwen15_tensor_inventory.json')
    store = cal.TargetArtifactStore(list(source['objects'].values()),'F16')
    codec = cal.read(root/'evidence/REMOTE_BUILD_LIVE_02.json')
    config = cal.read(root/'upstream/qwen15_config.json')
    hidden = np.random.default_rng(seed).normal(0,.09,(tokens,cal.SPEC['hidden'])).astype('<f2').tobytes()
    (out/'L5_INPUT.bin').write_bytes(hidden)
    binary_sha = cal.digest(binary.read_bytes())
    placement = {e:e%8 for e in range(cal.SPEC['experts'])}
    cal.dump(out/'INPUTS.json',dict(tokens=tokens,seed=seed,layer=5,arm=cal.ARM,
                                   input_sha256=cal.digest(hidden),binary_sha256=binary_sha,placement=placement,
                                   gets=0,thermal=False,opp=1.0))
    wall_begin = time.monotonic()
    backend = cal.LiveBackend(binary,binary_sha,out/'backend',str(root/'ramulator32.yaml'),
                              controls='off',timeout=72000)
    try:
        native = cal.TiledPayload(backend,codec['payload_library'],codec['payload_sha256'])
        transfer = cal.WaveTransport(backend,cal.ARM)
        execution_begin = time.monotonic()
        output,routes,clock = cal.with_parallel_transfers(placement,cal.SPEC,store,native,transfer,config,
                                                          list(range(tokens)),hidden)
        execution_seconds = time.monotonic()-execution_begin
        assert len(output)==tokens*cal.SPEC['hidden']*2 and np.isfinite(np.frombuffer(output,dtype='<f2')).all()
        native.close_weights()
        counts = backend.close()
        assert counts['transactions']==counts['callbacks'] and counts['packets']==counts['packet_callbacks']
        (out/'L5_OUTPUT.bin').write_bytes(output)
        cal.dump(out/'ROUTES.json',routes)
        cal.dump(out/'MATRICES.json',native.calls)
        cal.dump(out/'TRANSPORT.json',dict(events=transfer.events,waves=transfer.waves))
        qk_pv = sum(m['complete']-m['start'] for m in native.calls if m['label'] in ('attention_QK','attention_PV'))
        attention = clock[1]-clock[0]
        moe = clock[2]-clock[1]
        timings = dict(status='PASS_MULTITOKEN_FIT_SAMPLE',tokens=tokens,seed=seed,
                       layer_ns=attention+moe,attention_ns=attention,attention_qk_pv_ns=qk_pv,moe_ns=moe,
                       execution_wall_seconds=execution_seconds,total_wall_seconds=time.monotonic()-wall_begin,
                       input_sha256=cal.digest(hidden),output_sha256=cal.digest(output),binary_sha256=binary_sha,
                       active_endpoints=sorted({e[k] for e in transfer.events for k in ('src','dst')}),
                       endpoint_pairs=len({(e['src'],e['dst']) for e in transfer.events}),
                       messages=len(transfer.events),matrices=len(native.calls))
        cal.dump(out/'RESULT.json',timings)
        print(json.dumps(timings),flush=True)
    except BaseException:
        (out/'ERROR.txt').write_text(traceback.format_exc())
        if not backend.closed:
            backend.abort()
        raise


if __name__=='__main__':
    sample()
