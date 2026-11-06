from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.artifacts import TargetArtifactStore
from core.common import ContractError


class ArtifactChecks(unittest.TestCase):
    def test_bf16_must_be_explicit_and_is_never_reinterpreted_as_fp16(self):
        fixtures=Path(__file__).resolve().parents[1]/'evidence'/'temporary_fixture_root'
        fixtures.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(fixtures)) as directory:
            root=Path(directory)
            self.assertEqual(root.resolve().parent,fixtures.resolve())
            path=root/'bf16.bin';path.write_bytes(b'\x80\x3f\x00\x40')
            manifest=[{'name':'w','dtype':'BF16','shape':[2],'bytes':4,
                       'parts':[{'file':str(path),'offset':0,'dtype':'BF16','shape':[2],'bytes':4}]}]
            with self.assertRaises(ContractError):TargetArtifactStore(manifest)
            reader=TargetArtifactStore(manifest,expected_dtype='BF16')
            self.assertEqual(reader.read('w',0,4),b'\x80\x3f\x00\x40')
            self.assertTrue(all(x['dtype']=='BF16' for x in reader.served_segments))

    def test_fragmented_tp_objects_all_unaligned_subranges(self):
        matrix = np.arange(15, dtype=np.float16).reshape(3, 5)
        full = matrix.tobytes()
        fixtures = Path(__file__).resolve().parents[1] / 'evidence' / 'temporary_fixture_root'
        fixtures.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(fixtures)) as directory:
            root = Path(directory)
            self.assertEqual(root.resolve().parent, fixtures.resolve())
            for axis, pieces in ((0, [matrix[:1], matrix[1:]]), (1, [matrix[:, :2], matrix[:, 2:]])):
                parts = []
                for i, piece in enumerate(pieces):
                    path = root / ('%d_%d.bin' % (axis, i))
                    # Poison bytes model packed data in the same archive.
                    path.write_bytes(b'PACKED-DO-NOT-READ' + piece.tobytes() + b'POISON')
                    parts.append({'file': str(path), 'offset': len(b'PACKED-DO-NOT-READ'), 'bytes': piece.nbytes,
                                  'dtype': 'F16', 'shape': list(piece.shape), 'concat_axis': axis})
                store = TargetArtifactStore([{'name': 'w', 'dtype': 'F16', 'shape': [3, 5],
                                              'bytes': len(full), 'parts': parts}])
                for offset in range(len(full)):
                    for length in range(1, len(full) - offset + 1):
                        self.assertEqual(store.read('w', offset, length), full[offset:offset + length])
                self.assertTrue(all(x['dtype'] == 'F16' for x in store.served_segments))
                with self.assertRaises(ContractError):
                    store.read('w', 29, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
