"""Executable CPU payload collectives; no simulated NoC timing claim.

The transport is explicit. It can be replaced by a target service only after
that service supplies matching completion/payload receipts. Host copies are
never labelled target NoC transfers.
"""
import hashlib
from .common import require


class HostPayloadTransport:
    target_noc = False
    def __init__(self, native):
        self.native=native
        self.events=[]

    def send(self, src, dst, token, stage, payload):
        require(isinstance(src,int) and isinstance(dst,int) and src>=0 and dst>=0 and src!=dst,
                'invalid payload peer')
        require(bool(payload) and stage and token is not None,'missing transfer identity')
        delivered=self.native.copy(payload)
        require(delivered==payload,'payload changed in transport')
        self.events.append({'src':src,'dst':dst,'token':token,'stage':stage,'bytes':len(payload),
                            'payload_sha256':hashlib.sha256(payload).hexdigest(),
                            'completed':True,'backend':'native CPU copy','target_noc':False})
        return delivered


def srs_payload(partials, destinations, dtype, native, transport):
    ranks=len(partials)
    require(ranks>0 and destinations and all(len(row)==len(destinations) for row in partials),'bad SRS extents')
    shards=[[] for _ in range(ranks)]
    for token,dst in enumerate(destinations):
        require(isinstance(dst,int) and 0<=dst<ranks,'bad SRS destination')
        parts=[]
        for src in range(ranks):
            payload=partials[src][token]
            parts.append(payload if src==dst else transport.send(src,dst,token,'SRS',payload))
        shards[dst].append((token,native.sum(parts,dtype)))
    return shards


def sag_payload(shards, token_count, native, transport):
    require(token_count>0 and shards,'empty SAG')
    locations={}
    for src,rows in enumerate(shards):
        for token,payload in rows:
            require(isinstance(token,int) and 0<=token<token_count and token not in locations,'invalid/duplicate SAG token')
            require(payload,'empty SAG payload')
            locations[token]=(src,payload)
    require(set(locations)==set(range(token_count)),'missing SAG token')
    replicas=[]
    for dst in range(len(shards)):
        rows=[]
        for token in range(token_count):
            src,payload=locations[token]
            rows.append(payload if src==dst else transport.send(src,dst,token,'SAG',payload))
        replicas.append(rows)
    require(all(row==replicas[0] for row in replicas),'SAG replicas differ')
    return replicas
