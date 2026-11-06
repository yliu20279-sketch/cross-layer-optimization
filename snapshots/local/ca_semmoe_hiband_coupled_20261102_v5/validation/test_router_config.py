import json
from pathlib import Path
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.live_moe import selected_weights
from models.qwen15 import SPEC as Q15
from models.qwen3 import SPEC as Q3
from core.common import ContractError


class RouterConfigurationChecks(unittest.TestCase):
    def test_specs_match_actual_source_config(self):
        for name,spec in [('qwen15',Q15),('qwen3',Q3)]:
            source=json.loads((ROOT/('upstream/'+name+'_config.json')).read_text())
            self.assertEqual(spec['norm_topk_prob'],source['norm_topk_prob'])

    def test_topk_weights_preserve_model_specific_probability_mass(self):
        scores=np.asarray([.4,.3,.2,.1],dtype='<f4');top=np.asarray([0,1])
        np.testing.assert_array_equal(selected_weights(scores,top,Q15),scores[top])
        self.assertLess(float(selected_weights(scores,top,Q15).sum()),1)
        np.testing.assert_allclose(selected_weights(scores,top,Q3).sum(),1,rtol=0,atol=np.finfo(np.float32).eps)
        with self.assertRaises(ContractError):selected_weights(scores,top,{})
