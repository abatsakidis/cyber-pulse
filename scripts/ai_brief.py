#!/usr/bin/env python3
import json,os
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1]; news=R/'data/news.json'; out=R/'data/ai.json'
items=json.loads(news.read_text()) if news.exists() else []
counts={}
for x in items[:150]: counts[x.get('category','General Security')]=counts.get(x.get('category','General Security'),0)+1
top=sorted(counts.items(),key=lambda z:z[1],reverse=True)[:6]
# Safe default: heuristic brief. The dashboard remains fully functional without an API key.
out.write_text(json.dumps({'generated_at':datetime.now(timezone.utc).isoformat(),'mode':'heuristic','summary':f'Ανάλυση {len(items[:150])} πρόσφατων άρθρων. Κυρίαρχες θεματικές: '+', '.join(f'{k} ({v})' for k,v in top)+'.','clusters':[k for k,v in top]},ensure_ascii=False,indent=2))
