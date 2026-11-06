import re
def audit(lines):
 prefix=0;holes=set();latest=0;acks=0;drains=0
 for line in lines:
  m=re.fullmatch(r"(MAINT_WRITE_ACK|MAINT_DRAIN) (\d+) (\d+) (\d+) (\d+)\n",line)
  if not m:raise ValueError("malformed event")
  kind=m[1];a,b,c,d=map(int,m.groups()[1:])
  if kind=="MAINT_WRITE_ACK":
   if a<=prefix or a in holes or d<c:raise ValueError("invalid ack")
   holes.add(a);latest=max(latest,d);acks+=1
   while prefix+1 in holes:prefix+=1;holes.remove(prefix)
  else:
   if b or d<c or prefix<a or holes or latest>d:raise ValueError("invalid drain")
   drains+=1
 if holes:raise ValueError("missing ack")
 return dict(acks=acks,drains=drains,prefix=prefix)

if __name__=="__main__":
 import sys,json
 with open(sys.argv[1]) as source:print(json.dumps(audit(source)))
