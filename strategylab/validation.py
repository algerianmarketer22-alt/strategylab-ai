from dataclasses import replace
import pandas as pd
from .simulation import simulate
from .statistics import metrics

def evaluate(d, signal, cfg):
    entry, exit, _ = signal
    full = simulate(d,entry,exit,cfg)
    summary, monthly, annual = metrics(full)
    boundary = d.index[0]+pd.DateOffset(months=24)
    enough = d.index[-1]+pd.Timedelta(cfg.interval)>=d.index[0]+pd.DateOffset(months=36)
    continuous = d.index.to_series().diff().dropna().eq(pd.Timedelta(cfg.interval)).all()
    oos = None
    if enough and continuous:
        exploration = simulate(d,entry,exit,cfg,end=boundary)
        summary['exploration_pct'] = metrics(exploration)[0]['rendement_pct']
        oos = simulate(d,entry,exit,cfg,start=boundary)
        m,_,_ = metrics(oos)
        summary.update(oos_pct=m['rendement_pct'],oos_trades=m['trades'],oos_drawdown=m['drawdown_pct'])
    else:
        summary['exploration_pct'] = None
        summary.update(oos_pct=None,oos_trades=None,oos_drawdown=None)
    if not cfg.executable or (summary['rejets'] and not summary['trades']):
        category = 'Non exécutable'
    elif oos is None:
        category = 'Insuffisamment validée'
    elif summary['oos_pct']<0:
        category = 'Perdante hors échantillon'
    elif summary['oos_trades']<10:
        category = 'Insuffisamment validée'
    else:
        category = 'Prometteuse historique'
    summary['catégorie'] = category
    summary['score_prudent'] = (summary['oos_pct']-summary['oos_drawdown']) if oos is not None else None
    # Aucun choix automatique de paramètres : variantes préfixées avant la validation.
    costly = simulate(d,entry,exit,replace(cfg,commission=min(.99,cfg.commission*2),slippage=min(.99,cfg.slippage*2)))
    summary['rendement_frais_doubles_pct'] = metrics(costly)[0]['rendement_pct']
    summary['oos_frais_doubles_pct'] = None
    if oos is not None:
        stressed = simulate(d,entry,exit,replace(cfg,commission=min(.99,cfg.commission*2),slippage=min(.99,cfg.slippage*2)),start=boundary)
        summary['oos_frais_doubles_pct'] = metrics(stressed)[0]['rendement_pct']
        if category=='Prometteuse historique' and (summary['oos_frais_doubles_pct']<=0 or summary['oos_drawdown']>25):
            summary['catégorie'] = 'Insuffisamment validée'
    return summary, full, monthly, annual, oos

def walk_forward(d, signal, cfg, months=6):
    """Fenêtres test successives, règles gelées, passé disponible pour réchauffer les indicateurs."""
    start = d.index[0]+pd.DateOffset(months=24)
    rows = []
    while start+pd.DateOffset(months=months)<=d.index[-1]+pd.Timedelta(cfg.interval):
        end = start+pd.DateOffset(months=months)
        r = simulate(d,*signal[:2],cfg,start=start,end=end)
        m,_,_ = metrics(r)
        rows.append({'début_fenêtre':str(start),'fin_exclusive':str(end),**m})
        start = end
    return pd.DataFrame(rows)
