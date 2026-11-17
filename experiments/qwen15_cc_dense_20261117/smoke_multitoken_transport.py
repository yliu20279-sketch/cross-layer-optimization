"""Exercise eight native endpoints and check actual overlapping packet intervals."""

import json

from run_multitoken_calibration import ARM, BINARY, OUT, ROOT, WaveTransport, digest, dump
from core.coupled_backend import LiveBackend


def main():
    backend = LiveBackend(BINARY,digest(BINARY.read_bytes()),OUT/'backend',
                          str(ROOT/'ramulator32.yaml'),controls='off',timeout=180)
    try:
        transport = WaveTransport(backend,ARM)
        transfers = []
        for src in range(8):
            for dst in ((src+1)%4+4*(src//4),(src+4)%8):
                offset = 17*src+dst
                transfers.append(((src,dst),src,dst,bytes((offset+i)%251 for i in range(4096))))
        circuits = ()
        if ARM=='project_noc':
            circuit = next(p for _,s,d,_ in transfers for p in transport.routes.get((s,d),()))
            circuits = (circuit,)
        actual = transport.send_wave('eight_endpoint_smoke',transfers,circuits)
        assert all(actual[key]==payload for key,_,_,payload in transfers)
        pending, peak = 0,0
        for _,delta in sorted([(r['inject_ns'],1) for r in transport.events]+[
            (r['wire_done_ns'],-1) for r in transport.events]):
            pending += delta
            peak = max(peak,pending)
        assert pending==0 and peak>=2
        active_circuits = sum(bool(r['circuit']) for r in transport.events)
        assert active_circuits==int(ARM=='project_noc')
        stats = backend.close()
        assert stats['packets']==stats['packet_callbacks'] and stats['transactions']==stats['callbacks']
        output = dict(status='PASS_EIGHT_ENDPOINT_CONCURRENT_TRANSFER',arm=ARM,active_endpoints=list(range(8)),
                      messages=len(actual),cross_partition_messages=8,gets=0,peak_in_flight=peak,
                      circuit_messages=active_circuits,
                      counters=stats,transfers=transport.events,windows=transport.waves)
        dump(OUT/'RESULT.json',output)
        print(json.dumps({k:v for k,v in output.items() if k not in ('counters','transfers')}))
    except BaseException:
        if not backend.closed:
            backend.abort()
        raise


if __name__=='__main__':
    main()
