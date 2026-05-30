from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
from datetime import datetime
import re
import requests
import time

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('public', filename)

def extract_ticker(libelle):
    match = re.search(r'\(([A-Z0-9]{2,6})\)', libelle)
    if match:
        return match.group(1)
    words = re.split(r'[\s,\(\)]+', libelle)
    for w in words:
        if 2 <= len(w) <= 5 and w.isupper():
            return w
    return libelle.split()[0][:5].upper()

def get_yahoo_data(ticker):
    """Appelle Yahoo Finance pour obtenir cours, dividende annuel, date ex-dividend, beta, PER."""
    suffixes = ['.PA', '.AS', '.DE', '.MI', '.MC', '']
    for suffix in suffixes:
        symbol = ticker + suffix
        # URL pour les infos de dividende
        url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules=summaryDetail,price"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            data = resp.json()
            res = data.get('quoteSummary', {}).get('result')
            if not res:
                continue
            sd = res[0].get('summaryDetail', {})
            price_info = res[0].get('price', {})
            price = price_info.get('regularMarketPrice', {}).get('raw')
            if not price:
                price = price_info.get('regularMarketOpen', {}).get('raw')
            prev_close = price_info.get('regularMarketPreviousClose', {}).get('raw', price)
            change = (price - prev_close) / prev_close if prev_close and price else 0
            annual_div = sd.get('trailingAnnualDividendRate', {}).get('raw', 0)
            ex_div_raw = sd.get('exDividendDate', {}).get('raw')
            ex_div_date = datetime.fromtimestamp(ex_div_raw).strftime('%Y-%m-%d') if ex_div_raw else None
            beta = sd.get('beta', {}).get('raw')
            pe = sd.get('trailingPE', {}).get('raw')
            return {
                'cours': price,
                'var': change,
                'annualDiv': annual_div,
                'exDivDate': ex_div_date,
                'beta': beta,
                'trailingPE': pe,
                'divYield': annual_div / price if price else 0
            }
        except Exception as e:
            print(f"Erreur pour {symbol}: {e}")
            continue
    # Fallback : cours via une autre endpoint (quote) si besoin
    try:
        qurl = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}.PA"
        qresp = requests.get(qurl, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        qdata = qresp.json()
        quote = qdata.get('quoteResponse', {}).get('result', [{}])[0]
        price = quote.get('regularMarketPrice', 0)
        prev_close = quote.get('regularMarketPreviousClose', price)
        change = (price - prev_close) / prev_close if prev_close else 0
        return {
            'cours': price,
            'var': change,
            'annualDiv': 0,
            'exDivDate': None,
            'beta': None,
            'trailingPE': None,
            'divYield': 0
        }
    except:
        return None

def detect_sector(name, ticker):
    low = (name + ' ' + ticker).lower()
    if 'etf' in low or 'tracker' in low or 'amundi' in low:
        return 'ETF'
    if any(x in low for x in ['bnp', 'credit', 'axa', 'societe']):
        return 'Finance'
    if any(x in low for x in ['total', 'engie', 'rubis']):
        return 'Énergie'
    if any(x in low for x in ['renault', 'stellantis', 'alstom']):
        return 'Auto/Transport'
    if any(x in low for x in ['sanofi', 'essilor', 'gensight']):
        return 'Santé'
    if any(x in low for x in ['lvmh', 'kering', 'hermes']):
        return 'Luxe'
    return 'Autre'

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'excel' not in request.files:
        return jsonify({'error': 'Aucun fichier'}), 400

    file = request.files['excel']
    try:
        filename = file.filename
        if filename.lower().endswith('.xls'):
            df = pd.read_excel(file, engine='xlrd', dtype=str)
        else:
            df = pd.read_excel(file, engine='openpyxl', dtype=str)
    except Exception as e:
        return jsonify({'error': f'Erreur lecture Excel: {e}'}), 400

    df.columns = df.columns.str.strip().str.replace('\n', ' ')
    cols_lower = {k.lower(): k for k in df.columns}

    libelle_col = None
    for candidate in ['libellé', 'libelle', 'titre', 'nom', 'designation', 'instrument']:
        if candidate in cols_lower:
            libelle_col = cols_lower[candidate]
            break
    if not libelle_col:
        return jsonify({'error': f'Colonne "Libellé" introuvable. Colonnes: {list(df.columns)}'}), 400

    cours_col = cols_lower.get('cours') or cols_lower.get('prix')
    qty_col = cols_lower.get('qté') or cols_lower.get('qte') or cols_lower.get('quantité')
    pru_col = cols_lower.get('pru') or cols_lower.get('prix revient')

    portfolio = []
    for _, row in df.iterrows():
        libelle = row[libelle_col]
        if pd.isna(libelle):
            continue
        ticker = extract_ticker(str(libelle))
        if not ticker:
            continue

        qty = 0.0
        if qty_col and not pd.isna(row[qty_col]):
            try:
                qty = float(row[qty_col])
            except:
                pass
        pru = 0.0
        if pru_col and not pd.isna(row[pru_col]):
            try:
                pru = float(row[pru_col])
            except:
                pass
        cours_initial = 0.0
        if cours_col and not pd.isna(row[cours_col]):
            try:
                cours_initial = float(row[cours_col])
            except:
                pass

        portfolio.append({
            'name': str(libelle),
            'ticker': ticker,
            'qty': qty,
            'pru': pru,
            'cours_initial': cours_initial,
            'etf': 'etf' in str(libelle).lower()
        })

    if not portfolio:
        return jsonify({'error': 'Aucune ligne valide (ticker manquant)'}), 400

    enriched = []
    total = len(portfolio)
    for i, p in enumerate(portfolio):
        data = get_yahoo_data(p['ticker'])
        if data:
            cours = data['cours'] if data['cours'] > 0 else p['cours_initial']
            var = data['var']
            valeur = p['qty'] * cours
            pv = valeur - p['qty'] * p['pru']
            pvpct = pv / (p['qty'] * p['pru']) if p['qty'] * p['pru'] else 0
            enriched.append({
                **p,
                'cours': cours,
                'var': var,
                'valeur': valeur,
                'pv': pv,
                'pvpct': pvpct,
                'annualDiv': data['annualDiv'],
                'exDivDate': data['exDivDate'],
                'expectedDivAmount': p['qty'] * data['annualDiv'],
                'divYield': data['divYield'],
                'beta': data['beta'],
                'trailingPE': data['trailingPE'],
                'sector': detect_sector(p['name'], p['ticker'])
            })
        else:
            # Aucune donnée, on garde les valeurs initiales
            valeur = p['cours_initial'] * p['qty']
            enriched.append({
                **p,
                'cours': p['cours_initial'],
                'var': 0,
                'valeur': valeur,
                'pv': valeur - p['qty'] * p['pru'],
                'pvpct': (valeur - p['qty'] * p['pru']) / (p['qty'] * p['pru']) if p['qty'] * p['pru'] else 0,
                'annualDiv': 0,
                'exDivDate': None,
                'expectedDivAmount': 0,
                'divYield': 0,
                'beta': None,
                'trailingPE': None,
                'sector': detect_sector(p['name'], p['ticker'])
            })
        if (i+1) % 5 == 0:
            print(f"Traitement: {i+1}/{total} titres")
        time.sleep(0.1)  # respect des limites de l'API

    return jsonify({'success': True, 'portfolio': enriched})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
