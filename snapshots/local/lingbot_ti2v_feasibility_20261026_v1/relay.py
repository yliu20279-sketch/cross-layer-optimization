from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import urllib.request,urllib.parse
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  url=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get('url',[''])[0]
  if urllib.parse.urlparse(url).hostname not in ['huggingface.co','raw.githubusercontent.com']:
   self.send_error(403);return
  try:
   headers={'User-Agent':'LingBot-fixed-asset-download/1.0'}
   if self.headers.get('Range'):headers['Range']=self.headers['Range']
   with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=120) as r:
    self.send_response(r.status)
    for k in ['Content-Length','Content-Range','Accept-Ranges','Content-Type']:
     if r.headers.get(k):self.send_header(k,r.headers[k])
    self.end_headers()
    while True:
     b=r.read(1024*1024)
     if not b:break
     self.wfile.write(b)
  except Exception as e:
   try:self.send_error(502,str(e)[:160])
   except:pass
 def log_message(self,*a):pass
ThreadingHTTPServer(('127.0.0.1',18765),Handler).serve_forever()
