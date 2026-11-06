"""Byte-exact target FP16 operand service, including reused TP4 fragments.

This is a real byte reader for native operand adapters, not a timing model.
Only declared F16 spans are exposed. Packed GPTQ/metadata are never operands.
"""
from pathlib import Path
import json
from .common import require
from .memory import tensor_bytes


class TargetArtifactStore:
    def __init__(self, manifest):
        self.objects = {row['name']: row for row in manifest}
        require(len(self.objects) == len(manifest), 'duplicate target object')
        self.served_bytes = 0
        self.served_segments = []
        for obj in manifest:
            require(obj['dtype'] == 'F16' and not obj.get('runtime_quantized', False), 'packed/non-F16 operand')
            require(tensor_bytes(obj['shape'], 'F16') == obj['bytes'], 'logical byte extent differs')
            parts = obj['parts']
            require(parts and sum(p['bytes'] for p in parts) == obj['bytes'], 'fragment payload mismatch')
            for part in parts:
                require(part['dtype'] == 'F16' and tensor_bytes(part['shape'], 'F16') == part['bytes'],
                        'fragment dtype/shape differs')
                path = Path(part['file'])
                require(path.is_file() and part['offset'] >= 0 and
                        part['offset'] + part['bytes'] <= path.stat().st_size, 'fragment outside file')
            if len(parts) > 1:
                axis = parts[0].get('concat_axis')
                require(axis in (0, 1) and len(obj['shape']) == 2 and
                        all(p.get('concat_axis') == axis for p in parts), 'unsupported fragment layout')
                other = 1 - axis
                require(all(len(p['shape']) == 2 and p['shape'][other] == obj['shape'][other] for p in parts)
                        and sum(p['shape'][axis] for p in parts) == obj['shape'][axis], 'concat shape mismatch')
            else:
                require(parts[0]['shape'] == obj['shape'], 'single fragment shape mismatch')

    def _span(self, obj, offset, remaining):
        parts = obj['parts']
        if len(parts) == 1:
            return parts[0], offset, remaining
        axis = parts[0]['concat_axis']
        columns = obj['shape'][1]
        row, byte_column = divmod(offset, columns * 2)
        if axis == 0:
            row_base = 0
            for part in parts:
                if row < row_base + part['shape'][0]:
                    local = (row - row_base) * columns * 2 + byte_column
                    return part, local, min(remaining, part['bytes'] - local)
                row_base += part['shape'][0]
        else:
            column_base = 0
            for part in parts:
                width = part['shape'][1] * 2
                if byte_column < column_base + width:
                    local = row * width + byte_column - column_base
                    return part, local, min(remaining, column_base + width - byte_column)
                column_base += width
        require(False, 'logical offset outside fragments')

    def read(self, name, offset, length):
        require(name in self.objects, 'unknown target object')
        obj = self.objects[name]
        require(isinstance(offset, int) and isinstance(length, int) and offset >= 0 and length > 0
                and offset + length <= obj['bytes'], 'operand outside logical tensor')
        chunks = []
        while length:
            part, local, n = self._span(obj, offset, length)
            require(n > 0, 'empty fragment read')
            with Path(part['file']).open('rb') as handle:
                handle.seek(part['offset'] + local)
                chunk = handle.read(n)
            require(len(chunk) == n, 'short target read')
            chunks.append(chunk)
            self.served_segments.append({'object': name, 'file': part['file'], 'dtype': 'F16',
                                         'file_offset': part['offset'] + local, 'bytes': n})
            self.served_bytes += n
            offset += n
            length -= n
        return b''.join(chunks)
