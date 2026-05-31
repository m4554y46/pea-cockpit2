from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
import re
import requests
import time
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Fallback manuel pour les ETF et actions qui ne renvoient pas de dividendes via Yahoo
DIV_FALLBACK = {
    'SEL': {'annual': 1.85, 'exDate': '2025-05-15'},
    'CD8': {'annual': 2.10, 'exDate': '2025-05-15'},
    'CW8': {'annual': 0.00, 'exDate': None},
    'PSP5': {'annual': 0.00, 'exDate': None},
    'WPEA': {'annual': 0.00, 'exDate': None},
    'PANX': {'annual': 0.00, 'exDate': None},
    'HLT': {'annual': 0.00, 'exDate': None},
    'PMEH': {'annual': 0.00, 'exDate': None},
}

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

def fetch_yahoo_data(ticker):
    symbol = f"{ticker}.PA"
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules=price,summaryDetail,defaultKeyStatistics"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        data = resp.json()
        result = data.get('quoteSummary', {}).get('result', [{}])[0]
        if not result:
            return None
        price_info = result.get('price', {})
        price = price_info.get('regularMarketPrice', {}).get('raw', 0)
        prev_close = price_info.get('regularMarketPreviousClose', {}).get('raw', price)
        change = (price - prev_close) / prev_close if prev_close else 0
        summary = result.get('summaryDetail', {})
        annual_div = summary.get('trailingAnnualDividendRate', {}).get('raw', 0)
        ex_div_ts = summary.get('exDividendDate', {}).get('raw')
        ex_div_date = datetime.fromtimestamp(ex_div_ts).strftime('%Y-%m-%d') if ex_div_ts else None
        beta = summary.get('beta', {}).get('raw')
        pe = result.get('defaultKeyStatistics', {}).get('trailingPE', {}).get('raw')
        return {
            'cours': price,
            'var': change,
            'annualDiv': annual_div,
            'exDivDate': ex_div_date,
            'beta': beta,
            'trailingPE': pe,
            'divYield': annual_div / price if price else 0
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
    if any(x in low for x in ['renault', 'stellantis', 'valeo']):
        return 'Automobile'
    if any(x in low for x in ['sanofi', 'essilor']):
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
        if file.filename.lower().endswith('.xls'):
            df = pd.read_excel(file, engine='xlrd', dtype=str)
        else:
            df = pd.read_excel(file, engine='openpyxl', dtype=str)
    except Exception as e:
        return jsonify({'error': f'Erreur lecture: {e}'}), 400

    df.columns = df.columns.str.strip().str.replace('\n', ' ')
    cols_lower = {k.lower(): k for k in df.columns}
    libelle_col = None
    for cand in ['libellé', 'libelle', 'titre', 'nom']:
        if cand in cols_lower:
            libelle_col = cols_lower[cand]
            break
    if not libelle_col:
        return jsonify({'error': f'Libellé introuvable. Colonnes: {list(df.columns)}'}), 400

    cours_col = cols_lower.get('cours') or cols_lower.get('prix')
    qty_col = cols_lower.get('qté') or cols_lower.get('qte') or cols_lower.get('quantité')
    pru_col = cols_lower.get('pru') or cols_lower.get('prix revient')

    result = []
    total = len(df)
    for idx, row in df.iterrows():
        lib = row[libelle_col]
        if pd.isna(lib):
            continue
        ticker = extract_ticker(str(lib))
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

        data = fetch_yahoo_data(ticker)
        if data and data['cours'] > 0:
            cours = data['cours']
            var = data['var']
            annual_div = data['annualDiv']
            ex_date = data['exDivDate']
            beta = data['beta']
            pe = data['trailingPE']
            div_yield = data['divYield']
        else:
            cours = cours_initial
            var = 0
            annual_div = 0
            ex_date = None
            beta = None
            pe = None
            div_yield = 0

        # Fallback manuel
        if ticker in DIV_FALLBACK:
            annual_div = DIV_FALLBACK[ticker]['annual']
            ex_date = DIV_FALLBACK[ticker]['exDate']
            div_yield = annual_div / cours if cours else 0

        valeur = qty * cours
        pv = valeur - qty * pru
        pvpct = pv / (qty * pru) if qty * pru else 0

        result.append({
            'name': str(lib),
            'ticker': ticker,
            'qty': qty,
            'pru': pru,
            'cours': cours,
            'var': var,
            'valeur': valeur,
            'pv': pv,
            'pvpct': pvpct,
            'annualDiv': annual_div,
            'exDivDate': ex_date,
            'expectedDivAmount': qty * annual_div,
            'divYield': div_yield,
            'beta': beta,
            'trailingPE': pe,
            'sector': detect_sector(str(lib), ticker),
            'etf': 'etf' in str(lib).lower()
        })
        time.sleep(0.1)
        if (idx+1) % 5 == 0:
            print(f"Progression: {idx+1}/{total}")

    return jsonify({'success': True, 'portfolio': result})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
