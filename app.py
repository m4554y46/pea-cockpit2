from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
from datetime import datetime
import re
import requests
import time
import json

app = Flask(__name__)
CORS(app)

# Base de données manuelle de dividendes pour les valeurs françaises courantes (fallback)
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
    'CD8': {'annual': 2.10, 'exDate': '2025-05-15'},
    'SEL': {'annual': 1.85, 'exDate': '2025-05-15'},
    'CW8': {'annual': 0.00, 'exDate': None},
    'PSP5': {'annual': 0.00, 'exDate': None},
    'WPEA': {'annual': 0.00, 'exDate': None},
    'PANX': {'annual': 0.00, 'exDate': None},
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

def fetch_dividends_from_yahoo(ticker):
    """Appelle directement l'API Yahoo Finance pour obtenir dividendes et cours"""
    suffixes = ['.PA', '.AS', '.DE', '.MI', '.MC', '']
    for suffix in suffixes:
        symbol = ticker + suffix
        # URL pour les infos de dividende
        url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules=summaryDetail,price"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            data = resp.json()
            summary = data.get('quoteSummary', {}).get('result', [{}])[0]
            if summary:
                sd = summary.get('summaryDetail', {})
                price_info = summary.get('price', {})
                annual_div = sd.get('trailingAnnualDividendRate', {}).get('raw', 0)
                ex_date_raw = sd.get('exDividendDate', {}).get('raw')
                ex_date = datetime.fromtimestamp(ex_date_raw).strftime('%Y-%m-%d') if ex_date_raw else None
                current_price = price_info.get('regularMarketPrice', {}).get('raw', 0)
                if not current_price:
                    current_price = price_info.get('regularMarketOpen', {}).get('raw', 0)
                change = price_info.get('regularMarketChangePercent', {}).get('raw', 0) / 100
                beta = sd.get('beta', {}).get('raw', None)
                pe = sd.get('trailingPE', {}).get('raw', None)
                if annual_div > 0 or current_price > 0:
                    return {
                        'cours': current_price,
                        'var': change,
                        'annualDiv': annual_div,
                        'exDivDate': ex_date,
                        'beta': beta,
                        'trailingPE': pe,
                        'divYield': annual_div / current_price if current_price else 0
                    }
        except Exception as e:
            print(f"Erreur Yahoo pour {symbol}: {e}")
            continue
    return None

def get_stock_data(ticker):
    # 1. Essayer Yahoo direct
    data = fetch_dividends_from_yahoo(ticker)
    if data and data['cours'] > 0:
        return data
    # 2. Fallback sur la base manuelle pour les dividendes (mais cours via Yahoo simple)
    # Récupérer le cours minimum via Yahoo quote
    try:
        quote_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}.PA"
        resp = requests.get(quote_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        quote = resp.json().get('quoteResponse', {}).get('result', [{}])[0]
        price = quote.get('regularMarketPrice', 0)
        prev_close = quote.get('regularMarketPreviousClose', price)
        change = (price - prev_close) / prev_close if prev_close else 0
    except:
        price = 0
        change = 0
    # Fallback dividendes
    div_info = DIVIDEND_FALLBACK.get(ticker, {'annual': 0, 'exDate': None})
    return {
        'cours': price,
        'var': change,
        'annualDiv': div_info['annual'],
        'exDivDate': div_info['exDate'],
        'beta': None,
        'trailingPE': None,
        'divYield': div_info['annual'] / price if price else 0
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

    # Nettoyer les noms de colonnes
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
    for p in portfolio:
        data = get_stock_data(p['ticker'])
        if data and data['cours'] > 0:
            cours = data['cours']
            valeur = p['qty'] * cours
            pv = valeur - p['qty'] * p['pru']
            pvpct = pv / (p['qty'] * p['pru']) if p['qty'] * p['pru'] else 0
            enriched.append({
                **p,
                'cours': cours,
                'var': data['var'],
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
            # Si pas de cours, on garde les valeurs initiales
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
        time.sleep(0.2)  # pour ne pas surcharger l'API

    return jsonify({'success': True, 'portfolio': enriched})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
