"""Verify all frozen GetS callbacks before the long mixed run."""

import csv
import hashlib
import json
from pathlib import Path
import struct
import sys


def main(root, binary, fixture, out):
    sys.path.insert(0,str(root))
    from core.coupled_backend import LiveBackend, MAGIC

    source = json.loads(fixture.read_text())['transactions']
    b = LiveBackend(binary, hashlib.sha256(binary.read_bytes()).hexdigest(), out,
                    str(root/'ramulator32.yaml'), controls='off', timeout=45)
    try:
        (b.out/'GETS.stim').write_text(''.join(f"{r['arrival']} {r['address']}\n" for r in source))
        b.process.stdin.write(struct.pack('<8Q',15,len(source),32,0,0,0,0,0))
        b.process.stdin.flush()
        ack=struct.unpack('<8Q',b._read(64))
        if ack[1]:
            raise RuntimeError(b._read(ack[2]).decode())
        assert ack[0]==MAGIC and ack[7]==32
        b.clock=ack[7]
        summary=b.close()
        with (b.out/'GETS.csv').open() as stream:
            rows=list(csv.DictReader(stream))
        assert len(rows)==len(source)
        assert summary['packet_callbacks']==summary['callbacks']==2*len(source)
        assert all(int(r['arrival'])==expected['arrival'] and int(r['reply_done'])>=int(r['read_done'])
                   for r,expected in zip(rows,source))
        print('PASS_GETS_ACTUATOR',len(rows),max(int(r['reply_done']) for r in rows),flush=True)
    finally:
        if not b.closed:
            b.abort()


if __name__=='__main__':
    main(*(Path(p).resolve() for p in sys.argv[1:]))
