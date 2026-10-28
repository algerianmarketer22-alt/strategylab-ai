"""Profils explicites, sans optimisation sur les performances historiques."""
from dataclasses import asdict, replace
import hashlib
import json
import pandas as pd
from .simulation import Config
from .strategies import signals

PERIODS = {'3 ans':36, '2 ans':24, '1 an':12, '6 mois':6}

def indicator_explanations(name, logic):
    text = name+' '+logic
    definitions = [
        (('SMA',),'Une SMA est la moyenne simple des clôtures : SMA20 utilise les 20 dernières bougies, SMA50 les 50 dernières. En D1, une bougie correspond à une journée. Un croisement haussier signifie que la première moyenne était inférieure ou égale à la seconde à la clôture précédente et lui devient strictement supérieure.'),
        (('EMA',),'Une EMA est une moyenne exponentielle donnant plus de poids aux clôtures récentes, avec un coefficient 2/(période+1). Les nombres indiquent les périodes en bougies. Son calcul est récursif et ne réécrit pas les signaux passés.'),
        (('MACD',),'Le MACD est EMA12 moins EMA26 ; sa ligne de signal est une EMA9 du MACD. L’histogramme est la différence entre MACD et signal. Un franchissement haussier de zéro passe d’une valeur inférieure ou égale à zéro à une valeur strictement positive.'),
        (('RSI',),'Le RSI14 compare les gains et pertes des 14 dernières périodes avec un lissage de Wilder (coefficient 1/14). Il varie de 0 à 100. Les niveaux d’achat et de sortie sont ceux indiqués dans les règles, sans ajout de filtre caché.'),
        (('Bollinger','Z-score','Volatility squeeze'),'Les bandes de Bollinger utilisent SMA20 ± 2 écarts types des 20 clôtures (écart type de population). Le Z-score20 est (clôture − SMA20) / cet écart type. Un écart type nul rend le Z-score non défini et ne crée pas de signal.'),
        (('Stochastique',),'Le stochastique K14 vaut 100 × (clôture − plus bas14) / (plus haut14 − plus bas14). D3 est la moyenne simple de K sur trois bougies. Les niveaux 30 et 80 ainsi que les croisements gouvernent les entrées et sorties décrites.'),
        (('ADX','+DI'),'ADX14 mesure la force du mouvement ; +DI et −DI en indiquent la direction. Les mouvements directionnels et l’amplitude vraie sont lissés selon Wilder sur 14 périodes ; ADX lisse ensuite la différence relative absolue des deux indices directionnels. Les seuils 25 et 20 ne signifient pas une probabilité de gain.'),
        (('Donchian','Cassure hauts'),'Les plus hauts et plus bas sont calculés sur les bougies précédentes, en excluant la bougie du signal : 20, 55 ou 100 selon la règle. La cassure est confirmée par la clôture. Le filtre de volume de la cassure 100 compare le volume courant à sa moyenne simple sur 20 bougies.'),
        (('ATR','Keltner','Supertrend','Volatility squeeze'),'L’ATR14 est le lissage de Wilder sur 14 bougies de l’amplitude vraie : maximum de haut−bas, |haut−clôture précédente| et |bas−clôture précédente|. Il mesure une distance de prix, pas un pourcentage. Un stop suiveur ATR ne baisse jamais pendant une position et sa mise à jour ne s’applique qu’à la bougie suivante.'),
        (('Keltner','Volatility squeeze'),'Le canal de Keltner utilise EMA20 ± 2 ATR14. La compression exige que les deux bandes de Bollinger soient à l’intérieur de ce canal ; la stratégie squeeze attend la fin de cette compression et une clôture au-dessus de la bande haute de Bollinger.'),
        (('Supertrend',),'Le Supertrend utilise le milieu (haut+bas)/2 et des bandes à ±3 ATR14. Ses bandes finales sont ajustées récursivement selon les clôtures et bandes antérieures ; une clôture au-dessus de la bande supérieure antérieure bascule la tendance à la hausse, sous la bande inférieure antérieure à la baisse. Les autres clôtures conservent l’état précédent.'),
        (('ROC',),'Le ROC10 est 100 × (clôture / clôture dix bougies auparavant − 1). Il représente une variation en pourcentage, sans annualisation.'),
        (('Moyenne volatilité',),'La volatilité est l’écart type des rendements journaliers des 20 dernières bougies (écart type échantillonnal, sans annualisation). Les seuils de 3 % et 5 % portent sur cette mesure, pas sur la variation du prix total.'),
        (('Achat-conservation',),'Le profil de référence investit les liquidités finançables une fois, conserve l’actif et le liquide conventionnellement à la fin, avec les mêmes coûts que les autres stratégies. Le capital restant après arrondi reste en liquidités.'),
        (('Liquidités',),'Aucun signal d’achat n’est émis : le capital reste en devise de cotation. Aucun intérêt, frais de transaction ou rendement de placement n’est ajouté.'),
    ]
    return [description for tokens,description in definitions if any(token in text for token in tokens)]

# Choix pédagogiques de risque, pas des paramètres certifiés optimaux.
PROFILES = {
    'SMA 20/50': ('Suivre les tendances intermédiaires avec deux moyennes simples.', .08, 0., 0.),
    'SMA 50/200': ('Suivre les grandes tendances avec des moyennes plus lentes.', .12, 0., 0.),
    'EMA 9/21': ('Réagir aux changements de tendance avec des moyennes exponentielles rapides.', .05, 0., 0.),
    'EMA 20/50': ('Suivre une tendance intermédiaire en donnant plus de poids aux prix récents.', .08, 0., 0.),
    'EMA 50/200': ('Chercher les tendances longues avec deux moyennes exponentielles.', .12, 0., 0.),
    'Triple EMA': ('Exiger l’alignement de trois moyennes pour confirmer une tendance.', .08, 0., 0.),
    'MACD': ('Détecter un changement de dynamique avec le MACD et sa ligne de signal.', .07, 0., 0.),
    'MACD histogramme': ('Combiner une accélération du MACD et une tendance de fond positive.', .07, 0., 0.),
    'RSI momentum': ('Acheter une force relative déjà élevée plutôt qu’un actif simplement en baisse.', .06, 0., 0.),
    'RSI retour moyenne': ('Chercher un rebond après une phase de faiblesse du RSI.', .04, .08, 0.),
    'Bollinger cassure': ('Suivre une cassure haussière de l’enveloppe de volatilité.', .06, 0., 0.),
    'Z-score': ('Chercher un retour vers la moyenne après un écart statistique négatif important.', .04, .08, 0.),
    'Stochastique': ('Chercher un redémarrage dans la partie basse de l’intervalle récent des prix.', .04, .08, 0.),
    'ADX directionnel': ('Combiner la force de tendance ADX et sa direction +DI/−DI.', .08, 0., 0.),
    'Donchian 20': ('Acheter une cassure du plus haut des 20 journées précédentes.', .08, 0., 0.),
    'Donchian 55': ('Acheter une cassure plus rare du plus haut des 55 journées précédentes.', .12, 0., 0.),
    'Cassure hauts 100': ('Exiger une cassure de long terme accompagnée d’un volume élevé.', .10, 0., 0.),
    'ATR breakout': ('Chercher un choc haussier dépassant deux fois l’amplitude récente.', .08, 0., 0.),
    'ATR trailing': ('Suivre une tendance et relever un stop adapté à la volatilité ATR.', 0., 0., 0.),
    'Supertrend': ('Suivre les bascules d’une tendance définie par des bandes ATR.', .10, 0., 0.),
    'Keltner': ('Acheter la cassure d’un canal de volatilité autour d’une moyenne exponentielle.', .07, 0., 0.),
    'Volatility squeeze': ('Chercher une cassure haussière au sortir d’une compression de volatilité.', .06, 0., 0.),
    'ROC momentum': ('Acheter une accélération positive du prix sur dix journées.', .06, 0., 0.),
    'Moyenne volatilité': ('Suivre une moyenne seulement si la volatilité récente reste contenue.', .06, 0., 0.),
    'Tendance multiple': ('Exiger l’accord des moyennes, de l’ADX et du RSI avant d’acheter.', .08, 0., 0.),
    'EMA RSI': ('Confirmer un croisement de moyennes par un RSI orienté à la hausse.', .07, 0., 0.),
    'Achat-conservation': ('Acheter une seule fois puis conserver jusqu’à la fin de la période.', 0., 0., 0.),
    'Liquidités': ('Conserver le capital sans achat, sans frais et sans intérêts.', 0., 0., 0.),
}

def catalogue():
    schema = pd.DataFrame({k:pd.Series(dtype=float) for k in ('open','high','low','close','volume')},index=pd.DatetimeIndex([],tz='UTC'))
    registry = signals(schema)
    return {name:{'purpose':purpose,'logic':registry[name][2],'explanations':indicator_explanations(name,registry[name][2]),
                  'config':Config(stop=stop,target=target,trailing=trailing,atr_multiple=3. if name=='ATR trailing' else 0.)}
            for name,(purpose,stop,target,trailing) in PROFILES.items()}

def identity(name, config, reference):
    """Les paramètres changent l'identité ; marché et dates définissent le scénario."""
    actual, original = asdict(config),asdict(reference)
    # L'autorisation opérationnelle d'un instrument n'est pas un paramètre de stratégie.
    changes = {key:value for key,value in actual.items() if key!='executable' and value!=original[key]}
    if not changes:
        return name, changes
    canonical = {key:float(value) if isinstance(value,(int,float)) else value for key,value in actual.items() if key!='executable'}
    digest = hashlib.sha256(json.dumps(canonical,sort_keys=True,allow_nan=False).encode()).hexdigest()[:10]
    return f'{name} — Variante {digest}', changes

def bounds(label, end):
    if label not in PERIODS:
        raise ValueError('Durée de backtest non autorisée.')
    end = pd.Timestamp(end)
    end = end.tz_localize('UTC') if end.tzinfo is None else end.tz_convert('UTC')
    return end-pd.DateOffset(months=PERIODS[label]),end

def configuration_table(config, currency):
    return {
        'Capital initial':f'{config.capital:g} {currency}',
        'Taille de position':{'fraction':f'{config.size*100:g} % des liquidités disponibles','risque':f'{config.size*100:g} % du capital risqué jusqu’au stop','montant':f'{config.size:g} {currency} par opération'}[config.mode],
        'Stop-loss fixe':f'{config.stop*100:g} %' if config.stop else 'Désactivé',
        'Take-profit fixe':f'{config.target*100:g} %' if config.target else 'Désactivé',
        'Stop suiveur en pourcentage':f'{config.trailing*100:g} %' if config.trailing else 'Désactivé',
        'Stop suiveur ATR':f'{config.atr_multiple:g} × ATR14 Wilder' if config.atr_multiple else 'Désactivé',
        'Commission par côté':f'{config.commission*100:g} %',
        'Spread total':f'{config.spread*100:g} %',
        'Slippage par côté':f'{config.slippage*100:g} %',
        'Minimum notionnel':f'{config.minimum:g} {currency}',
        'Incrément de quantité':f'{config.step:g} unité de l’actif de base',
        'Quantité minimale':f'{config.min_qty:g} unité de l’actif de base',
        'Bougies':{'1d':'D1 : une journée','4h':'H4 : quatre heures','1h':'H1 : une heure'}[config.interval],
        'Exécution':'Ouverture suivante après confirmation du signal ; long uniquement ; aucun emprunt',
        'Ambiguïté intrabar':'Stop prioritaire si objectif et stop sont touchés dans la même bougie',
        'Fin du backtest':'Liquidation conventionnelle à la dernière clôture connue, frais inclus',
    }
