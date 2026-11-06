import unittest
from mean import mean
class MeanTests(unittest.TestCase):
    def test_empty(self): self.assertIsNone(mean([]))
    def test_values(self): self.assertEqual(mean([2,4,6]),4)
if __name__ == "__main__": unittest.main()
