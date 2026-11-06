"""Contiguous decoder slice with actual stage-boundary payload delivery.

A slice entry is explicit; starting at a middle layer is not called full-model
execution. Uses the same backend as attention/MoE, not a timing-only PP graph.
"""
from .common import require


class DecoderSlice:
    def __init__(self,layer):self.layer=layer;self.events=[]

    def forward(self,hidden,positions,token_ids,start_layer,stop_layer):
        spec=self.layer.spec
        require(isinstance(start_layer,int) and isinstance(stop_layer,int) and
                0<=start_layer<stop_layer<=spec['layers'],'invalid explicit decoder slice')
        current=hidden;previous_stage=None
        for index in range(start_layer,stop_layer):
            stage=index//spec['layers_per_stage']
            if previous_stage is not None and stage!=previous_stage:
                require(stage==previous_stage+1,'noncontiguous PP stage traversal')
                current=self.layer.transport.send(previous_stage*spec['tp'],stage*spec['tp'],
                    tuple(positions),'PP_boundary_layer_%d'%index,current)
            current=self.layer.forward(current,positions,token_ids,index)
            self.events.append({'layer':index,'stage':stage,'complete':self.layer.n.backend.clock})
            previous_stage=stage
        return current
