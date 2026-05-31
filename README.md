# PEA Cockpit — Architecture & Installation

## Pourquoi un proxy local ?

Yahoo Finance **bloque les IPs de datacenters** (Render, Heroku, Vercel…).
Votre IP de box internet personnelle n'est jamais bloquée.

**Solution :** un micro-serveur Python (`proxy_local.py`) tourne sur votre machine.
Il relaie les appels Yahoo Finance depuis votre IP personnelle.
Le cockpit HTML l'interroge sur `http://localhost:5001`.

```
[ cockpit.html ] ──→ [ proxy_local.py :5001 ] ──→ [ Yahoo Finance ]
    (browser)           (votre machine)              (votre IP box)
```

---

## Installation proxy local (une fois)

```bash
# 1. Installer les dépendances
pip install flask flask-cors requests

# 2. Lancer le proxy (à faire à chaque session de trading)
python proxy_local.py
```

Le terminal affiche :
```
  PEA Cockpit — Proxy Local Yahoo Finance v2.0
  Écoute sur http://localhost:5001
  Votre IP box = jamais blacklistée
```

---

## Utilisation du cockpit

1. Lancez `proxy_local.py` dans un terminal
2. Ouvrez `index.html` dans Chrome/Firefox
3. Le bouton **⚪ Proxy local** devient **🟢 Proxy local** automatiquement
4. Importez votre Excel Bourse Direct → les données arrivent en batch (60 tickers en ~25s)

---

## Données récupérées par le proxy

Pour chaque ticker :
- **Cours** temps réel + variation du jour
- **Dividende annuel** (€/action)
- **Rendement** dividende (%)
- **Date ex-dividende** (prochaine)
- **Date de paiement**
- **Beta** (sensibilité au marché)
- **P/E trailing** (valorisation)
- **P/E forward** (anticipations)
- **Payout ratio** (% du bénéfice distribué)
- **52 semaines high/low**

---

## Gestion des ETF Amundi / Lyxor

Les ETF PEA ont souvent un ticker Bourse Direct différent du code Yahoo Finance.
La table `TICKER_MAP` dans `proxy_local.py` fait la conversion :

```python
"SEL"  → "C40.PA"    # Amundi Stoxx Europe Select Dividend 30
"CD8"  → "EMVD.PA"   # Amundi MSCI EMU High Dividend
"CW8"  → "CW8.PA"    # Amundi MSCI World
"PSP5" → "PSP5.PA"   # Amundi PEA S&P 500
...
```

Si un ticker ne retourne pas de dividende depuis Yahoo (ETF capitalisant),
le fallback `DIV_FALLBACK` dans `proxy_local.py` fournit les données manuelles.
**Mettez-le à jour** chaque année avec les nouvelles dates de détachement.

---

## Architecture des fichiers

```
pea-cockpit2/
├── proxy_local.py        ← Lancez ça sur votre machine (NOUVEAU)
├── app.py                ← Backend Render (fallback si proxy inactif)
├── requirements.txt
└── public/
    └── index.html        ← Le cockpit (modifié pour utiliser proxy en priorité)
```

---

## Déploiement sur Render (optionnel)

Render reste utile pour héberger le cockpit en ligne.
Mais **les données viendront de votre proxy local**, pas de Render.

Si vous voulez tout en autonome sur Render :
→ Utiliser l'API Yahoo Finance **avec yfinance** qui gère mieux les cookies :
```
pip install yfinance
```
Et dans app.py :
```python
import yfinance as yf
stock = yf.Ticker("TTE.PA")
info = stock.info  # dividende, beta, PE, etc.
```

---

## Mise à jour des dividendes de fallback

Dans `proxy_local.py`, mettez à jour `DIV_FALLBACK` 1x/an :
```python
DIV_FALLBACK = {
    "TTE": {"annual": 3.22, "exDate": "2025-09-19", "yield": 0.041},
    # → Modifiez exDate quand la nouvelle date est publiée (rapport annuel TotalEnergies)
}
```

Sources de référence pour les dates :
- **Boursorama** : fiche action → Dividendes
- **Zonebourse.com** : calendrier dividendes
- **Euronext** : euronext.com/fr/markets/paris
