"""
PEA Cockpit — Backend Render (fallback)
Utilisé quand le proxy local n'est pas actif.
Render est parfois rate-limité par Yahoo → préférez proxy_local.py sur votre box.
"""
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests, time, re
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ── Correspondance ticker Bourse Direct → Yahoo Finance
TICKER_MAP = {
    "SEL":"C40.PA", "CD8":"EMVD.PA", "CW8":"CW8.PA", "PSP5":"PSP5.PA",
    "PANX":"PANX.PA", "WPEA":"WPEA.PA", "PMEH":"PMEH.PA", "HLT":"HLT.PA",
    "RS2K":"RS2K.PA", "TTE":"TTE.PA", "MC":"MC.PA", "OR":"OR.PA",
    "SAN":"SAN.PA", "BNP":"BNP.PA", "ACA":"ACA.PA", "AIR":"AIR.PA",
    "SAF":"SAF.PA", "RNO":"RNO.PA", "ORA":"ORA.PA", "RUI":"RUI.PA",
    "ML":"ML.PA", "RMS":"RMS.PA", "KER":"KER.PA",
}

DIV_FALLBACK = {
    "SEL": {"annual":1.92,"exDate":"2025-12-15","yield":0.081},
    "CD8": {"annual":2.20,"exDate":"2025-11-20","yield":0.011},
    "TTE": {"annual":3.22,"exDate":"2025-09-19","yield":0.041},
    "BNP": {"annual":4.60,"exDate":"2025-05-21","yield":0.063},
    "ACA": {"annual":1.76,"exDate":"2025-05-28","yield":0.068},
    "ORA": {"annual":0.72,"exDate":"2025-06-05","yield":0.055},
    "SAN": {"annual":3.92,"exDate":"2025-05-28","yield":0.044},
    "RNO": {"annual":1.85,"exDate":"2025-04-30","yield":0.046},
    "ML":  {"annual":1.49,"exDate":"2025-06-12","yield":0.063},
    "CW8":{"annual":0,"exDate":None,"yield":0},
    "PSP5":{"annual":0,"exDate":None,"yield":0},
    "PANX":{"annual":0,"exDate":None,"yield":0},
    "WPEA":{"annual":0,"exDate":None,"yield":0},
}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"

def resolve(ticker):
    return TICKER_MAP.get(ticker, f"{ticker}.PA")

def pf(d, *keys):
    for k in keys:
        if not isinstance(d, dict): return None
        d = d.get(k)
        if d is None: return None
    return d.get("raw", d) if isinstance(d, dict) else d

def fetch_one(ticker):
    sym = resolve(ticker)
    res = {"ticker": ticker, "symbol": sym, "cours":0, "var":0,
           "annualDiv":0, "divYield":0, "exDivDate":None, "payDate":None,
           "beta":None, "trailingPE":None, "forwardPE":None, "payoutRatio":None}

    # Prix via chart
    for host in ["query1","query2"]:
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}",
                params={"interval":"1d","range":"1d"},
                headers={"User-Agent":UA,"Referer":"https://finance.yahoo.com/"},timeout=8)
            if r.status_code==200:
                meta = r.json().get("chart",{}).get("result",[{}])[0].get("meta",{})
                if meta.get("regularMarketPrice",0)>0:
                    pr = meta["regularMarketPrice"]
                    prev = meta.get("previousClose") or meta.get("chartPreviousClose") or pr
                    res["cours"] = pr
                    res["var"] = (pr-prev)/prev if prev else 0
                    break
        except: pass

    # quoteSummary pour dividendes + ratios
    modules = "summaryDetail,calendarEvents,defaultKeyStatistics"
    for host in ["query1","query2"]:
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v10/finance/quoteSummary/{sym}",
                params={"modules":modules,"formatted":"false"},
                headers={"User-Agent":UA,"Referer":"https://finance.yahoo.com/"},timeout=10)
            if r.status_code!=200: continue
            q = r.json().get("quoteSummary",{}).get("result",[])
            if not q: continue
            q = q[0]
            sd = q.get("summaryDetail",{}); ce = q.get("calendarEvents",{}); ks = q.get("defaultKeyStatistics",{})
            res["annualDiv"] = pf(sd,"trailingAnnualDividendRate") or pf(sd,"dividendRate") or 0
            res["divYield"]  = pf(sd,"trailingAnnualDividendYield") or pf(sd,"dividendYield") or 0
            ex_ts = pf(ce,"exDividendDate") or pf(sd,"exDividendDate")
            if isinstance(ex_ts,(int,float)) and ex_ts>0:
                res["exDivDate"] = datetime.utcfromtimestamp(ex_ts).strftime("%Y-%m-%d")
            pay_ts = pf(ce,"dividendDate")
            if isinstance(pay_ts,(int,float)) and pay_ts>0:
                res["payDate"] = datetime.utcfromtimestamp(pay_ts).strftime("%Y-%m-%d")
            res["beta"]       = pf(ks,"beta") or pf(sd,"beta")
            res["trailingPE"] = pf(ks,"trailingPE") or pf(sd,"trailingPE")
            res["forwardPE"]  = pf(ks,"forwardPE") or pf(sd,"forwardPE")
            res["payoutRatio"]= pf(sd,"payoutRatio") or pf(ks,"payoutRatio")
            res["fiftyTwoWeekHigh"] = pf(sd,"fiftyTwoWeekHigh")
            res["fiftyTwoWeekLow"]  = pf(sd,"fiftyTwoWeekLow")
            break
        except: pass

    # Fallback dividendes manuels
    fb = DIV_FALLBACK.get(ticker,{})
    if fb.get("annual",0)>0 and res["annualDiv"]==0: res["annualDiv"]=fb["annual"]
    if fb.get("exDate") and not res["exDivDate"]: res["exDivDate"]=fb["exDate"]
    if fb.get("yield",0)>0 and res["divYield"]==0: res["divYield"]=fb["yield"]
    if res["divYield"]==0 and res["annualDiv"]>0 and res["cours"]>0:
        res["divYield"] = res["annualDiv"]/res["cours"]

    return res

@app.route("/")
def index():
    return send_from_directory("public","index.html")

@app.route("/<path:f>")
def static_files(f):
    return send_from_directory("public",f)

@app.route("/ping")
def ping():
    return jsonify({"status":"ok","source":"render","ts":datetime.now().isoformat()})

@app.route("/quotes", methods=["POST"])
def quotes():
    tickers = (request.get_json(force=True) or {}).get("tickers",[])
    if not tickers:
        return jsonify({"error":"tickers vide"}),400
    results = {}
    for i,t in enumerate(tickers):
        t=t.upper().strip()
        try: results[t]=fetch_one(t)
        except Exception as e: results[t]={"error":str(e),"ticker":t}
        time.sleep(0.35)
        if (i+1)%5==0: time.sleep(0.8)
    return jsonify({"success":True,"data":results,"count":len(results)})

@app.route("/quote")
def quote():
    t = request.args.get("ticker","").upper().strip()
    if not t: return jsonify({"error":"ticker requis"}),400
    return jsonify(fetch_one(t))

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)
