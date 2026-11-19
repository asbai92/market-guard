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
    end=int(datetime.now(timezone.utc).timestamp()); start=int(datetime(1985,1,1,tzinfo=timezone.utc).timestamp())
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
    # Télécharger les séries séparément : l'export multi-séries FRED renvoie parfois un CSV mal formé.
    ids=["T10Y2Y","DGS10","DGS2","ICSA","UNRATE","CORALACBS","CPIAUCSL","FEDFUNDS"]
    out={}
    for k in ids:
        payload=get("https://fred.stlouisfed.org/graph/fredgraph.csv?id="+k).decode("utf-8-sig",errors="replace")
        reader=csv.reader(io.StringIO(payload,newline=""))
        rows=list(reader)
        if not rows: raise RuntimeError("CSV FRED vide: "+k)
        header=[x.strip() for x in rows[0]]
        try:
            date_idx=header.index("observation_date")
        except ValueError:
            date_idx=0
        try:
            value_idx=header.index(k)
        except ValueError:
            value_idx=1
        vals=[]
        for row in rows[1:]:
            if len(row)<=max(date_idx,value_idx): continue
            dt=row[date_idx].strip()
            raw=row[value_idx].strip()
            if not dt or raw in ("",".","nan","NaN"): continue
            try: vals.append({"date":dt,"value":float(raw)})
            except ValueError: continue
        if not vals: raise RuntimeError("Série FRED vide ou illisible: "+k)
        out[k]=vals
    return out
def yield_curve_history(series):
    monthly={}
    for row in series:
        monthly.setdefault(row['date'][:7], []).append(row['value'])
    current_month=datetime.now(timezone.utc).strftime('%Y-%m')
    values=[{'month':m,'avg':statistics.mean(v)} for m,v in sorted(monthly.items()) if m<current_month]
    if len(values)<3:
        return {'available':False,'confirmed_inversion':None,'detail':'Historique mensuel insuffisant.'}
    latest=values[-1]
    # Identifier le premier mois de la dernière séquence continue d'inversion,
    # pas le début de la dernière fenêtre glissante de trois mois.
    negative=[i for i,x in enumerate(values) if x['avg']<0]
    runs=[]
    if negative:
        run=[negative[0]]
        for idx in negative[1:]:
            if idx==run[-1]+1: run.append(idx)
            else:
                if len(run)>=3: runs.append(run)
                run=[idx]
        if len(run)>=3: runs.append(run)
    if not runs:
        current=latest['avg']<0
        return {'available':True,'confirmed_inversion':False,'currently_inverted':current,'start_month':None,'months_since_start':None,'risk_window_12_18m':False,'watch':current,'latest_monthly_average':latest['avg'],'latest_month':latest['month'],'detail':'Aucune séquence de 3 moyennes mensuelles négatives détectée.'}
    start=values[runs[-1][0]]['month']
    end=values[runs[-1][-1]]['month']
    sy,sm=map(int,start.split('-')); ly,lm=map(int,latest['month'].split('-'))
    elapsed=(ly-sy)*12+(lm-sm)
    current=latest['avg']<0
    window=12<=elapsed<=18
    watch=current or (0<=elapsed<=18)
    return {'available':True,'confirmed_inversion':True,'currently_inverted':current,'start_month':start,'end_month':end,'months_since_start':elapsed,'risk_window_12_18m':window,'watch':watch,'latest_monthly_average':latest['avg'],'latest_month':latest['month'],'detail':'Inversion mensuelle persistante de '+start+' à '+end+'; '+str(elapsed)+' mois depuis le début. Fenêtre historique 12–18 mois: '+('oui' if window else 'non')+'.'}

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

def age_days(date_text):
    try:
        d=date.fromisoformat(str(date_text)[:10])
        return (datetime.now(timezone.utc).date()-d).days
    except Exception:
        return None

def freshness_check(indices, macro):
    checks=[]
    for k,label in [("sp500","S&P 500"),("dow","Dow Jones"),("nasdaq","Nasdaq 100")]:
        dt=indices.get(k,{}).get("date"); age=age_days(dt)
        checks.append({"name":label,"date":dt,"age_days":age,"max_age_days":4,"fresh":age is not None and age<=4})
    if macro:
        for key,label,max_age in [("claims_latest_date","Demandes chômage",14),("unemployment_date","Chômage",60),("chargeoff_date","Charge-offs",240),("yield_spread_date","Courbe taux",7)]:
            dt=macro.get(key); age=age_days(dt)
            checks.append({"name":label,"date":dt,"age_days":age,"max_age_days":max_age,"fresh":age is not None and age<=max_age})
        dt=macro.get("dates",{}).get("CPIAUCSL"); age=age_days(dt)
        checks.append({"name":"CPI","date":dt,"age_days":age,"max_age_days":60,"fresh":age is not None and age<=60})
    return {"checks":checks,"all_fresh":bool(checks) and all(x["fresh"] for x in checks),"stale_items":[x for x in checks if not x["fresh"]]}

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
        yc=yield_curve_history(f["T10Y2Y"])
        d10=f["DGS10"][-1]["value"]; d2=f["DGS2"][-1]["value"]
        claims=f["ICSA"]; avg4=statistics.mean(x["value"] for x in claims[-4:]); avg13=statistics.mean(x["value"] for x in claims[-13:])
        un=f["UNRATE"]; un_rise=statistics.mean(x["value"] for x in un[-3:])>=min(x["value"] for x in un[-12:])+0.3 if len(un)>=12 else None
        co=f["CORALACBS"]; co_rise=(co[-1]["value"]>co[-2]["value"]>co[-3]["value"] and co[-1]["value"]-co[-5]["value"]>=0.15) if len(co)>=5 else None
        cpi=f["CPIAUCSL"]; cpi_yoy=(cpi[-1]["value"]/cpi[-13]["value"]-1)*100 if len(cpi)>=13 else None
        fed=f["FEDFUNDS"][-1]["value"]
        macro={"yield_spread":f["T10Y2Y"][-1]["value"],"yield_spread_date":f["T10Y2Y"][-1]["date"],"yield_inverted":f["T10Y2Y"][-1]["value"]<0,"yield_curve":yc,"claims_latest":claims[-1]["value"],"claims_latest_date":claims[-1]["date"],
          "claims_4w_avg":avg4,"claims_13w_avg":avg13,"claims_rising":avg4>avg13*1.08,
          "unemployment_latest":un[-1]["value"],"unemployment_date":un[-1]["date"],"unemployment_rising":un_rise,
          "chargeoff_latest":co[-1]["value"],"chargeoff_date":co[-1]["date"],"chargeoffs_rising":co_rise,
          "cpi_yoy":cpi_yoy,"fed_funds":fed,"inflation_restrictive":(cpi_yoy>=3 and fed>=4) if cpi_yoy is not None else None,
          "dates":{k:v[-1]["date"] for k,v in f.items()}}
        sources.append({"name":"FRED / Federal Reserve","date":max(macro["dates"].values()),"status":"séries publiques récupérées"})
    except Exception as e: errors.append("FRED: "+str(e))
    # L'article demande la NYSE A/D Line ($ADLINENYA) comparee au Dow.
    # Le proxy DeanFinancials S&P 500 est volontairement exclu du verdict.
    ad={"available":False,"status":None,"divergence":None,"new_low":None,
        "detail":"NYSE A/D Line ($ADLINENYA) non connectee. Aucun proxy S&P 500 n'est utilise dans les criteres NYSE."}
    ad_sp500={"available":False,"detail":"Proxy S&P 500 non disponible."}
    try:
        ad_sp500=ad_metrics(raw["sp500"])
        ad_sp500["warning"]="Univers S&P 500 uniquement : indicateur secondaire, non substituable à la NYSE A/D Line."
        sources.append({"name":"DeanFi — A/D S&P 500 (proxy secondaire)","date":ad_sp500.get("last_date"),"status":"disponible" if ad_sp500.get("available") else "indisponible"})
    except Exception as e:
        ad_sp500={"available":False,"detail":"Collecte A/D S&P 500 impossible : "+str(e)}
    stages=[trends.get(k,{}).get("stage4") for k in ("sp500","dow","nasdaq")]
    breaks=[trends.get(k,{}).get("support_break") for k in ("sp500","dow","nasdaq")]
    all_stages=all(x is True for x in stages) if all(trends.get(k,{}).get("available") for k in ("sp500","dow","nasdaq")) else None
    all_breaks=all(x is True for x in breaks) if all(trends.get(k,{}).get("available") for k in ("sp500","dow","nasdaq")) else None
    criteria=[
      criterion("Divergence NYSE A/D / Dow Jones supérieure à 3 mois",None,ad.get("detail"),2),
      criterion("NYSE A/D inscrit un nouveau plus bas après le rebond",None,ad.get("detail"),1),
      criterion("MM30 semaines descendante et cours sous MM30 sur les 3 indices",all_stages,f"{sum(x is True for x in stages)}/3 indices en phase 4.",2),
      criterion("Les 3 indices cassent leur support hebdomadaire",all_breaks,"Cassure confirmée sur deux clôtures hebdomadaires sous les supports calculés sur les 26 semaines antérieures.",2)
    ]
    if macro:
      criteria += [
        criterion("Inversion persistante 10 ans–2 ans / risque 12–18 mois",macro["yield_curve"].get("watch"),macro["yield_curve"].get("detail","Historique indisponible.")+" Écart quotidien : "+f"{macro['yield_spread']:.2f} point.",1),
        criterion("Inscriptions au chômage en hausse",macro["claims_rising"],f"Moyenne 4 semaines {macro['claims_4w_avg']:,.0f} vs 13 semaines {macro['claims_13w_avg']:,.0f}.",1),
        criterion("Taux de charge-offs bancaires en hausse",macro["chargeoffs_rising"],f"Dernier taux : {macro['chargeoff_latest']:.2f} % ({macro['chargeoff_date']}).",1),
        criterion("Inflation élevée et taux directeurs restrictifs",macro["inflation_restrictive"],f"CPI 12 mois : {macro['cpi_yoy']:.2f} % ; Fed Funds : {macro['fed_funds']:.2f} %." if macro.get("cpi_yoy") is not None else "Données CPI insuffisantes.",1)]
    else:
      criteria += [criterion(n,None,"Séries FRED indisponibles.",1) for n in ["Courbe des taux 10 ans – 2 ans inversée","Inscriptions au chômage en hausse","Taux de charge-offs bancaires en hausse","Inflation élevée et taux directeurs restrictifs"]]
    score=sum(x["weight"] for x in criteria if x["status"]=="yes"); coverage=sum(x["status"]!="unknown" for x in criteria)\n    freshness=freshness_check(indices,macro)
    all_market=all(trends.get(k,{}).get("available") for k in ("sp500","dow","nasdaq"))
    if not freshness["all_fresh"] or not all_market or coverage<5:
      status="UNKNOWN"; explanation="Données absentes ou périmées : verdict suspendu. Ne pas interpréter comme rassurant."
    elif all_stages is True and all_breaks is True:
      status="EXIT"; explanation="Confirmation technique forte : les trois indices sont sous leurs MM30 semaines descendantes et ont confirmé la cassure de supports. Signal à examiner, pas un ordre automatique."
    elif score>=4 or sum(x is True for x in stages)>=2 or sum(x is True for x in breaks)>=2:
      status="CAUTION"; explanation="Risque en hausse : plusieurs signaux se dégradent. Vigilance renforcée."
    elif ad.get("available") is not True:
      status="CAUTION"; explanation="Aucun signal technique majeur détecté dans les données disponibles, mais la NYSE A/D manque : le système ne peut pas certifier un état vert."
    else:
      status="HOLD"; explanation="Données fraîches et critères disponibles : aucun signal de sortie détecté. Cela ne garantit pas l'absence de baisse."
    data={"generated_at":now,"verdict":{"status":status,"score":score,"max_score":sum(x["weight"] for x in criteria),"coverage":coverage,"explanation":explanation},
      "indices":indices,"trends":trends,"macro":macro,"ad":ad,"ad_sp500":ad_sp500,"criteria":criteria,"sources":sources,
      "health":{"stale":bool(errors or not freshness["all_fresh"]),"freshness":freshness,"errors":errors,"notes":[
       "La ligne NYSE A/D exacte ($ADLINENYA) n'est pas connectée. Le proxy S&P 500 DeanFi est affiché séparément et ne remplace pas la série NYSE.",
       "La cassure est testée sur deux clôtures hebdomadaires sous le plus bas des 26 semaines précédentes.",
       "La phase 4 correspond à une clôture sous MM30 semaines avec MM30 descendante sur 4 semaines.",
       "Les seuils de chômage, charge-offs et inflation sont des règles indicatives ajoutées au modèle, pas des seuils officiels BlogBourse.",
       "La courbe des taux est suivie par T10Y2Y; inversion confirmée après 3 moyennes mensuelles négatives. La fenêtre 12–18 mois est un repère historique, pas une prévision certaine.",
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
