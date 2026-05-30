import yfinance as yf
import json
import time

# Ta liste de tickers
tickers = ["AIR.PA", "TTE.PA", "RNO.PA"] # ... ajoute tes 60 tickers ici

results = {}

for ticker in tickers:
    try:
        t = yf.Ticker(ticker)
        # On récupère le dernier dividende
        last_div = t.dividends.iloc[-1]
        results[ticker] = float(last_div)
        print(f"Scraped {ticker}")
        time.sleep(1) # Pause courte pour ne pas spammer
    except Exception as e:
        print(f"Erreur sur {ticker}: {e}")
        results[ticker] = None

# Sauvegarde dans un fichier json à la racine
with open('data.json', 'w') as f:
    json.dump(results, f, indent=4)
