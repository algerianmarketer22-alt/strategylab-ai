import numpy as np
import pandas as pd

def metrics(result):
    e, t = result['equity'], result['trades']
    initial = result['config']['capital']
    equity = e.capital
    pnl = t.pnl if len(t) else pd.Series(dtype=float)
    wins, losses = pnl[pnl>0],pnl[pnl<0]
    peak = equity.cummax().clip(lower=initial)
    days = (e.index[-1]-e.index[0]+pd.Timedelta(result['config']['interval'])).total_seconds()/86400
    monthly = equity.resample('ME').last().pct_change()
    if len(monthly):
        monthly.iloc[0] = equity.resample('ME').last().iloc[0]/initial-1
    annual = equity.resample('YE').last().pct_change()
    if len(annual):
        annual.iloc[0] = equity.resample('YE').last().iloc[0]/initial-1
    maxdd = float(((equity/peak)-1).min()*-100)
    return {'capital_final':float(equity.iloc[-1]), 'profit_net':float(equity.iloc[-1]-initial),
            'rendement_pct':float((equity.iloc[-1]/initial-1)*100),
            'annualisé_pct':float(((equity.iloc[-1]/initial)**(365.25/days)-1)*100) if days>=365 else None,
            'drawdown_pct':maxdd, 'ratio_rendement_drawdown':float((equity.iloc[-1]/initial-1)*100/maxdd) if maxdd>0 else None,'trades':len(t),
            'réussite_pct':float((pnl>0).mean()*100) if len(t) else None,
            'profit_factor':float(wins.sum()/-losses.sum()) if len(losses) else None,
            'gain_moyen':float(wins.mean()) if len(wins) else None,
            'perte_moyenne':float(losses.mean()) if len(losses) else None,
            'ratio_gain_perte':float(wins.mean()/-losses.mean()) if len(wins) and len(losses) else None,
            'exposition_pct':float(e['exposé'].mean()*100), 'frais':result['fees'],
            'début':str(e.index[0]),'fin':str(e.index[-1]),'bougies':len(e),
            'mois_positifs_pct':float((monthly>0).mean()*100),
            'rejets':int((result['events']['type']=='rejet').sum()) if len(result['events']) else 0}, monthly, annual
