"""Read-only probes against the real demo server. Run from repo root with server on 18765."""
import concurrent.futures, hashlib, json, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path
BASE='http://127.0.0.1:18765'
def get(params=None,path='/pulse'):
 url=BASE+path+('?' + urllib.parse.urlencode(params) if params is not None else '')
 start=time.perf_counter()
 try:
  with urllib.request.urlopen(url,timeout=60) as r: code=r.status;body=r.read();ct=r.headers.get('Content-Type')
 except urllib.error.HTTPError as e:code=e.code;body=e.read();ct=e.headers.get('Content-Type')
 try:data=json.loads(body)
 except ValueError:data=None
 return {'params':params,'path':path,'http':code,'seconds':round(time.perf_counter()-start,3),'bytes':len(body),'content_type':ct,'data':data,'text':None if data is not None else body.decode()}
cases=[{}, {'topic':'zec'},{'topic':'ZEC'},{'topic':'zcash'},{'topic':'зек'},{'topic':' ZEC '},{'topic':'$ZEC'}, {'topic':'eth'}, {'topic':'Ethereum'}, {'topic':'btc'},{'topic':''},{'topic':'../../.env'}, {'topic':'zec','format':'md'},{'topic':'zec','format':'html'}]
for window in ('24h','1h','2026-09-17..2026-09-19','2026-09-23..2026-09-17','2026-02-30..2026-02-31','aaaaaaaaaa..zzzzzzzzzz','2026/09/17..2026/09/19','2026-09-24..2026-09-24','2026-09-11..2026-09-11'):
 cases.append({'topic':'zec','window':window})
results=[get(path='/healthz'),get(path='/openapi.json')]
for q in cases:
 r=get(q);results.append(r);d=r['data'] or {};print(q,r['http'],d.get('status',d.get('detail')),d.get('counts'),r['seconds'],flush=True)
for day in range(11,24):results.append(get({'topic':'zec','window':f'2026-09-{day:02}..2026-09-{day:02}'}))
start=time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool: batch=list(pool.map(lambda _:get({'topic':'zec'}),range(6)))
print('parallel',round(time.perf_counter()-start,3),[(r['http'],r['seconds']) for r in batch],flush=True)
results.extend(batch)
Path('artifacts/pulse-critique/http-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
full=next(r for r in results if r['params']=={'topic':'zec'})['data']
print('md matches',full['brief_markdown']==Path('artifacts/pulse-zec/brief.md').read_text())
print('db md5',hashlib.md5(Path('astrafeed.db').read_bytes()).hexdigest())
