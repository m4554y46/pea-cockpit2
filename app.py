from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
from datetime import datetime
import re
import requests
import time

app = Flask(__name__)
CORS(app)

# Base de données manuelle de dividendes (pour les valeurs courantes)
DIVIDEND_FALLBACK = {
    'TTE': {'annual': 3.40, 'exDate': '2025-06-10'},
    'BNP': {'annual': 4.60, 'exDate': '2025-05-20'},
    'SAN': {'annual': 3.56, 'exDate': '2025-05-12'},
    'MC': {'annual': 13.00, 'exDate': '2025-12-02'},
    'AI': {'annual': 3.20, 'exDate': '2025-11-18'},
    'OR': {'annual': 2.20, 'exDate': '2025-06-03'},
    'SU': {'annual': 3.50, 'exDate': '2025-06-04'},
    'ACA': {'annual': 2.10, 'exDate': '2025-05-22'},
    'GLE': {'annual': 2.15, 'exDate': '2025-05-22'},
    'RNO': {'annual': 1.20, 'exDate': '2025-06-05'},
    'STLAP': {'annual': 1.55, 'exDate': '2025-04-23'},
    'ENGI': {'annual': 1.65, 'exDate': '2025-06-02'},
    'CAP': {'annual': 3.30, 'exDate': '2025-05-29'},
    'DSY': {'annual': 1.80, 'exDate': '2025-06-12'},
    'SAF': {'annual': 2.60, 'exDate': '2025-05-27'},
    'AIR': {'annual': 1.80, 'exDate': '2025-06-04'},
    'ORAN': {'annual': 0.72, 'exDate': '2025-06-03'},
    'CS': {'annual': 1.80, 'exDate': '2025-05-15'},
    'EN': {'annual': 1.40, 'exDate': '2025-06-20'},
    'FR': {'annual': 0.00, 'exDate': None},
    'RUI': {'annual': 2.50, 'exDate': '2025-07-01'},
    'AMUN': {'annual': 5.20, 'exDate': '2025-05-30'},
    'SCR': {'annual': 1.20, 'exDate': '2025-06-15'},
    'SEL': {'annual': 1.85, 'exDate': '2025-05-15'},
    'CD8': {'annual': 2.10, 'exDate': '2025-05-15'},
    'CW8': {'annual': 0.00, 'exDate': None},
    'PSP5': {'annual': 0.00, 'exDate': None},
    'WPEA': {'annual': 0.00, 'exDate': None},
    'PANX': {'annual': 0.00, 'exDate': None},
    'HLT': {'annual': 0.00, 'exDate': None},
    'PMEH': {'annual': 0.00, 'exDate': None},
    'BOL': {'annual': 0.00, 'exDate': None},
    'CA': {'annual': 0.00, 'exDate': None},
    'CO': {'annual': 0.00, 'exDate': None},
    'ALATI': {'annual': 0.00, 'exDate': None},
    'ALO': {'annual': 0.00, 'exDate': None},
    'ALJXR': {'annual': 0.00, 'exDate': None},
    'ARDS': {'annual': 0.00, 'exDate': None},
    'AVT': {'annual': 0.00, 'exDate': None},
    'ELIOR': {'annual': 0.00, 'exDate': None},
    'ETL': {'annual': 0.00, 'exDate': None},
    'FDJU': {'annual': 0.00, 'exDate': None},
    'FNAC': {'annual': 0.00, 'exDate': None},
    'FRVIA': {'annual': 0.00, 'exDate': None},
    'HAG': {'annual': 0.00, 'exDate': None},
    'ALHRS': {'annual': 0.00, 'exDate': None},
    'NK': {'annual': 0.00, 'exDate': None},
    'ALINN': {'annual': 0.00, 'exDate': None},
    'INPST': {'annual': 0.00, 'exDate': None},
    'DEC': {'annual': 0.00, 'exDate': None},
    'NXI': {'annual': 0.00, 'exDate': None},
    'OPM': {'annual': 0.00, 'exDate': None},
    'SIGHT': {'annual': 0.00, 'exDate': None},
    'TEP': {'annual': 0.00, 'exDate': None},
    'TFI': {'annual': 0.00, 'exDate': None},
    'ALWIT': {'annual': 0.00, 'exDate': None},
    'WLN': {'annual': 0.00, 'exDate': None},
    'ALECP': {'annual': 0.00, 'exDate': None},
    'FGR': {'annual': 0.00, 'exDate': None},
    'SEFER': {'annual': 0.00, 'exDate': None},
    'ALWIN': {'annual': 0.00, 'exDate': None},
    'SAOT': {'annual': 0.00, 'exDate': None},
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

def fetch_yahoo_quote(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}.PA"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=5)
        data = resp.json()
        quote = data.get('quoteResponse', {}).get('result', [{}])[0]
        price = quote.get('regularMarketPrice', 0)
        prev_close = quote.get('regularMarketPreviousClose', price)
        change = (price - prev_close) / prev_close if prev_close else 0
        return {'cours': price, 'var': change}
    except Exception as e:
        print(f"Erreur Yahoo pour {ticker}: {e}")
        return None

def get_stock_data(ticker):
    quote = fetch_yahoo_quote(ticker)
    cours = quote['cours'] if quote else 0
    var = quote['var'] if quote else 0
    div_info = DIVIDEND_FALLBACK.get(ticker, {'annual': 0, 'exDate': None})
    return {
        'cours': cours,
        'var': var,
        'annualDiv': div_info['annual'],
        'exDivDate': div_info['exDate'],
        'beta': None,
        'trailingPE': None,
        'divYield': div_info['annual'] / cours if cours else 0
    }

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
        data = get_stock_data(p['ticker'])
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
        if (i+1) % 10 == 0:
            print(f"Traitement: {i+1}/{total} titres")
        time.sleep(0.05)

    return jsonify({'success': True, 'portfolio': enriched})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
