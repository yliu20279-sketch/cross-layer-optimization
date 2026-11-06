"""Separate source implementation admission from later P0-2 validation.

An old performance gate remains conservative. This module prevents treating
P0-2 empirical verification as something a P0-1 document has already passed.
"""
from pathlib import Path
from .common import file_hash


def source_gate(contract, coverage):
    missing = []
    prefix, count = ('Q3', 6) if 'Qwen3' in contract.get('model_id', '') else ('Q15', 7)
    required = {('%s-%02d' % (prefix, i)) for i in range(1, count + 1)}
    required.update('C-%02d' % i for i in range(1, 8))
    supplied = {item['id'] for item in coverage}
    missing.extend('coverage:' + name for name in sorted(required - supplied))
    if len(supplied) != len(coverage):
        missing.append('coverage:duplicate_ID')
    for name in ('model_id', 'checkpoint_content_sha256', 'tokenizer_sha256', 'precision_sha256'):
        if not contract.get(name):
            missing.append('identity:' + name)
    # A content-addressed frozen artifact can identify a local snapshot even if
    # its upstream commit is unknown. Never manufacture a publisher revision.
    if not contract.get('revision') and not contract.get('content_snapshot_id'):
        missing.append('identity:immutable_snapshot')
    for item in coverage:
        path = (Path(__file__).resolve().parents[1]/item['relative_path']
                if item.get('relative_path') else Path(item.get('path', '')))
        if item.get('implementation') != 'implemented' or not path.is_file() or not item.get('sha256'):
            missing.append('source:' + item['id'])
        elif file_hash(path) != item['sha256']:
            missing.append('source_changed:' + item['id'])
    if not contract.get('runtime', {}).get('source_build_identity_sha256'):
        missing.append('runtime:source_build_identity')
    return {'p0_1_source_complete': not missing, 'missing': missing,
            'p0_2_verified': False, 'performance_ready': False}
