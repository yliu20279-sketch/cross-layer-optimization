from pathlib import Path
import hashlib
import json
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.common import ContractError
from core.native_payload import NativePayload
from core.payload_collectives import HostPayloadTransport,srs_payload,sag_payload
LIB=ROOT/'runtime/build_02/libpayload.so'
LIB_SHA=None
candidate=json.loads((ROOT/'evidence/REMOTE_BUILD_LIVE_02.json').read_text())
if Path(candidate['payload_library']).is_file():
    LIB=Path(candidate['payload_library']);LIB_SHA=candidate['payload_sha256']


@unittest.skipUnless(LIB.is_file(),'native Linux library verified on 113, not available locally')
class NativeChecks(unittest.TestCase):
    def setUp(self):
        self.native=NativePayload(LIB,LIB_SHA or hashlib.sha256(LIB.read_bytes()).hexdigest())

    def test_library_identity_and_explicit_dtype_refusal(self):
        with self.assertRaises(ContractError):NativePayload(LIB,'0'*64)
        with self.assertRaises(ContractError):self.native.decode(b'\x00\x00','INT4')
        with self.assertRaises(ContractError):self.native.decode(b'\x00','F16')
        bits=b'\x80\x3f'
        self.assertNotEqual(self.native.decode(bits,'F16')[0],self.native.decode(bits,'BF16')[0])

    def test_qkv_bias_is_applied_before_final_storage_round(self):
        a=np.asarray([1.0009765625],dtype='<f2').tobytes()
        bias=np.asarray([-1.001953125],dtype='<f2').tobytes()
        out=self.native.linear(a,a,1,1,1,'F16','input_major',bias)
        self.assertEqual(np.frombuffer(out,dtype='<f2')[0],np.float16(2**-20))
        self.assertNotEqual(out,b'\x00\x00')

    def test_k_tail_and_weight_layout_independent_integer_reference(self):
        a=np.arange(130,dtype='<f2').reshape(2,65)%3
        weight=(np.arange(195,dtype='<f2').reshape(65,3)%5)-2
        for dtype in ('F16','BF16'):
            x=self.native.encode(a,dtype);kn=self.native.encode(weight,dtype)
            nk=self.native.encode(weight.T.copy(),dtype)
            y=self.native.linear(x,kn,2,65,3,dtype,'input_major')
            z=self.native.linear(x,nk,2,65,3,dtype,'output_major')
            self.assertEqual(y,z)
            ref=a.astype(np.int64)@weight.astype(np.int64)
            np.testing.assert_array_equal(self.native.decode(y,dtype).reshape(2,3),ref)

    def test_collective_delivers_every_peer_and_refuses_missing_or_duplicate_tokens(self):
        n=self.native;t=HostPayloadTransport(n)
        parts=[[n.encode([rank+token,rank-token],'F16') for token in range(3)] for rank in range(4)]
        shards=srs_payload(parts,[3,0,3],'F16',n,t)
        replicas=sag_payload(shards,3,n,t)
        self.assertEqual(len(t.events),18)
        for token in range(3):
            np.testing.assert_array_equal(n.decode(replicas[0][token],'F16'),[6+4*token,6-4*token])
        with self.assertRaises(ContractError):sag_payload([[(0,b'aa')],[(0,b'aa')]],1,n,t)
        with self.assertRaises(ContractError):sag_payload([[],[]],1,n,t)
        with self.assertRaises(ContractError):srs_payload(parts,[4,0,0],'F16',n,t)


if __name__=='__main__':unittest.main()
