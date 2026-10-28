# Vérification exécutée le 28 octobre 2026

- Nouveau parcours de profils : **36 tests réussis**, dont 28 profils valides, les quatre durées, le renommage automatique de chaque réglage et la remise à zéro au changement de stratégie.
- Test d'intégration BTC réel : période exacte de six mois, profil SMA 20/50, nouvelle variante après passage du stop à 3 %, journaux et exports rendus, navigation vers le mode expert conservée.
- Python local isolé : 3.11.16 ; dépendances installées, versions dans `requirements-lock.txt`.
- `python -m pytest -q -p no:cacheprovider` : **19 tests réussis**. Données synthétiques réservées aux tests.
- BTC/USDT réel : **1 096 bougies D1**, du **2023-10-28 au 2026-10-27 UTC**, aucune rupture ni archive absente.
- ETH/USDT réel : **1 096 bougies D1**, mêmes dates et mêmes contrôles, aucune rupture ni archive absente.
- SHA-256 contrôlés sur les archives Binance mensuelles/journalières, timestamps millisecondes/microsecondes traités.
- **28 simulations par marché** (26 stratégies et deux benchmarks), soit **56 simulations historiques réelles**. Rapports détaillés dans `%LOCALAPPDATA%/StrategyLabAI/verification_BTCUSDT.json` et `verification_ETHUSDT.json`.
- Parcours Streamlit AppTest avec BTC réel : 8 stratégies, exploration de 24 mois, gel des réglages, validation sur 12 mois, graphiques, journaux et exports rendus sans exception.
- Serveur local démarré sur `http://127.0.0.1:8501` ; point de santé HTTP 200.

## Ce qui n'est pas certifié

H1/H4 n'ont pas fait l'objet de la vérification réseau complète ; leurs résultats sont bloqués sans couverture continue de trois ans. Aucun CSV réel forex/or n'a été fourni : import et conversions sont testés unitairement, aucune performance historique sur ces marchés n'est inventée. Les règles actuelles Binance sont lisibles via API publique, sans garantie de validité historique. Les propriétés et minimums des instruments physiques doivent être documentés par l'utilisateur. Le calendrier forex/or n'est pas certifié ; ses fermetures empêchent une validation OOS strictement continue. La sensibilité paramétrique automatique couvre SMA/EMA à ±1 seulement ; elle ne constitue pas une analyse exhaustive. L'import MT5 direct n'est pas implémenté.

Les rapports ne sont pas une recommandation de stratégie ni une promesse de rendement. Aucun compte de courtage, clé privée ou ordre réel n'a été utilisé. La protection Windows n'a pas été modifiée ; le stockage est dans le dossier local de l'application.
