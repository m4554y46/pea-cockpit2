#!/usr/bin/env python3
"""
PEA Cockpit — Proxy Local Yahoo Finance
Tournez ce script sur votre machine personnelle (pas Render).
Votre IP de box internet n'est jamais blacklistée par Yahoo.

Usage:
  pip install flask flask-cors requests yfinance
  python proxy_local.py

Puis dans le cockpit HTML, cliquez "Connecter proxy local".
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import json
import time
import re
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app, origins=["*"])

# ── User-Agent pool : rotation pour éviter les 429
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]
_ua_idx = 0

def next_ua():
    global _ua_idx
    ua = UA_POOL[_ua_idx % len(UA_POOL)]
    _ua_idx += 1
    return ua

# ── Cache simple en mémoire (TTL 10 min pour éviter spam)
_cache = {}
def get_cached(key):
    if key in _cache:
        val, ts = _cache[key]
        if time.time() - ts < 600:
            return val
    return None

def set_cached(key, val):
    _cache[key] = (val, time.time())

# ── Table de correspondance tickers Bourse Direct → Yahoo Finance
# Les ETF Amundi/Lyxor ont souvent un ticker Yahoo différent du ticker BD
TICKER_MAP = {
    # ETF Amundi
    "SEL":   "C40.PA",    # Amundi Stoxx Europe Select Dividend 30
    "CD8":   "EMVD.PA",   # Amundi MSCI EMU High Dividend
    "CW8":   "CW8.PA",    # Amundi MSCI World
    "PSP5":  "PSP5.PA",   # Amundi PEA S&P 500
    "PANX":  "PANX.PA",   # Amundi PEA Nasdaq-100
    "WPEA":  "WPEA.PA",   # Amundi PEA World
    "PMEH":  "PMEH.PA",   # Amundi PEA EM
    "RS2K":  "RS2K.PA",   # Amundi Russell 2000
    "PAEEM": "PAEEM.PA",
    "PCEU":  "PCEU.PA",
    "HLT":   "HLT.PA",    # Amundi MSCI Health Care
    "DXET":  "DXET.PA",
    "LYLEM": "LYLEM.PA",
    # Actions françaises connues
    "TTE":   "TTE.PA",
    "MC":    "MC.PA",
    "OR":    "OR.PA",
    "SAN":   "SAN.PA",
    "BNP":   "BNP.PA",
    "ACA":   "ACA.PA",
    "CS":    "CS.PA",
    "AIR":   "AIR.PA",
    "SAF":   "SAF.PA",
    "DG":    "DG.PA",
    "RI":    "RI.PA",
    "EI":    "EI.PA",
    "ORA":   "ORA.PA",
    "EN":    "EN.PA",
    "RNO":   "RNO.PA",
    "ERF":   "ERF.PA",
    "RMS":   "RMS.PA",
    "KER":   "KER.PA",
    "SGO":   "SGO.PA",
    "LR":    "LR.PA",
    "AXA":   "CS.PA",
    "FP":    "TTE.PA",    # ancien ticker TotalEnergies
    "ML":    "ML.PA",
    "RUBIS": "RUI.PA",
    "ABVX":  "ABVX.PA",
    "DBV":   "DBV.PA",
}

# ── Dividendes de fallback (mis à jour manuellement quand Yahoo échoue)
# Format: {'annual': float, 'exDate': 'YYYY-MM-DD', 'yield': float}
DIV_FALLBACK = {
    "SEL":   {"annual": 1.92, "exDate": "2025-12-15", "yield": 0.081},
    "CD8":   {"annual": 2.20, "exDate": "2025-11-20", "yield": 0.011},
    "TTE":   {"annual": 3.22, "exDate": "2025-09-19", "yield": 0.041},  # 4 versements/an
    "BNP":   {"annual": 4.60, "exDate": "2025-05-21", "yield": 0.063},
    "ACA":   {"annual": 1.76, "exDate": "2025-05-28", "yield": 0.068},
    "ORA":   {"annual": 0.72, "exDate": "2025-06-05", "yield": 0.055},
    "SAN":   {"annual": 3.92, "exDate": "2025-05-28", "yield": 0.044},
    "AXA":   {"annual": 2.04, "exDate": "2025-05-21", "yield": 0.056},
    "RNO":   {"annual": 1.85, "exDate": "2025-04-30", "yield": 0.046},
    "RUI":   {"annual": 2.04, "exDate": "2025-06-19", "yield": 0.052},
    "ML":    {"annual": 1.49, "exDate": "2025-06-12", "yield": 0.063},
    "CW8":   {"annual": 0.00, "exDate": None, "yield": 0.0},
    "PSP5":  {"annual": 0.00, "exDate": None, "yield": 0.0},
    "PANX":  {"annual": 0.00, "exDate": None, "yield": 0.0},
    "WPEA":  {"annual": 0.00, "exDate": None, "yield": 0.0},
    "PMEH":  {"annual": 0.00, "exDate": None, "yield": 0.0},
}


def resolve_symbol(ticker):
    """Résout le symbole Yahoo Finance depuis le ticker Bourse Direct."""
    if ticker in TICKER_MAP:
        return TICKER_MAP[ticker]
    # Essayer avec .PA d'abord, puis sans suffixe
    return f"{ticker}.PA"


def yahoo_fetch(symbol, modules="price,summaryDetail,defaultKeyStatistics,calendarEvents"):
    """Appel Yahoo Finance quoteSummary avec rotation UA + gestion 429."""
    cached = get_cached(f"qs:{symbol}")
    if cached:
        return cached

    for host in ["query1", "query2"]:
        url = f"https://{host}.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
        params = {"modules": modules, "corsDomain": "finance.yahoo.com", "formatted": "false"}
        headers = {
            "User-Agent": next_ua(),
            "Accept": "application/json",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Referer": "https://finance.yahoo.com/",
        }
        try:
            r = requests.get(url, params=params, headers=headers, timeout=10)
            if r.status_code == 429:
                time.sleep(2)
                continue
            if r.status_code != 200:
                continue
            data = r.json()
            result = data.get("quoteSummary", {}).get("result", [])
            if result:
                set_cached(f"qs:{symbol}", result[0])
                return result[0]
        except Exception as e:
            print(f"  [{host}] {symbol} erreur: {e}")
            continue
    return None


def parse_field(obj, *keys, default=None):
    """Navigation sécurisée dans un dict imbriqué."""
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
        if cur is None:
            return default
    if isinstance(cur, dict) and "raw" in cur:
        return cur["raw"]
    return cur


def enrich_ticker(ticker):
    """Récupère cours + dividendes + ratios pour un ticker."""
    symbol = resolve_symbol(ticker)
    print(f"  Fetching {ticker} → {symbol}")

    result = {}

    # ── 1. Cours via /v8/finance/chart (plus fiable pour le prix)
    chart_cached = get_cached(f"chart:{symbol}")
    if not chart_cached:
        for host in ["query1", "query2"]:
            try:
                url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}"
                r = requests.get(url, params={"interval":"1d","range":"1d"},
                                 headers={"User-Agent": next_ua(), "Referer": "https://finance.yahoo.com/"},
                                 timeout=8)
                if r.status_code == 200:
                    meta = r.json().get("chart", {}).get("result", [{}])[0].get("meta", {})
                    if meta.get("regularMarketPrice"):
                        chart_cached = meta
                        set_cached(f"chart:{symbol}", meta)
                        break
            except:
                pass

    if chart_cached:
        price = chart_cached.get("regularMarketPrice", 0)
        prev  = chart_cached.get("previousClose") or chart_cached.get("chartPreviousClose") or price
        result["cours"] = price
        result["var"]   = (price - prev) / prev if prev else 0
        result["currency"] = chart_cached.get("currency", "EUR")
    else:
        result["cours"] = 0
        result["var"]   = 0

    # ── 2. Dividendes + ratios via quoteSummary
    qs = yahoo_fetch(symbol)
    if qs:
        sd = qs.get("summaryDetail", {})
        ce = qs.get("calendarEvents", {})
        ks = qs.get("defaultKeyStatistics", {})
        fd = qs.get("financialData", {})

        # Dividende annuel : cascade de fallbacks
        annual_div = (parse_field(sd, "trailingAnnualDividendRate")
                   or parse_field(sd, "dividendRate")
                   or parse_field(fd, "dividendRate")
                   or 0)

        div_yield = (parse_field(sd, "trailingAnnualDividendYield")
                  or parse_field(sd, "dividendYield")
                  or parse_field(fd, "dividendYield")
                  or 0)

        # Date ex-dividende : timestamp Unix → date
        ex_ts = parse_field(ce, "exDividendDate") or parse_field(sd, "exDividendDate")
        if isinstance(ex_ts, (int, float)) and ex_ts > 0:
            ex_date = datetime.utcfromtimestamp(ex_ts).strftime("%Y-%m-%d")
        elif isinstance(ex_ts, str) and len(ex_ts) >= 8:
            ex_date = ex_ts[:10]
        else:
            ex_date = None

        pay_ts = parse_field(ce, "dividendDate")
        pay_date = datetime.utcfromtimestamp(pay_ts).strftime("%Y-%m-%d") if isinstance(pay_ts, (int, float)) and pay_ts > 0 else None

        result["annualDiv"]    = annual_div
        result["divYield"]     = div_yield if div_yield > 0 else (annual_div / result["cours"] if result["cours"] > 0 else 0)
        result["exDivDate"]    = ex_date
        result["payDate"]      = pay_date
        result["beta"]         = parse_field(ks, "beta") or parse_field(sd, "beta")
        result["trailingPE"]   = parse_field(ks, "trailingPE") or parse_field(sd, "trailingPE")
        result["forwardPE"]    = parse_field(ks, "forwardPE") or parse_field(sd, "forwardPE")
        result["payoutRatio"]  = parse_field(sd, "payoutRatio") or parse_field(ks, "payoutRatio")
        result["marketCap"]    = parse_field(sd, "marketCap")
        result["fiftyTwoWeekHigh"] = parse_field(sd, "fiftyTwoWeekHigh")
        result["fiftyTwoWeekLow"]  = parse_field(sd, "fiftyTwoWeekLow")
        result["averageVolume"]    = parse_field(sd, "averageVolume")
    else:
        result.update({"annualDiv":0,"divYield":0,"exDivDate":None,"payDate":None,
                       "beta":None,"trailingPE":None,"forwardPE":None,"payoutRatio":None,
                       "marketCap":None,"fiftyTwoWeekHigh":None,"fiftyTwoWeekLow":None,"averageVolume":None})

    # ── 3. Fallback manuel dividendes si Yahoo n'a rien
    fb = DIV_FALLBACK.get(ticker)
    if fb and (result["annualDiv"] == 0 or result["exDivDate"] is None):
        if fb["annual"] > 0 and result["annualDiv"] == 0:
            result["annualDiv"] = fb["annual"]
        if fb["exDate"] and not result["exDivDate"]:
            result["exDivDate"] = fb["exDate"]
        if fb["yield"] > 0 and result["divYield"] == 0:
            result["divYield"] = fb["yield"]

    result["ticker"] = ticker
    result["symbol"] = symbol
    return result


# ══════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════

@app.route("/ping")
def ping():
    return jsonify({"status": "ok", "ts": datetime.now().isoformat(), "version": "2.0"})


@app.route("/quote")
def quote_single():
    ticker = request.args.get("ticker", "").upper().strip()
    if not ticker:
        return jsonify({"error": "ticker requis"}), 400
    data = enrich_ticker(ticker)
    return jsonify(data)


@app.route("/quotes", methods=["POST"])
def quote_batch():
    """Endpoint batch : reçoit une liste de tickers, retourne toutes les données."""
    body = request.get_json(force=True) or {}
    tickers = body.get("tickers", [])
    if not tickers:
        return jsonify({"error": "liste tickers vide"}), 400

    print(f"\n=== Batch {len(tickers)} tickers ===")
    results = {}
    for i, t in enumerate(tickers):
        t = t.upper().strip()
        try:
            results[t] = enrich_ticker(t)
        except Exception as e:
            print(f"  ERREUR {t}: {e}")
            results[t] = {"error": str(e), "ticker": t}
        # Pause anti-rate-limit : 300ms entre chaque, 1s tous les 5
        time.sleep(0.3)
        if (i + 1) % 5 == 0:
            time.sleep(0.7)

    print(f"=== Batch terminé : {len(results)} résultats ===\n")
    return jsonify({"success": True, "data": results, "count": len(results)})


@app.route("/ticker_map")
def get_ticker_map():
    """Retourne la table de correspondance pour debug."""
    return jsonify(TICKER_MAP)


@app.route("/div_fallback")
def get_div_fallback():
    """Retourne les dividendes de fallback."""
    return jsonify(DIV_FALLBACK)


if __name__ == "__main__":
    print("=" * 55)
    print("  PEA Cockpit — Proxy Local Yahoo Finance v2.0")
    print("  Écoute sur http://localhost:5001")
    print("  Votre IP box = jamais blacklistée")
    print("=" * 55)
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
