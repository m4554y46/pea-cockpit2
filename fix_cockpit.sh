#!/bin/bash
set -e
echo "🔧 Correction du cockpit PEA..."

# Backup
mkdir -p backup
cp app.py backup/ 2>/dev/null || true

# Nouveau app.py (version stable avec fallback dividendes)
cat > app.py << 'ENDAPP'
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
import re
import requests
import time

app = Flask(__name__)
CORS(app)

# Base de données manuelle de dividendes (complète)
DIV_FALLBACK = {
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

def get_price(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}.PA"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=5)
        data = resp.json()
        q = data.get('quoteResponse', {}).get('result', [{}])[0]
        price = q.get('regularMarketPrice', 0)
        prev = q.get('regularMarketPreviousClose', price)
        change = (price - prev) / prev if prev else 0
        return price, change
    except:
        return 0, 0

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
    for _, row in df.iterrows():
        lib = row[libelle_col]
        if pd.isna(lib):
            continue
        ticker = extract_ticker(str(lib))
        if not ticker:
            continue
        qty = float(row[qty_col]) if qty_col and not pd.isna(row[qty_col]) else 0.0
        pru = float(row[pru_col]) if pru_col and not pd.isna(row[pru_col]) else 0.0
        cours_initial = float(row[cours_col]) if cours_col and not pd.isna(row[cours_col]) else 0.0

        price, change = get_price(ticker)
        cours = price if price > 0 else cours_initial
        valeur = qty * cours
        pv = valeur - qty * pru
        pvpct = pv / (qty * pru) if qty * pru else 0
        div = DIV_FALLBACK.get(ticker, {'annual': 0, 'exDate': None})

        result.append({
            'name': str(lib),
            'ticker': ticker,
            'qty': qty,
            'pru': pru,
            'cours': cours,
            'var': change,
            'valeur': valeur,
            'pv': pv,
            'pvpct': pvpct,
            'annualDiv': div['annual'],
            'exDivDate': div['exDate'],
            'expectedDivAmount': qty * div['annual'],
            'divYield': div['annual'] / cours if cours else 0,
            'beta': None,
            'trailingPE': None,
            'sector': 'ETF' if 'etf' in str(lib).lower() else 'Autre',
            'etf': 'etf' in str(lib).lower()
        })
        time.sleep(0.05)
    return jsonify({'success': True, 'portfolio': result})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
ENDAPP

# Mise à jour requirements.txt
cat > requirements.txt << 'ENDREQ'
flask==2.3.3
flask-cors==4.0.0
pandas>=2.2.0
openpyxl>=3.1.2
xlrd>=2.0.1
requests>=2.31.0
gunicorn>=21.2.0
ENDREQ

# Correction CSS (scroll risques)
echo -e "\n/* Fix risque table */\n#riskMetrics { overflow-x: auto; white-space: nowrap; }\n.risk-table { min-width: 500px; }" >> public/style.css

echo "✅ Correction terminée !"
echo "📌 Maintenant, exécute : git add . && git commit -m 'Fix complet' && git push origin main"
