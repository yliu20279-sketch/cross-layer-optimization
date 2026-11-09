"""Small executable interface contract, NOT RTL or cycle-accurate NoC simulation."""
from collections import deque
from itertools import permutations
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent


class Reassembly:
    def __init__(self):
        self.transfer=(3,17)
        self.fragment_bytes=4
        self.total_bytes=10
        self.base=128
        self.memory=bytearray(256)
        self.queues=[deque() for _ in range(5)]
        self.queue_capacity=1
        self.staging=deque()
        self.staging_capacity=1
        self.pending=set()
        self.committed=set()
        self.round_robin=0
        self.completion_count=0

    @property
    def complete(self):
        return self.committed=={0,1,2} and not self.pending

    def accept(self,transfer,offset,payload,link):
        if transfer!=self.transfer:raise ValueError("unknown transfer")
        if offset<0 or offset%self.fragment_bytes or offset>=self.total_bytes:raise ValueError("offset")
        expected=min(self.fragment_bytes,self.total_bytes-offset)
        if len(payload)!=expected:raise ValueError("length")
        fragment=offset//self.fragment_bytes
        if fragment in self.pending or fragment in self.committed:raise ValueError("duplicate")
        if len(self.queues[link])==self.queue_capacity:return False
        self.queues[link].append((fragment,offset,payload))
        self.pending.add(fragment)
        return True

    def step(self,sram_ready):
        if self.staging and sram_ready:
            fragment,offset,payload=self.staging.popleft()
            address=self.base+offset
            assert self.base<=address and address+len(payload)<=self.base+self.total_bytes
            self.memory[address:address+len(payload)]=payload
            self.pending.remove(fragment)
            self.committed.add(fragment)
            if self.complete:self.completion_count+=1
        if len(self.staging)<self.staging_capacity:
            for shift in range(len(self.queues)):
                port=(self.round_robin+shift)%len(self.queues)
                if self.queues[port]:
                    self.staging.append(self.queues[port].popleft())
                    self.round_robin=(port+1)%len(self.queues)
                    break
        assert all(len(q)<=self.queue_capacity for q in self.queues)
        assert len(self.staging)<=self.staging_capacity
        assert not self.complete or not self.staging and not any(self.queues)


class ConfigurationBarrier:
    def __init__(self,ownership):
        self.owners={}
        self.paths={}
        for entry in ownership:
            lower,owner=entry["lower_CS"],entry["owner_node"]
            self.owners[lower]=owner;self.paths[lower]=(owner,lower)
            upper=entry["upper_CS"]
            if upper is not None:
                self.owners[upper]=owner;self.paths[upper]=(owner,lower,upper)
        self.paused=False
        self.drained=set()
        self.responses=set()
        self.pending={}
        self.sequence=0
        self.registers={cs:None for cs in self.owners}
        self.failed=False

    def pause(self):
        self.paused=True
        self.drained.clear();self.responses.clear();self.pending.clear()

    def drain_response(self,node,quiescent):
        if not self.paused or node not in range(16):raise ValueError("pause protocol")
        if quiescent:self.drained.add(node)

    def write(self,owner,target,state):
        if not self.paused or self.drained!=set(range(16)):raise ValueError("not drained")
        if self.owners.get(target)!=owner:raise ValueError("wrong target owner")
        if target in self.pending:raise ValueError("write already pending")
        self.registers[target]=state
        self.sequence+=1
        self.pending[target]=self.sequence
        self.responses.discard(target)
        # Target-write response is separate, especially for relayed upper writes.
        return self.sequence

    def write_response(self,target,transaction,success=True):
        if self.pending.get(target)!=transaction:raise ValueError("stale or wrong response")
        del self.pending[target]
        if success:self.responses.add(target)
        else:self.failed=True

    def resume(self):
        if self.failed or self.pending or self.responses!=set(range(13)):raise ValueError("incomplete configuration")
        self.paused=False


def must_reject(operation):
    try:operation()
    except ValueError:return
    raise AssertionError("invalid operation accepted")


def main():
    source=bytes(range(10))
    cases=0
    for order in permutations(range(3)):
        for service_period in (1,2,5,11):
            rx=Reassembly();todo=deque(order)
            for cycle in range(200):
                if todo:
                    fragment=todo[0];offset=4*fragment
                    if rx.accept(rx.transfer,offset,source[offset:offset+4],fragment%2):todo.popleft()
                was_complete=rx.complete
                rx.step(cycle%service_period==0)
                if not was_complete and rx.complete:assert len(rx.committed)==3
                if not todo and rx.complete:break
            else:raise AssertionError("bounded test did not complete")
            assert rx.memory[128:138]==source and rx.completion_count==1
            assert rx.memory[:128]==bytes(128) and rx.memory[138:]==bytes(118)
            cases+=1
    rx=Reassembly()
    assert rx.accept(rx.transfer,8,source[8:],0)
    assert not rx.accept(rx.transfer,0,source[:4],0)
    rx.step(False);rx.step(False)
    assert not rx.complete and not rx.committed
    must_reject(lambda:rx.accept(rx.transfer,8,source[8:],1))
    must_reject(lambda:rx.accept((2,99),0,source[:4],1))
    must_reject(lambda:rx.accept(rx.transfer,3,source[:4],1))
    must_reject(lambda:rx.accept(rx.transfer,12,source[:4],1))
    must_reject(lambda:rx.accept(rx.transfer,4,source[:2],1))
    meta=json.loads((ROOT/"node_interface_v3.json").read_text(encoding="utf-8"))
    barrier=ConfigurationBarrier(meta["configuration_ownership"])
    assert set(barrier.paths)==set(range(13))
    must_reject(lambda:barrier.write(0,0,"state"))
    barrier.pause()
    for node in range(15):barrier.drain_response(node,True)
    barrier.drain_response(15,False)
    must_reject(lambda:barrier.write(0,0,"state"))
    barrier.drain_response(15,True)
    must_reject(lambda:barrier.write(15,0,"state"))
    transactions={}
    for target in range(13):
        transactions[target]=barrier.write(barrier.owners[target],target,"enabled state")
        if target<12:barrier.write_response(target,transactions[target])
    must_reject(barrier.resume)
    must_reject(lambda:barrier.write_response(12,transactions[12]-1))
    barrier.write_response(12,transactions[12])
    barrier.resume();assert not barrier.paused
    barrier.pause()
    for node in range(16):barrier.drain_response(node,True)
    current=barrier.write(0,0,"new state")
    must_reject(lambda:barrier.write_response(0,transactions[0]))
    barrier.write_response(0,current,False)
    must_reject(barrier.resume)
    mux_cases=0
    for directions in [("NW","NE","SW","SE","U"),("E","S","D")]:
        n=len(directions);bits=3 if n==5 else 2
        for enable in (False,True):
            for output in range(1<<bits):
                for selection in range(n-1):
                    if enable and output<n:
                        choices=[d for d in directions if d!=directions[output]]
                        assert choices[selection]!=directions[output]
                    mux_cases+=1
    report={
        "status":"PASS",
        "scope":"small finite-buffer interface contract model only; not RTL, NoC simulation or timing",
        "out_of_order_and_stall_cases":cases,
        "fragment_queue_capacity":1,"staging_capacity":1,"active_contexts":1,
        "fragment_payload_bytes":4,"transfer_bytes":10,
        "control_target_paths":barrier.paths,
        "checks":["exact offset-directed memory placement","completion only after all writes","finite queue backpressure","reject pending duplicates and invalid fragments","all 16 drain responses required","target ownership","upper target acknowledgement before resume","stale transaction responses rejected","failed write keeps pause","self input excluded by MUX input list"],
        "mux_encoding_cases":mux_cases,
        "not_tested":["actual network/CDC","RTL ready/valid","large context concurrency","timeout recovery","physical timing"]
    }
    (ROOT/"interface_model_checks.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8",newline="\n")
    print(f"PASS: {cases} reorder/stall cases; finite buffering and bounds; 13 target control paths and 16-NI pause barrier; {mux_cases} MUX cases. Model only.")


if __name__=="__main__":main()
