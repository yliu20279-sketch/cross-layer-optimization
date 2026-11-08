from pathlib import Path
from collections import Counter
import csv
import json

def audit_source(log,delay,capacity=1025):
    pending=Counter();peak=Counter();released=set();enqueued=set();tail={};times=Counter();count=Counter()
    for r in csv.DictReader(Path(log).open()):
        n=int(r['node']);key=int(r['packet']),int(r['ordinal']);t=float(r['time']);count[r['event']]+=1
        if r['event']=='ENQUEUE':
            assert key not in enqueued;enqueued.add(key);pending[n]+=1
            assert pending[n]==int(r['occupancy'])
        elif r['event']=='RELEASE':
            assert key in enqueued and key not in released;released.add(key);pending[n]-=1
            assert pending[n]==int(r['occupancy']) and float(r['send_finish'])==t
            times[n,t]+=1;assert times[n,t]==1,'source port consumed two flits on one edge'
            if int(r['tail']):
                transaction=(n,int(float(r['start'])))
                assert transaction not in tail;tail[transaction]=t
        else:raise AssertionError(r['event'])
        assert 0<=pending[n]<=capacity
        peak[n]=max(peak[n],pending[n])
    assert enqueued==released and not any(pending.values())
    feedback=[list(map(int,l.split())) for l in Path(delay).read_text().splitlines() if l.strip()]
    assert len(tail)==len(feedback) and len(feedback)>0
    # Payload lengths differ between real expert messages. Exact flit totals
    # are checked against the native bench independently in network.py.
    for ts,s,d,desc,num,send,recv in feedback:
        assert num==2 and ts+send==tail[s,ts],'WRITE feedback differs from actual source storage release'
        assert recv>=send,'destination precedes last source flit release'
    return {'passed':True,'messages':len(feedback),'source_flits':len(enqueued),'source_capacity_flits':capacity,
        'maximum_queued_flits':max(peak.values()),'maximum_queued_flits_by_node':dict(peak),
        'tail_feedback_matches_actual_source_release':True,'source_read_flits_per_cycle_at_most':1}

if __name__=='__main__':
    import sys
    print(json.dumps(audit_source(sys.argv[1],sys.argv[2]),indent=2))
