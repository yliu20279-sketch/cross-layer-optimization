"""Interface failure/ordering unit tests; stubs are not performance evidence."""
import unittest
from transport import CANoCTransport

class Backend:
    def __init__(self):
        self.live={1:(0,64,1),2:(5,64,0)};self.clock=10;self.calls=[]
        self.data={1:b'a'*64,2:b'\0'*64};self.fail_wait=False
    def get(self,h,size=None):
        self.calls.append(('get',h,self.clock));self.clock+=1
        return self.data[h][:(size or 64)]
    def put(self,h,value):self.calls.append(('put',h,self.clock));self.data[h]=value;self.clock+=1
    def rpc(self,op,target):
        self.calls.append(('rpc',op,target))
        if self.fail_wait:raise RuntimeError('failed wait')
        assert op==16 and target>=self.clock;self.clock=target

class Network:
    def __init__(self):self.fail=False;self.calls=[]
    def transfer(self,s,d,n,t,mode):
        self.calls.append((s,d,n,t,mode))
        if self.fail:raise RuntimeError('failed network')
        return dict(issue=t,receive_complete=20,drained=23,mode=mode)

class TransportTests(unittest.TestCase):
    def setUp(self):self.b=Backend();self.n=Network();self.t=CANoCTransport(self.b,self.n)
    def test_actual_completion_precedes_write(self):
        self.assertEqual(self.t.send_handles(1,2,64),b'a'*64)
        self.assertEqual([c for c in self.b.calls if c[0]=='put'],[('put',2,23)])
        self.assertEqual([c[1] for c in self.b.calls if c[0]=='rpc'],[16])
        self.assertEqual(len(self.n.calls),1)
    def test_network_failure_never_publishes(self):
        self.n.fail=True
        with self.assertRaises(RuntimeError):self.t.send_handles(1,2,64)
        self.assertFalse(any(c[0]=='put' for c in self.b.calls))
    def test_wait_failure_never_publishes(self):
        self.b.fail_wait=True
        with self.assertRaises(RuntimeError):self.t.send_handles(1,2,64)
        self.assertFalse(any(c[0]=='put' for c in self.b.calls))
    def test_reject_same_rank(self):
        self.b.live[2]=(0,64,0)
        with self.assertRaises(AssertionError):self.t.send_handles(1,2,64)
        self.assertFalse(self.n.calls)
    def test_reject_extent_overflow(self):
        with self.assertRaises(AssertionError):self.t.send_handles(1,2,96)
        self.assertFalse(self.n.calls)
    def test_reject_partial_flit_not_silently_pad(self):
        with self.assertRaises(AssertionError):self.t.send_handles(1,2,63)
        self.assertFalse(self.n.calls)
    def test_reject_stale_handle(self):
        with self.assertRaises(AssertionError):self.t.send_handles(3,2,64)
        self.assertFalse(self.n.calls)
    def test_reject_unbounded_message(self):
        self.b.live={1:(0,65536,1),2:(5,65536,0)}
        with self.assertRaises(AssertionError):self.t.send_handles(1,2,65536)
        self.assertFalse(self.n.calls)

if __name__=='__main__':unittest.main(verbosity=2)
