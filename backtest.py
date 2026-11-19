#!/usr/bin/env python3
"""Comparaison historique buy-and-hold vs signal technique, sans anticipation."""
import json, math, urllib.request, urllib.parse, statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SYMBOLS={"S&P 500":"^GSPC","Dow Jones":"^DJI","Nasdaq 100":"^NDX"}
CRISES=[("Bulle internet","2000-03-01","2002-10-01"),("Crise financiere","2007-10-01","2009-03-01"),("COVID","2020-02-01","2020-04-01"),("Bear market 2022","2022-01-01","2022-10-01")]

def get(symbol, start_year=1990):
    start=int(datetime(start_year,1,1,tzinfo=timezone.utc).timestamp())
    end=int(datetime.now(timezone.utc).timestamp())
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol,safe='')}?period1={start}&period2={end}&interval=1d"
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 MarketGuard"})
    with urllib.request.urlopen(req,timeout=60) as r:
        payload=json.loads(r.read())["chart"]
    if payload.get("error") or not payload.get("result"):
        raise RuntimeError(f"Données indisponibles pour {symbol}: {payload.get('error')}")
    data=payload["result"][0]; q=data["indicators"]["quote"][0]; rows=[]
    for i,t in enumerate(data["timestamp"]):
        c=q["close"][i]; lo=q["low"][i]
        if c is not None and lo is not None:
            rows.append({"date":datetime.fromtimestamp(t,timezone.utc).date().isoformat(),"close":float(c),"low":float(lo)})
    if len(rows)<100: raise RuntimeError(f"Historique insuffisant pour {symbol}")
    return rows

def weekly(rows):
    groups={}
    for r in rows:
        iso=datetime.fromisoformat(r["date"]).isocalendar(); key=(iso.year,iso.week)
        g=groups.setdefault(key,{"date":r["date"],"close":r["close"],"low":r["low"]})
        g["date"]=r["date"]; g["close"]=r["close"]; g["low"]=min(g["low"],r["low"])
    return list(groups.values())

def signals(w):
    out=[]
    for i,x in enumerate(w):
        if i<34:
            out.append({"date":x["date"],"close":x["close"],"combined":False,"reentry":False})
            continue
        closes=[y["close"] for y in w[:i+1]]
        ma=statistics.mean(closes[-30:]); ma4ago=statistics.mean(closes[-34:-4])
        support=min(y["low"] for y in w[i-26:i])
        prev_support=min(y["low"] for y in w[i-27:i-1])
        stage4=x["close"]<ma and ma<ma4ago
        broken=x["close"]<support and w[i-1]["close"]<prev_support
        # Réentrée confirmée: deux clôtures consécutives au-dessus de MM30,
        # MM30 en hausse sur 4 semaines. Décision à la clôture, effet semaine suivante.
        reentry=(x["close"]>ma and w[i-1]["close"]>statistics.mean([y["close"] for y in w[i-30:i-1]])
                 and ma>ma4ago)
        out.append({"date":x["date"],"close":x["close"],"ma30":ma,
                    "stage4":stage4,"support_break":broken,
                    "combined":stage4 and broken,"reentry":reentry})
    # Exiger deux confirmations hebdomadaires successives.
    for i in range(1,len(out)):
        out[i]["reentry"]=bool(out[i]["reentry"] and out[i-1]["reentry"])
    return out

def metrics(returns, invested, dates):
    if not returns: return {}
    equity=peak=1.0; maxdd=0.0
    for r in returns:
        equity*=1+r; peak=max(peak,equity); maxdd=min(maxdd,equity/peak-1)
    years=max((datetime.fromisoformat(dates[-1])-datetime.fromisoformat(dates[0])).days/365.25,0.01)
    return {"total_return_pct":round((equity-1)*100,2),
            "cagr_pct":round((equity**(1/years)-1)*100,2),
            "max_drawdown_pct":round(maxdd*100,2),
            "time_in_market_pct":round(sum(invested)/len(invested)*100,1),
            "weeks":len(returns)}

def simulate(price_weeks, signal_weeks):
    pmap={x["date"]:x for x in price_weeks}
    smap={x["date"]:x for x in signal_weeks}
    dates=sorted(set(pmap)&set(smap))
    if len(dates)<60: raise RuntimeError("Pas assez de semaines communes pour simuler")
    dates=dates[34:]
    buy=[]; strat=[]; positions=[]; pos=1; exits=[]; entries=[]
    prev=None
    for date in dates:
        px=pmap[date]["close"]
        if prev is not None:
            ret=px/prev-1
            buy.append(ret); strat.append(ret*pos); positions.append(pos)
        sig=smap[date]
        # Les signaux de la clôture actuelle ne s'appliquent qu'à la semaine suivante.
        if sig.get("combined") and pos==1:
            pos=0; exits.append(date)
        elif sig.get("reentry") and pos==0:
            pos=1; entries.append(date)
        prev=px
    invested=[1 if x else 0 for x in positions]
    return {"buy_and_hold":metrics(buy,[1]*len(buy),dates[1:]),
            "strategy":metrics(strat,invested,dates[1:]),
            "exits":exits,"reentries":entries,
            "missed_rebound_risk":"La stratégie reste en cash jusqu'à confirmation de réentrée."}

def main():
    allres={}
    for name,symbol in SYMBOLS.items():
        daily=get(symbol); w=weekly(daily); sig=signals(w)
        allres[name]={"start":daily[0]["date"],"end":daily[-1]["date"],"weeks":len(w),"signals":sig}
    events=[]
    for title,start,end in CRISES:
        item={"event":title,"period":[start,end],"indices":{}}
        for name,d in allres.items():
            found=[x for x in d["signals"] if start<=x["date"]<=end and x["combined"]]
            item["indices"][name]={"signal_during_period":bool(found),"first_signal_date":found[0]["date"] if found else None}
        events.append(item)
    stats={}
    for name,d in allres.items():
        found=[x for x in d["signals"] if x["combined"]]
        stats[name]={"signal_weeks":len(found),"weeks_total":len(d["signals"]),
                     "signal_frequency_pct":round(len(found)/max(1,len(d["signals"]))*100,2),
                     "first_signal":found[0]["date"] if found else None}
    comparisons={}
    for name in ("S&P 500","Dow Jones","Nasdaq 100"):
        comparisons[name]=simulate(weekly(get(SYMBOLS[name])),allres[name]["signals"])
    lqq={}
    try:
        lqq_daily=get("LQQ.PA",2006); lqq_w=weekly(lqq_daily)
        lqq["available"]=True
        lqq["symbol"]="LQQ.PA"
        lqq["start"]=lqq_daily[0]["date"]
        lqq["comparison_using_nasdaq_signal"]=simulate(lqq_w,allres["Nasdaq 100"]["signals"])
        lqq["warning"]="Historique Yahoo Finance; prix de clôture seulement. Vérifier ajustements, dividendes, frais et éventuelles modifications du fonds."
    except Exception as e:
        lqq={"available":False,"reason":str(e),"warning":"Le test LQQ sera affiché indisponible plutôt que remplacé par une approximation."}
    out={"generated_at":datetime.now(timezone.utc).isoformat(),
         "method":"Simulation hebdomadaire sans anticipation: signal évalué à la clôture, position modifiée pour la semaine suivante. Sortie si MM30 descendante + cassure confirmée; réentrée après deux clôtures au-dessus de MM30 avec moyenne en hausse. Cash rémunéré 0%; sans frais, fiscalité, glissement ni dividendes. Résultats historiques non prédictifs.",
         "crises":events,"statistics":stats,"comparisons":comparisons,"lqq":lqq}
    (ROOT/"data"/"backtest.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"crises":events,"comparisons":comparisons,"lqq":lqq},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
