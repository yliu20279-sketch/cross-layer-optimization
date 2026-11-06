from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from models.qwen15.projections import projection_plan


class ProjectionChecks(unittest.TestCase):
    def test_qkv_bias_slices_cover_exactly_once(self):
        prefix='model.layers.0.self_attn.q_proj'
        manifest=[{'name':prefix+'.weight','dtype':'F16','layout':'input_major','shape':[2048,2048]},
                  {'name':prefix+'.bias','dtype':'F16','shape':[2048]}]
        plans=[projection_plan(manifest,prefix,r) for r in range(4)]
        self.assertEqual([p['bias_slice'] for p in plans],[[0,512],[512,1024],[1024,1536],[1536,2048]])
        self.assertTrue(all(p['bias_stage']=='before_final_fp16_cast' for p in plans))

    def test_down_tp_splits_k_and_requires_fp32_sum(self):
        prefix='model.layers.12.mlp.shared_expert.down_proj'
        manifest=[{'name':prefix+'.weight','dtype':'F16','layout':'input_major','shape':[5632,2048]}]
        plans=[projection_plan(manifest,prefix,r) for r in range(4)]
        self.assertEqual([p['matrix_bounds_KN'][:2] for p in plans],[[0,1408],[1408,2816],[2816,4224],[4224,5632]])
        self.assertTrue(all(p['output_dtype']=='F32' and p['tp_reduce_required'] for p in plans))
        self.assertEqual([p['partition'] for p in plans],[8,9,10,11])


if __name__=='__main__':unittest.main(verbosity=2)
