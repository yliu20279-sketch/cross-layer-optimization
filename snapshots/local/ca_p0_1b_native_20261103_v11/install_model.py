from pathlib import Path
p=Path('core/coupled_layer.py')
s=p.read_text()
i=s.index('    def _append_kv')
s=s[:i]+"""    def _kv_get(self, handle):
        b=self.n.backend
        size=self.kv_sizes[handle]
        reply=b.rpc(3,handle,0,size,self.request_owner)
        require(reply[3]==size,'KV read refused')
        return b._read(size)

    def _kv_stage(self, rank, payload):
        b=self.n.backend
        handle=b.rpc(12,rank,len(payload),self.request_owner)[2]
        self.kv_sizes[handle]=len(payload)
        require(b.rpc(2,handle,0,len(payload),self.request_owner,payload=payload)[3]==len(payload),'KV write refused')
        return handle

    def _kv_free(self, handle):
        require(self.n.backend.rpc(4,handle,self.request_owner)[3]==1,'KV release refused')
        del self.kv_sizes[handle]

"""+s[i:]
s=s.replace('self.cache={};','self.kv_sizes={};self.cache={};')
s=s.replace("b.get(old['k']),b.get(old['v'])","self._kv_get(old['k']),self._kv_get(old['v'])")
s=s.replace('b.stage(rank,combined[0]);vh=b.stage(rank,combined[1])','self._kv_stage(rank,combined[0]);vh=self._kv_stage(rank,combined[1])')
s=s.replace("b.free(old['k']);b.free(old['v'])","self._kv_free(old['k']);self._kv_free(old['v'])")
s=s.replace('return b.get(kh),b.get(vh),past','return self._kv_get(kh),self._kv_get(vh),past')
s=s.replace("self.n.backend.free(entry['k']);self.n.backend.free(entry['v'])","self._kv_free(entry['k']);self._kv_free(entry['v'])")
p.write_text(s)
p=Path('tools/run_interleaved.py')
s=p.read_text()
s=s.replace('        trace = []','''        for owner,layer in enumerate(sessions.values(),1):
            layer.request_owner=owner
        trace = []''')
s=s.replace('raw = backend.get(handle)','raw = layer._kv_get(handle)')
i=s.index("            if phase=='prefill':")
s=s[:i]+"""            a,b=sessions.values()
            for rank in range(spec['tp']):
                for member in ('k','v'):
                    ah,bh=a.cache[(0,rank)][member],b.cache[(0,rank)][member]
                    expected=a._kv_get(ah)[:256]+b._kv_get(bh)[:256]
                    require(len(expected)==512,'KV batch diagnostic geometry')
                    require(backend.rpc(13,ah,1,bh,2)[3]==512,'KV batch failed')
                    require(backend._read(512)==expected,'paired live KV read mismatch')
"""+s[i:]
p.write_text(s)
