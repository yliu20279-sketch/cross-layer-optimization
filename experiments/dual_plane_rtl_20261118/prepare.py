"""Freeze trace-derived traffic; never replay completion stamps as releases."""
import hashlib, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUTS = ROOT / 'lyc_inputs'

def main():
    out = ROOT / 'cases'; out.mkdir(exist_ok=True)
    manifest = []
    for name, tokens in [('fit4_161101',4), ('fit8_161101',8),
                         ('fit16_641101',16),('fit16_641102',16),('fit16_641103',16)]:
        p = INPUTS / 'multitoken_results/remote_receipts/fits_v1' / name / 'TRANSPORT.json'
        raw = p.read_bytes(); data = json.loads(raw)
        for pattern in ['hotspot', 'distributed']:
            waves = []
            for wi, wave in enumerate(data['waves']):
                es = data['events'][wave['first']:wave['first']+wave['count']]
                assert all(e['ready_ns'] == wave['ready_ns'] for e in es)
                # Request already contains its header (32B). Reply carries a
                # 32B header and 64B payload. Bank read is not network traffic.
                moe_payload = sum(e['bytes'] for e in es)
                moe_wire = sum(e['bytes'] + math.ceil(e['bytes']/512)*32 for e in es)
                ngets = round(moe_wire / 128)
                # Aggregate offered request rate is 1 flit/cycle, as in lyc's
                # 512-request case. Distributed placement changes OD, not rate.
                gets = [(i, 0 if pattern=='hotspot' else i%8,
                         1 if pattern=='hotspot' else (i%8+1+(i//8)%7)%8)
                        for i in range(ngets)]
                waves.append(dict(stage=wave['stage'], moe_payload_bytes=moe_payload,
                                  moe_wire_bytes=moe_wire, gets=ngets,
                                  gets_wire_bytes=ngets*128,
                                  gets_payload_bytes=ngets*64,
                                  source_read_bytes=moe_payload,
                                  flows=[(e['src'],e['dst'],e['bytes']) for e in es],
                                  arrivals=gets))
            for interval in [1,3,6]:
                name2=f'{name}_{pattern}'+(f'_rate{interval}' if interval!=1 else '')
                lines=[str(len(waves))]
                for w in waves:
                    lines.append(f"{w['stage']} {len(w['flows'])} {len(w['arrivals'])} {tokens*4096}")
                    lines.extend(f'{s} {d} {b}' for s,d,b in w['flows'])
                    lines.extend(f'{t*interval} {s} {d}' for t,s,d in w['arrivals'])
                target=out/(name2+'.txt'); target.write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
                manifest.append(dict(name=name2,tokens=tokens,pattern=pattern,interval=interval,
                                 input_sha256=hashlib.sha256(raw).hexdigest(),
                                 case_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                                  waves=[{k:v for k,v in w.items() if k not in ['flows','arrivals']} for w in waves]))
    (ROOT/'CASES.json').write_text(json.dumps(manifest,indent=2))
    print('Prepared',len(manifest),'cases,',sum(len(c['waves']) for c in manifest),'waves')

if __name__=='__main__': main()
