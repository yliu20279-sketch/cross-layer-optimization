from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.gptq import decode, independent_decode
from core.common import ContractError


class GPTQChecks(unittest.TestCase):
    def test_nibble_order_nonmonotonic_group_and_zero_plus_one(self):
        # Pack by scalar arithmetic, independent of either vectorized decoder.
        q = np.array([[(3 * k + n) % 16 for n in range(8)] for k in range(16)], dtype=np.int32)
        weight = np.zeros((2, 8), dtype=np.uint32)
        for k in range(16):
            for n in range(8):
                weight[k // 8, n] |= np.uint32(int(q[k, n]) << (4 * (k % 8)))
        stored = [[15 if n == 0 else n for n in range(8)], list(reversed(range(8))) ]
        zeros = np.zeros((2, 1), dtype=np.uint32)
        for g in range(2):
            for n in range(8):
                zeros[g, 0] |= np.uint32(stored[g][n] << (4 * n))
        scales = np.array([[.125] * 8, [.25] * 8], dtype=np.float16)
        groups = np.array([k % 2 for k in range(16)], dtype=np.int32)
        expected = np.array([[(int(q[k, n]) - stored[groups[k]][n] - 1) * float(scales[groups[k], n])
                              for n in range(8)] for k in range(16)], dtype=np.float16)
        args = (weight.view(np.int32), zeros.view(np.int32), scales, groups)
        self.assertTrue(np.array_equal(decode(*args).view(np.uint16), expected.view(np.uint16)))
        self.assertTrue(np.array_equal(independent_decode(*args).view(np.uint16), expected.view(np.uint16)))

    def test_invalid_group_refused(self):
        with self.assertRaises(ContractError):
            decode(np.zeros((1, 8), np.int32), np.zeros((1, 1), np.int32),
                   np.ones((1, 8), np.float16), np.array([1] * 8, np.int32))


if __name__ == '__main__':
    unittest.main(verbosity=2)
