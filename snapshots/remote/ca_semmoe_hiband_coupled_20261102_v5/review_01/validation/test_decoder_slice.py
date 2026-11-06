from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.coupled_decoder import DecoderSlice
from core.common import ContractError


class SliceControlChecks(unittest.TestCase):
    def test_stage_boundary_uses_completed_previous_layer_payload(self):
        sent=[];calls=[]
        def send(src,dst,token,stage,payload):
            sent.append((src,dst,stage,payload));return payload+b'PP'
        n=SimpleNamespace(backend=SimpleNamespace(clock=0))
        def forward(hidden,positions,tokens,layer):
            calls.append((layer,hidden));n.backend.clock+=1;return hidden+str(layer).encode()
        layer=SimpleNamespace(spec={'layers':24,'layers_per_stage':6,'tp':4},
            n=n,transport=SimpleNamespace(send=send),forward=forward)
        result=DecoderSlice(layer).forward(b'input',[0],[17],5,7)
        self.assertEqual(sent,[(0,4,'PP_boundary_layer_6',b'input5')])
        self.assertEqual(calls,[(5,b'input'),(6,b'input5PP')])
        self.assertEqual(result,b'input5PP6')

    def test_invalid_ranges_fail_before_any_layer_or_transfer(self):
        layer=SimpleNamespace(spec={'layers':24,'layers_per_stage':6,'tp':4})
        for first,last in [(0,0),(-1,1),(23,25),(7,6)]:
            with self.subTest(first=first,last=last),self.assertRaises(ContractError):
                DecoderSlice(layer).forward(b'x',[0],[17],first,last)
