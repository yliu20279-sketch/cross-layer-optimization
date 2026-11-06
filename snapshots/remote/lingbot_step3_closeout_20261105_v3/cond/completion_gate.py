"""Validate completion receipts before a consumer is released."""
from fractions import Fraction
from math import ceil

KINDS = frozenset(('cpu_return', 'dma_poll_complete',
                   'dirty_writeback_callback', 'noc_receive_tail'))


class CompletionGate:
    def __init__(self, identity, expected):
        if set(expected) != KINDS:
            raise ValueError('incomplete transaction binding')
        self.identity = dict(identity)
        self.expected = dict(expected)
        self.completed = {}

    def accept(self, kind, identity, transaction, tick, tick_ns):
        if kind not in self.expected or kind in self.completed:
            raise ValueError('unknown or duplicate completion')
        if identity != self.identity or transaction != self.expected[kind]:
            raise ValueError('completion identity mismatch')
        period = Fraction(tick_ns)
        if type(tick) is not int or tick < 0 or period <= 0:
            raise ValueError('invalid clock observation')
        self.completed[kind] = ceil(tick * period)

    def release(self, consumer_start_ns):
        if set(self.completed) != KINDS:
            raise ValueError('missing completion')
        ready_ns = max(self.completed.values())
        if type(consumer_start_ns) is not int or consumer_start_ns < ready_ns:
            raise ValueError('premature consumer start')
        return ready_ns
