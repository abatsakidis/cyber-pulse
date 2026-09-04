#!/usr/bin/env python3
import json,re,hashlib,html as H
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request,urlopen
from xml.etree import ElementTree as ET
R=Path(__file__).resolve().parents[1]; S=R/'data/sources.json'; O=R/'data/news.json'; T=R/'data/status.json'
def clean(x):
 x=re.sub(r'<script.*?</script>|<style.*?</style>',' ',x or '',flags=re.I|re.S); return re.sub(r'\s+',' ',H.unescape(re.sub(r'<[^>]+>',' ',x))).strip()
def txt(e,names):
 for n in names:
  for x in e.iter():
   if x.tag.split('}')[-1].lower()==n.lower() and (x.text or '').strip(): return x.text.strip()
 return ''
def date(e):
 v=txt(e,['pubDate','published','updated','date','dc:date'])
 try:return parsedate_to_datetime(v).astimezone(timezone.utc).isoformat()
 except:
  try:return datetime.fromisoformat(v.replace('Z','+00:00')).astimezone(timezone.utc).isoformat()
  except:return datetime.now(timezone.utc).isoformat()
def img(e,d):
 for x in e.iter():
  t=x.tag.split('}')[-1].lower(); u=x.attrib.get('url') or x.attrib.get('href')
  if t in ('content','thumbnail','enclosure') and u and re.search(r'\.(jpg|jpeg|png|webp)(\?|$)',u,re.I): return u
 m=re.search(r'<img[^>]+src=["\']([^"\']+)',d,re.I); return m.group(1) if m else ''
def cat(t,d):
 s=(t+' '+d).lower()
 for c,p in [('AI Security',r'\b(ai|artificial intelligence|llm|agentic|generative ai|chatgpt|copilot)\b.{0,90}\b(secur|hack|attack|cyber|phish|malware|ransom|exploit)'),('Ransomware',r'ransomware|extortion'),('Malware',r'malware|trojan|botnet|spyware|infostealer|rootkit'),('Vulnerability',r'zero[- ]day|cve-\d{4}-\d+|vulnerab|exploit|patch|security flaw'),('Cyberwarfare',r'cyber ?war|state[- ]sponsor|nation[- ]state|apt\d*|espionage|geopolit'),('Privacy',r'privacy|surveillance|data breach|data leak|personal data'),('Hacking',r'hack|phish|credential|ddos|intrusion|cyberattack|cyber attack')]:
  if re.search(p,s,re.I): return c
 return 'General Security'
def parse(raw,source):
 root=ET.fromstring(raw); out=[]
 for e in root.iter():
  if e.tag.split('}')[-1].lower() not in ('item','entry'): continue
  t=clean(txt(e,['title'])); l=''
  for x in e.iter():
   if x.tag.split('}')[-1].lower()=='link':
    l=x.attrib.get('href') or (x.text or '').strip()
    if l: break
  d=clean(txt(e,['description','summary','content','encoded']))
  if not t or not l: continue
  out.append({'id':hashlib.sha1((l+t).encode()).hexdigest()[:16],'source':source,'title':t,'description':d[:600],'link':l,'date':date(e),'image':img(e,d),'category':cat(t,d),'hot':bool(re.search(r'zero[- ]day|actively exploited|critical|ransomware|emergency|breach|massive attack',t+' '+d,re.I))})
 return out
def main():
 all=[]; status=[]
 for s in json.loads(S.read_text()):
  if not s.get('enabled'): continue
  row={'name':s['name'],'url':s['url'],'ok':False,'count':0}
  try:
   req=Request(s['url'],headers={'User-Agent':'CyberPulseRSS/2.0','Accept':'application/rss+xml,application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.5'})
   with urlopen(req,timeout=25) as r: raw=r.read(4000000)
   x=parse(raw,s['name']); all+=x; row.update(ok=True,count=len(x))
  except Exception as e: row['error']=str(e)[:220]
  status.append(row)
 d={x['id']:x for x in all}; items=sorted(d.values(),key=lambda x:x['date'],reverse=True)[:700]
 O.write_text(json.dumps(items,ensure_ascii=False,indent=2)); T.write_text(json.dumps({'updated':datetime.now(timezone.utc).isoformat(),'sources':status},ensure_ascii=False,indent=2)); print(f'{len(items)} articles; {sum(x["ok"] for x in status)}/{len(status)} sources OK')
if __name__=='__main__': main()
