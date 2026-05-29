from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import yfinance as yf
import pandas as pd
from datetime import datetime
import re
import os

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

def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker + '.PA')
        info = stock.info
        price = info.get('regularMarketPrice') or info.get('currentPrice') or 0
        prev_close = info.get('regularMarketPreviousClose') or info.get('previousClose') or price
        change = (price - prev_close) / prev_close if prev_close else 0
        annual_div = info.get('trailingAnnualDividendRate') or 0
        ex_div_ts = info.get('exDividendDate')
        ex_div_date = datetime.fromtimestamp(ex_div_ts).strftime('%Y-%m-%d') if ex_div_ts else None
        beta = info.get('beta')
        pe = info.get('trailingPE')
        return {
            'cours': price, 'var': change, 'annualDiv': annual_div, 'exDivDate': ex_div_date,
            'beta': beta, 'trailingPE': pe, 'divYield': annual_div / price if price else 0
        }
    except Exception as e:
        print(f"Erreur {ticker}: {e}")
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
        # Lire tout le fichier sans en-tête, pour inspecter les lignes
        filename = file.filename
        if filename.lower().endswith('.xls'):
            df_raw = pd.read_excel(file, header=None, engine='xlrd')
        else:
            df_raw = pd.read_excel(file, header=None, engine='openpyxl')
    except Exception as e:
        return jsonify({'error': f'Erreur lecture Excel: {e}'}), 400

    # Rechercher la ligne contenant les mots-clés (sur les 20 premières lignes)
    header_row = None
    for idx in range(min(20, len(df_raw))):
        row = df_raw.iloc[idx].astype(str).str.lower()
        if any(term in row.values for term in ['libellé', 'libelle', 'titre', 'nom']):
            header_row = idx
            break

    if header_row is None:
        return jsonify({'error': 'Impossible de trouver la ligne d\'en-tête (contenant "Libellé")'}), 400

    # Re-lire le fichier avec la bonne ligne d'en-tête
    file.seek(0)  # remettre le pointeur au début
    if filename.lower().endswith('.xls'):
        df = pd.read_excel(file, header=header_row, engine='xlrd', dtype=str)
    else:
        df = pd.read_excel(file, header=header_row, engine='openpyxl', dtype=str)

    # Nettoyer les noms de colonnes (supprimer espaces, \n)
    df.columns = df.columns.str.strip().str.replace('\n', ' ')

    print("Colonnes détectées :", list(df.columns))

    # Détection colonne libellé (insensible, avec plusieurs synonymes)
    libelle_col = None
    for col in df.columns:
        col_low = col.lower()
        if any(term in col_low for term in ['libellé', 'libelle', 'titre', 'nom', 'designation', 'instrument', 'valeur']):
            libelle_col = col
            break

    if not libelle_col:
        return jsonify({'error': f'Colonne "Libellé" introuvable. Colonnes trouvées : {list(df.columns)}'}), 400

    cols_lower = {k.lower(): k for k in df.columns}
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
        if data:
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

    return jsonify({'success': True, 'portfolio': enriched})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
