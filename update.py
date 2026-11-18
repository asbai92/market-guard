#!/usr/bin/env python3
"""Collecte Market Guard — sources publiques, calculs explicites, aucune transaction."""
import csv, io, json, os, statistics, urllib.request
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"
DATA.mkdir(exist_ok=True)
UA="Mozilla/5.0 (compatible; MarketGuard/2.0)"

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json,text/csv,*/*"})
    with urllib.request.urlopen(req,timeout=40) as r: return r.read()

def yahoo(symbol):
    import urllib.parse
    end=int(datetime.now(timezone.utc).timestamp()); start=end-5*366*86400
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol,safe='')}?period1={start}&period2={end}&interval=1d"
    j=json.loads(get(url)); result=j["chart"]["result"][0]; q=result["indicators"]["quote"][0]
    rows=[]
    for i,t in enumerate(result.get("timestamp",[])):
        c=q["close"][i]; lo=q["low"][i]
        if c is not None and lo is not None:
            rows.append({"date":datetime.fromtimestamp(t,timezone.utc).date().isoformat(),"close":float(c),"low":float(lo)})
    if len(rows)<180: raise RuntimeError(f"Historique insuffisant: {symbol}")
    return rows

def fred():
    ids=["DGS10","DGS2","ICSA","UNRATE","CORALACBS","CPIAUCSL","FEDFUNDS"]
    raw=get("https://fred.stlouisfed.org/graph/fredgraph.csv?id="+",".join(ids)).decode("cp1252")
    out={k:[] for k in ids}
    for row in csv.DictReader(io.StringIO(raw)):
        dt=row.get("observation_date") or row.get("DATE")
        if not dt: continue
        for k in ids:
            try: v=float(row[k]) if row.get(k) not in ("",".","NaN",None) else None
            except (ValueError,KeyError): v=None
            if v is not None: out[k].append({"date":dt,"value":v})
    for k,v in out.items():
        if not v: raise RuntimeError("Série FRED absente: "+k)
    return out

def weekly(rows):
    groups={}
    for r in rows:
        d=date.fromisoformat(r["date"]); iso=d.isocalendar(); key=f"{iso.year}-{iso.week:02d}"
        g=groups.setdefault(key,{"week":key,"date":r["date"],"close":r["close"],"low":r["low"]})
        g.update(date=r["date"],close=r["close"]); g["low"]=min(g["low"],r["low"])
    w=list(groups.values())
    today=datetime.now(timezone.utc).date()
    if w and w[-1]["week"]==f"{today.isocalendar().year}-{today.isocalendar().week:02d}" and today.weekday()<4: w=w[:-1]
    return w

def trend(rows):
    w=weekly(rows)
    if len(w)<34: return {"available":False}
    c=[x["close"] for x in w]
    ma=[statistics.mean(c[i-29:i+1]) if i>=29 else None for i in range(len(c))]
    # Chaque clôture est comparée au support des 26 semaines qui la précèdent.
    support_now=min(x["low"] for x in w[-27:-1])
    support_prev=min(x["low"] for x in w[-28:-2])
    broken=bool(c[-1]<support_now and c[-2]<support_prev)
    return {"available":True,"close":c[-1],"ma30":ma[-1],"ma30_4w_ago":ma[-5],
            "stage4":bool(c[-1]<ma[-1] and ma[-1]<ma[-5]),
            "support26":support_now,"support_break":broken,"last_week":w[-1]["date"],
            "change_1w_pct":(c[-1]/c[-2]-1)*100,"weeks":len(w)}

def ad_metrics(sp):
    # Source communautaire DeanFinancials, univers S&P 500 (proxy, pas NYSE/Dow).
    j=json.loads(get("https://raw.githubusercontent.com/DeanFinancials/deanfi-data/main/advance-decline/ad_line_historical.json"))
    meta=j.get("metadata",{}); generated=meta.get("generated_at")
    arr=j.get("data",[])
    vals=sorted([(x["date"],float(x["ad_line"])) for x in arr if x.get("date") and x.get("ad_line") is not None])
    if not generated or (datetime.now(timezone.utc)-datetime.fromisoformat(generated.replace("Z","+00:00"))).days>4:
        return {"available":False,"status":None,"detail":"Source A/D trop ancienne ou date de génération absente.","generated_at":generated}
    if len(vals)<100: return {"available":False,"status":None,"detail":"Historique A/D insuffisant."}
    cutoff=(date.fromisoformat(vals[-1][0])-timedelta(days=210)).isoformat()
    recent=[x for x in vals if x[0]>=cutoff]
    peak=max(recent,key=lambda x:x[1]); gap=len(recent)-1-next(i for i,x in enumerate(recent) if x[0]==peak[0])
    before=[x["close"] for x in sp if x["date"]<=peak[0]]
    after=[x["close"] for x in sp if x["date"]>peak[0]]
    price_new_high=bool(before and after and max(after)>max(before))
    divergence=gap>=63 and vals[-1][1]<peak[1] and price_new_high
    # Confirmation 2022 : l'A/D passe sous son plus bas depuis le rebond récent.
    low_60=min(v for _,v in vals[-61:-1]) if len(vals)>=61 else min(v for _,v in vals)
    new_low=vals[-1][1]<low_60
    return {"available":True,"status":bool(divergence),"divergence":bool(divergence),"new_low":bool(new_low),
            "peak_date":peak[0],"last_date":vals[-1][0],"sessions_since_peak":gap,
            "price_new_high_after_peak":price_new_high,"current":vals[-1][1],"previous_60d_low":low_60,
            "detail":f"Divergence > 3 mois: {bool(divergence)}. Nouveau plus bas A/D sur 60 séances: {bool(new_low)}. Univers S&P 500, proxy." ,
            "generated_at":generated}

def criterion(name,status,detail,weight=1):
    return {"name":name,"status":"unknown" if status is None else ("yes" if status else "no"),"detail":detail,"weight":weight}

def main():
    now=datetime.now(timezone.utc).isoformat(timespec="seconds")
    errors=[]; sources=[]; raw={}; indices={}; trends={}
    for key,sym,label in [("sp500","^GSPC","S&P 500"),("dow","^DJI","Dow Jones"),("nasdaq","^NDX","Nasdaq 100")]:
        try:
            raw[key]=yahoo(sym); trends[key]=trend(raw[key])
            indices[key]={"close":raw[key][-1]["close"],"date":raw[key][-1]["date"],"change_1w_pct":trends[key].get("change_1w_pct")}
            sources.append({"name":label+" — Yahoo Finance","date":raw[key][-1]["date"],"status":"cours récupérés"})
        except Exception as e: errors.append(label+": "+str(e)); trends[key]={"available":False}; indices[key]={}
    macro={}
    try:
        f=fred()
        d10=f["DGS10"][-1]["value"]; d2=f["DGS2"][-1]["value"]
        claims=f["ICSA"]; avg4=statistics.mean(x["value"] for x in claims[-4:]); avg13=statistics.mean(x["value"] for x in claims[-13:])
        un=f["UNRATE"]; un_rise=statistics.mean(x["value"] for x in un[-3:])>=min(x["value"] for x in un[-12:])+0.3 if len(un)>=12 else None
        co=f["CORALACBS"]; co_rise=(co[-1]["value"]>co[-2]["value"]>co[-3]["value"] and co[-1]["value"]-co[-5]["value"]>=0.15) if len(co)>=5 else None
        cpi=f["CPIAUCSL"]; cpi_yoy=(cpi[-1]["value"]/cpi[-13]["value"]-1)*100 if len(cpi)>=13 else None
        fed=f["FEDFUNDS"][-1]["value"]
        macro={"yield_spread":d10-d2,"yield_inverted":d10<d2,"claims_latest":claims[-1]["value"],
          "claims_4w_avg":avg4,"claims_13w_avg":avg13,"claims_rising":avg4>avg13*1.08,
          "unemployment_latest":un[-1]["value"],"unemployment_rising":un_rise,
          "chargeoff_latest":co[-1]["value"],"chargeoff_date":co[-1]["date"],"chargeoffs_rising":co_rise,
          "cpi_yoy":cpi_yoy,"fed_funds":fed,"inflation_restrictive":(cpi_yoy>=3 and fed>=4) if cpi_yoy is not None else None,
          "dates":{k:v[-1]["date"] for k,v in f.items()}}
        sources.append({"name":"FRED / Federal Reserve","date":max(macro["dates"].values()),"status":"séries publiques récupérées"})
    except Exception as e: errors.append("FRED: "+str(e))
    ad={"available":False,"status":None,"detail":"Source A/D indisponible."}
    try:
        ad=ad_metrics(raw.get("sp500",[]))
        if ad.get("available"): sources.append({"name":"DeanFinancials — A/D S&P 500 (proxy)","date":ad.get("last_date"),"status":"source communautaire; fraîcheur contrôlée"})
    except Exception as e: errors.append("A/D: "+str(e))
    stages=[trends.get(k,{}).get("stage4") for k in ("sp500","dow","nasdaq")]
    breaks=[trends.get(k,{}).get("support_break") for k in ("sp500","dow","nasdaq")]
    all_stages=all(x is True for x in stages) if all(trends.get(k,{}).get("available") for k in ("sp500","dow","nasdaq")) else None
    all_breaks=all(x is True for x in breaks) if all(trends.get(k,{}).get("available") for k in ("sp500","dow","nasdaq")) else None
    criteria=[
      criterion("Divergence A/D supérieure à 3 mois",ad.get("divergence"),ad.get("detail"),2),
      criterion("A/D inscrit un nouveau plus bas après le rebond",ad.get("new_low"),ad.get("detail"),1),
      criterion("MM30 semaines descendante et cours sous MM30 sur les 3 indices",all_stages,f"{sum(x is True for x in stages)}/3 indices en phase 4.",2),
      criterion("Les 3 indices cassent leur support hebdomadaire",all_breaks,"Cassure confirmée sur deux clôtures hebdomadaires sous les supports calculés sur les 26 semaines antérieures.",2)
    ]
    if macro:
      criteria += [
        criterion("Courbe des taux 10 ans – 2 ans inversée",macro["yield_inverted"],f"Écart 10 ans – 2 ans : {macro['yield_spread']:.2f} point.",1),
        criterion("Inscriptions au chômage en hausse",macro["claims_rising"],f"Moyenne 4 semaines {macro['claims_4w_avg']:,.0f} vs 13 semaines {macro['claims_13w_avg']:,.0f}.",1),
        criterion("Taux de charge-offs bancaires en hausse",macro["chargeoffs_rising"],f"Dernier taux : {macro['chargeoff_latest']:.2f} % ({macro['chargeoff_date']}).",1),
        criterion("Inflation élevée et taux directeurs restrictifs",macro["inflation_restrictive"],f"CPI 12 mois : {macro['cpi_yoy']:.2f} % ; Fed Funds : {macro['fed_funds']:.2f} %." if macro.get("cpi_yoy") is not None else "Données CPI insuffisantes.",1)]
    else:
      criteria += [criterion(n,None,"Séries FRED indisponibles.",1) for n in ["Courbe des taux 10 ans – 2 ans inversée","Inscriptions au chômage en hausse","Taux de charge-offs bancaires en hausse","Inflation élevée et taux directeurs restrictifs"]]
    score=sum(x["weight"] for x in criteria if x["status"]=="yes"); coverage=sum(x["status"]!="unknown" for x in criteria)
    all_market=all(trends.get(k,{}).get("available") for k in ("sp500","dow","nasdaq"))
    if coverage<5 or not all_market:
      status="UNKNOWN"; explanation="Collecte incomplète. Les données manquantes ne sont pas considérées comme rassurantes."
    elif all_stages is True and all_breaks is True and score>=6:
      status="EXIT"; explanation="Les 3 indices sont en phase 4 et ont confirmé la cassure de leurs supports hebdomadaires, avec un score de risque élevé. C'est le signal technique fort décrit dans l'approche 2022; vérifier les données et le portefeuille avant toute décision."
    elif score>=3 or any(x is True for x in stages) or any(x is True for x in breaks):
      status="CAUTION"; explanation="Plusieurs signaux se dégradent. Vigilance renforcée, sans signal complet de sortie."
    else:
      status="HOLD"; explanation="Les signaux disponibles ne réunissent pas les conditions de vigilance renforcée. Cela ne garantit pas l'absence de baisse."
    data={"generated_at":now,"verdict":{"status":status,"score":score,"max_score":sum(x["weight"] for x in criteria),"coverage":coverage,"explanation":explanation},
      "indices":indices,"trends":trends,"macro":macro,"ad":ad,"criteria":criteria,"sources":sources,
      "health":{"stale":bool(errors or not ad.get("available")),"errors":errors,"notes":[
       "La ligne A/D utilisée est un proxy S&P 500, pas la ligne NYSE exacte citée dans l'article 2019.",
       "La cassure est testée sur deux clôtures hebdomadaires sous le plus bas des 26 semaines précédentes.",
       "La phase 4 correspond à une clôture sous MM30 semaines avec MM30 descendante sur 4 semaines.",
       "Les seuils de chômage, charge-offs et inflation sont des règles indicatives ajoutées au modèle, pas des seuils officiels BlogBourse.",
       "Le score et les seuils doivent être backtestés; ce verdict n'est pas un ordre de vente."
      ]}}
    (DATA/"latest.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    state_path=DATA/"state.json"; old={}
    try: old=json.loads(state_path.read_text())
    except Exception: pass
    rank={"UNKNOWN":-1,"HOLD":0,"CAUTION":1,"EXIT":2}; old_status=old.get("status","UNKNOWN")
    if rank[status]>rank.get(old_status,-1) and old_status!="UNKNOWN": send_alert(status,score,explanation)
    state_path.write_text(json.dumps({"status":status,"score":score,"updated_at":now},indent=2),encoding="utf-8")
    print(json.dumps({"status":status,"score":score,"coverage":coverage,"errors":errors},ensure_ascii=False))

def send_alert(status,score,message):
    token=os.getenv("TELEGRAM_BOT_TOKEN"); chat=os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat: return
    import urllib.parse
    body=urllib.parse.urlencode({"chat_id":chat,"text":f"Market Guard — {status}\nScore : {score}/12\n{message}"}).encode()
    req=urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",data=body)
    with urllib.request.urlopen(req,timeout=20) as r: print("Telegram:",r.status)

if __name__=="__main__": main()
