# StrategyLab AI

Application locale Windows de recherche historique, en français. Aucun ordre réel, clé privée, compte payant ou modèle IA externe. Python 3.11. Un moteur spécialisé en comptabilité spot finance les achats frais compris ; une position maximum. Il remplace ici les moteurs généralistes pour expliciter fractions, rejets, gaps et conservation des liquidités.

## Installation PowerShell

Depuis le dossier du projet, avec Python 3.11 installé :

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-lock.txt
./.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
./launch.ps1
```

Alternative si `uv` est installé : `uv venv --python 3.11 .venv`, puis `uv pip install --python .venv/Scripts/python.exe -r requirements.txt`.
Ouvrir http://127.0.0.1:8501. Le serveur écoute uniquement sur la machine. Aucun téléversement cloud. Arrêter par Ctrl+C.

## Utilisation

### Parcours simple : profils prêts à tester

XAU/USD est sélectionné par défaut et simulé au moyen du titre IAU, iShares Gold Trust, adossé à l'or physique et coté en USD. Ce titre est distinct du prix de référence XAU/USD et ne donne pas une détention directe de lingots. L'historique OHLC provient de Yahoo Finance ; le calendrier XNYS distingue séances et fermetures. Le capital par défaut est de 100 EUR, convertis en USD puis reconvertis en EUR avec le dernier taux de référence BCE strictement antérieur à la séance et 0,1 % de frais hypothétiques par conversion. Les liquidités intermédiaires restent en USD. Parts entières uniquement ; l'accessibilité du titre et les frais réels selon le courtier ou le pays ne sont pas certifiés. L'interface montre d'abord le résultat unique, puis son explication et les détails sur demande.

La page d'accueil propose 26 stratégies et 2 benchmarks, chacun accompagné de son objectif, de ses conditions exactes d'entrée/sortie et de tous ses réglages. Choisir une stratégie charge automatiquement son profil : 100 unités monétaires de capital initial, allocation de 100 % des liquidités, D1, coûts explicites et protections propres au profil. Ces protections sont des choix pédagogiques non optimisés, jamais des valeurs présentées comme optimales.

Choisir **3 ans, 2 ans, 1 an ou 6 mois**, puis **Lancer ce backtest**. Les données réelles sont téléchargées et vérifiées automatiquement, en réutilisant les archives en cache. Le test porte exactement sur la durée calendaire choisie, jusqu'à la dernière journée UTC terminée ; le passé disponible prépare les indicateurs sans créer d'opérations avant la période. Une couverture insuffisante provoque une erreur, aucune extrapolation.

Les réglages sont visibles sans saisie obligatoire. Cocher **Personnaliser les réglages : créer une variante** permet de les modifier. Toute différence (capital, coûts, stop, taille, unité, minimums, etc.) produit automatiquement un nom `Nom — Variante <empreinte>`, conservé dans les résultats, exports et SQLite. Rétablir les valeurs initiales rétablit le nom de référence. Choisir une autre stratégie recharge son propre profil et désactive la personnalisation. Marché et durée constituent le scénario, sans renommer la logique de stratégie. Les stratégies et historiques déjà enregistrés restent intacts.

Les résultats du parcours simple sont des backtests historiques sur la durée choisie, sans qualification hors échantillon automatique. Ils incluent les benchmarks achat-conservation et liquidités aux mêmes coûts. Pour les imports forex/or, les règles manuelles et le protocole de validation, ouvrir **Mode expert** depuis la barre latérale. Les marchés sans données et conditions d'instrument documentées sont bloqués dans le parcours simple.

### Mode expert conservé

1. Choisir BTC/USDT, D1, trois ans et télécharger. SHA-256 de chaque ZIP et cache contrôlés ; archives mensuelles puis journalières en repli. Source : https://github.com/binance/binance-public-data . Les timestamps spot passent aux microsecondes en 2025. Aucune bougie interpolée.
2. Vérifier les dates et lacunes. Les prix ne sont jamais inventés. Les éventuelles erreurs réseau restent visibles. La date de fin est exclusive et les bougies inachevées sont exclues par défaut.
3. Choisir les coûts, la taille, les stratégies et lancer l'exploration sur les 24 premiers mois. Geler les réglages avec le bouton dédié, puis passer en phase Validation et relancer : les douze derniers mois deviennent accessibles. Tout changement de données, paramètres ou sélection exige une nouvelle exploration et un nouveau gel. Arrêter via le bouton Streamlit en haut à droite. Aucun résultat partiel du nouveau lot publié après interruption.
4. Comparer OOS, drawdown, trades et sensibilité aux frais. Trier les colonnes du tableau. Télécharger les journaux, le classement et le rapport HTML.
5. Construire les conditions ET/OU dans l'éditeur ; enregistrer avec un autre nom pour dupliquer. SMA, EMA, RSI et ROC acceptent des périodes 2 à 500 ; les autres indicateurs ont les paramètres documentés du registre. JSON validé, aucun eval ni exécution de code utilisateur. SQLite conserve règles, configuration, empreinte des bougies, journaux, transactions et courbes compressées ; Parquet conserve les bougies. Les stops manuels sont sauvegardés avec la stratégie. Les graphiques du rapport HTML fonctionnent hors connexion.

## Périmètre et conventions

26 stratégies déterministes plus deux benchmarks (les paramètres et conditions exactes apparaissent dans chaque fiche ; registre `strategylab/strategies.py`). Variantes de moyennes regroupées dans le registre, aucun renommage artificiel pour atteindre un quota. Toutes utilisent le passé et la clôture courante ; exécution ouverture suivante. Les tests modifient l'horizon futur et vérifient l'invariance des signaux passés.

Coûts constants paramétrables : moitié du spread et tout le slippage défavorables par côté, commission sur le notionnel. Quantités arrondies vers le bas, coût jamais supérieur aux liquidités. Les valeurs de lot par défaut sont des hypothèses et ne constituent pas une certification des règles historiques Binance. Le risque au stop reste une cible : un gap peut la dépasser. Stop prioritaire en cas d'ambiguïté intrabar ; trailing actualisé après la bougie. Fin : liquidation conventionnelle à la dernière clôture, avec frais, explicitement journalisée.

Validation : 24 mois puis 12 mois, uniquement si couverture continue suffisante ; indicateurs réchauffés avec le passé, cash neuf au début OOS. Pas de réoptimisation OOS. Une fois les résultats OOS consultés, modifier les paramètres invalide l'indépendance du test pour une sélection : réserver de nouvelles données avant toute conclusion. Score = rendement OOS moins drawdown OOS ; 10 trades minimum, drawdown OOS au plus 25% et rendement OOS positif avec commission/slippage doublés sont des seuils exploratoires pour la catégorie prometteuse, pas une preuve statistique. Le tableau présente aussi régularité mensuelle et coûts. Frais doubles testés sur historique et OOS. Sensibilité des périodes SMA/EMA à ±1 disponible ; si une stratégie ne les utilise pas, cette perturbation ne change pas ses signaux et ne teste pas ses autres paramètres. Fenêtres walk-forward successives de six mois après 24 mois disponibles en option, règles gelées, capital réinitialisé, aucune optimisation. Sans pertes ou sans trades, métriques non définies laissées vides. Performance annualisée seulement à partir d'un an. Benchmarks : 100% financé et stops automatiquement désactivés.

Les CSV réels acceptent mapping OHLCV, fuseau et décimale. Les trous sont signalés ; aucune entrée sur un signal séparé par une lacune. Pas de bougies artificielles le week-end pour le forex. Les CSV forex/or sont bloqués par défaut ; une simulation physique peut être activée uniquement après déclaration explicite de l'instrument détenu, source des conditions, minimum et incrément. Cette déclaration n'est pas une certification automatique. EUR/USD achète des EUR financés en USD ; USD/JPY est inversé (high=1/low, low=1/high), les USD achètent des JPY détenus puis reconvertis en USD. Les graphiques et signaux sont alors en USD/JPY détenu, soit USD par JPY ; le volume d'origine reste dans les unités de sa source. XAU/USD seul est une référence : prix négociable en USD par once troy et propriété physique exigés pour activer la simulation ; aucun CFD. USD et USDT sont distincts, sans conversion implicite. Sans calendrier de marché certifié, les fermetures forex sont signalées comme discontinuités et la validation OOS stricte n'est pas attribuée : aucune fausse continuité.

## Vérification réelle

```powershell
./.venv/Scripts/python.exe -m scripts.verify_real
./.venv/Scripts/python.exe -m scripts.verify_real --symbol ETHUSDT
./.venv/Scripts/python.exe -m scripts.verify_ui
```

Les rapports `%LOCALAPPDATA%/StrategyLabAI/verification_BTCUSDT.json` et `verification_ETHUSDT.json` indiquent les dates réellement téléchargées et les 28 résultats de chaque marché (26 stratégies et 2 benchmarks). Le même dossier conserve SQLite, Parquet et ZIP ; le dossier Documents n'a pas besoin d'une exception Defender. `STRATEGYLAB_DATA` permet de choisir un autre dossier accessible. Les valeurs courantes des filtres Binance peuvent être lues par API publique ; elles ne prouvent pas les règles de lot historiques, et une erreur API n'est jamais remplacée par une certification inventée. Tests synthétiques uniquement dans `tests/`, jamais chargés comme performances réelles. AppTest vérifie aussi le parcours de comparaison avec BTC réel.

Limites : import MT5 direct absent (CSV exporté de MT5 importable), pas de calendrier certifié forex/or, pas de règles historiques de lots, pas d'optimisation combinatoire, ni d'analyse statistique exhaustive de robustesse. H1/H4 implémentés mais non certifiés tant que trois ans continus ne sont pas téléchargés et contrôlés. L'import CSV ne prouve pas sa provenance ni les conditions d'exécution : elles sont déclarées par l'utilisateur. L'historique de deux cryptos ne représente pas l'ensemble du marché et ne permet pas d'écarter le biais de sélection/survivance. Le nom AI ne signifie pas prédiction : stratégies déterministes, aucun LLM ni frais d'API.

En hébergement Linux partagé, les stratégies manuelles restent propres à chaque session et les journaux ne sont pas enregistrés dans une base SQLite commune. Ils disparaissent à la fin de la session : utilisez les exports pour les conserver. Sur Windows local, SQLite continue à conserver les données comme indiqué ci-dessus.
