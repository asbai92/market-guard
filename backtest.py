#!/usr/bin/env python3
"""Backtest technique simplifie de Market Guard : recherche des faux signaux et retards."""
import json, urllib.request, urllib.parse, statistics
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SYMBOLS={"S&P 500":"^GSPC","Dow Jones":"^DJI","Nasdaq 100":"^NDX"}
CRISES=[("Bulle internet","2000-03-01","2002-10-01"),("Crise financiere","2007-10-01","2009-03-01"),("COVID","2020-02-01","2020-04-01"),("Bear market 2022","2022-01-01","2022-10-01")]
def get(symbol):
 start=int(datetime(1990,1,1,tzinfo=timezone.utc).timestamp()); end=int(datetime.now(timezone.utc).timestamp())
 url=f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol,safe='')}?period1={start}&period2={end}&interval=1d"
 req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 MarketGuard"})
 with urllib.request.urlopen(req,timeout=60) as r: data=json.loads(r.read())["chart"]["result"][0]
 q=data["indicators"]["quote"][0]; daily=[]
 for i,t in enumerate(data["timestamp"]):
  c=q["close"][i]; lo=q["low"][i]
  if c is not None and lo is not None: daily.append({"date":datetime.fromtimestamp(t,timezone.utc).date().isoformat(),"close":float(c),"low":float(lo)})
 return daily
def weekly(rows):
 groups={}
 for r in rows:
  d=datetime.fromisoformat(r["date"]); iso=d.isocalendar(); key=(iso.year,iso.week)
  g=groups.setdefault(key,{"date":r["date"],"close":r["close"],"low":r["low"]})
  g["date"]=r["date"];g["close"]=r["close"];g["low"]=min(g["low"],r["low"])
 return list(groups.values())
def signals(w):
 out=[]
 for i,x in enumerate(w):
  if i<34:out.append({"date":x["date"],"combined":False});continue
  closes=[y["close"] for y in w[:i+1]]
  ma=statistics.mean(closes[-30:]); ma4ago=statistics.mean(closes[-34:-4])
  support=min(y["low"] for y in w[i-26:i]); prev=min(y["low"] for y in w[i-27:i-1])
  stage4=x["close"]<ma and ma<ma4ago
  broken=x["close"]<support and w[i-1]["close"]<prev
  out.append({"date":x["date"],"close":x["close"],"stage4":stage4,"support_break":broken,"combined":stage4 and broken})
 return out
def main():
 allres={}
 for name,symbol in SYMBOLS.items():
  daily=get(symbol); w=weekly(daily); sig=signals(w)
  allres[name]={"start":daily[0]["date"],"end":daily[-1]["date"],"weeks":len(w),"signals":sig}
 eventresults=[]
 for title,start,end in CRISES:
  item={"event":title,"period":[start,end],"indices":{}}
  for name,d in allres.items():
   s=[x for x in d["signals"] if start<=x["date"]<=end and x["combined"]]
   item["indices"][name]={"signal_during_period":bool(s),"first_signal_date":s[0]["date"] if s else None}
  eventresults.append(item)
 stats={}
 for name,d in allres.items():
  s=[x for x in d["signals"] if x["combined"]]
  stats[name]={"signal_weeks":len(s),"weeks_total":len(d["signals"]),"signal_frequency_pct":round(len(s)/max(1,len(d["signals"]))*100,2),"first_signal":s[0]["date"] if s else None}
 out={"generated_at":datetime.now(timezone.utc).isoformat(),"method":"Backtest technique seul: cours sous MM30 semaines descendante ET cassure confirmee de deux clotures sous support des 26 semaines precedentes. N'inclut pas macro, A/D, ni simulation de portefeuille LQQ; supports approximatifs.","crises":eventresults,"statistics":stats,"series":allres}
 (ROOT/"data"/"backtest.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({"crises":eventresults,"statistics":stats},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
