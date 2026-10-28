import numpy as np
import pandas as pd
import re

RISK_OVERRIDES = {'ATR trailing': {'atr_multiple':3.}}

def indicators(d, ma_delta=0):
    c, h, l = d.close, d.high, d.low
    v = {'close': c, 'open': d.open, 'high': h, 'low': l, 'volume': d.volume}
    for n in (9, 10, 12, 20, 21, 26, 50, 55, 100, 200):
        v[f'SMA{n}'] = c.rolling(n+ma_delta).mean()
        v[f'EMA{n}'] = c.ewm(span=n+ma_delta, adjust=False, min_periods=n+ma_delta).mean()
    change = c.diff()
    up = change.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    down = (-change.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    v['RSI14'] = (100-100/(1+up/down)).where(down.ne(0), 100).where(up.ne(0) | down.ne(0), 50)
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    v['ATR14'] = atr
    v['MACD'] = v['EMA12']-v['EMA26']
    v['MACD_SIGNAL'] = v['MACD'].ewm(span=9, adjust=False, min_periods=9).mean()
    v['MACD_HIST'] = v['MACD']-v['MACD_SIGNAL']
    std = c.rolling(20).std(ddof=0)
    v['BB_UP'] = v['SMA20']+2*std
    v['BB_LOW'] = v['SMA20']-2*std
    v['Z20'] = (c-v['SMA20'])/std.replace(0, np.nan)
    k = 100*(c-l.rolling(14).min())/(h.rolling(14).max()-l.rolling(14).min()).replace(0, np.nan)
    v['STOCH_K'] = k
    v['STOCH_D'] = k.rolling(3).mean()
    plus, minus = h.diff(), -l.diff()
    pdm = plus.where((plus > minus) & (plus > 0), 0)
    mdm = minus.where((minus > plus) & (minus > 0), 0)
    v['DI_PLUS'] = 100*pdm.ewm(alpha=1/14, adjust=False, min_periods=14).mean()/atr
    v['DI_MINUS'] = 100*mdm.ewm(alpha=1/14, adjust=False, min_periods=14).mean()/atr
    dx = 100*(v['DI_PLUS']-v['DI_MINUS']).abs()/(v['DI_PLUS']+v['DI_MINUS']).replace(0, np.nan)
    v['ADX14'] = dx.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    for n in (20, 55, 100):
        v[f'HIGH{n}'] = h.rolling(n).max().shift()
        v[f'LOW{n}'] = l.rolling(n).min().shift()
    v['KC_UP'] = v['EMA20']+2*atr
    v['KC_LOW'] = v['EMA20']-2*atr
    v['ROC10'] = c.pct_change(10)*100
    v['VOL20'] = c.pct_change().rolling(20).std()
    # Supertrend récursif : les bandes passées ne sont jamais recalculées.
    upper, lower = (h+l)/2+3*atr, (h+l)/2-3*atr
    trend = pd.Series(np.nan, index=d.index)
    for i in range(14, len(d)):
        if i > 14:
            if c.iloc[i-1] <= upper.iloc[i-1]:
                upper.iloc[i] = min(upper.iloc[i], upper.iloc[i-1])
            if c.iloc[i-1] >= lower.iloc[i-1]:
                lower.iloc[i] = max(lower.iloc[i], lower.iloc[i-1])
        previous = trend.iloc[i-1] if i > 14 else 1
        trend.iloc[i] = 1 if c.iloc[i] > upper.iloc[i-1] else (-1 if c.iloc[i] < lower.iloc[i-1] else previous)
    v['SUPERTREND'] = trend
    return pd.DataFrame(v, index=d.index)

def cross(a, b):
    if np.isscalar(b):
        b = pd.Series(b, index=a.index)
    return (a > b) & (a.shift() <= b.shift())

def signals(d, ma_delta=0):
    v = indicators(d,ma_delta)
    c = v.close
    out = {}
    def add(name, entry, exit, doc):
        out[name] = (entry.fillna(False).astype(bool), exit.fillna(False).astype(bool), doc)
    for kind, pairs in [('SMA', [(20,50),(50,200)]), ('EMA', [(9,21),(20,50),(50,200)])]:
        for a,b in pairs:
            x,y = v[f'{kind}{a}'],v[f'{kind}{b}']
            add(f'{kind} {a}/{b}', cross(x,y), cross(y,x), f'Entrée croisement haussier {kind}{a}/{b}, sortie croisement baissier.')
    add('Triple EMA', (v.EMA9>v.EMA21)&(v.EMA21>v.EMA50), v.EMA9<v.EMA21, 'Entrée EMA9>EMA21>EMA50 ; sortie EMA9<EMA21.')
    add('MACD', cross(v.MACD,v.MACD_SIGNAL), cross(v.MACD_SIGNAL,v.MACD), 'MACD EMA12-EMA26 ; signal EMA9 ; croisements.')
    add('MACD histogramme', cross(v.MACD_HIST,0)&(c>v.EMA200), v.MACD_HIST<0, 'Histogramme franchit zéro et close>EMA200 ; sortie histogramme<0.')
    add('RSI momentum', cross(v.RSI14,60), v.RSI14<45, 'RSI Wilder14 franchit 60 ; sortie sous 45.')
    add('RSI retour moyenne', cross(v.RSI14,30), v.RSI14>55, 'RSI14 repasse au-dessus de 30 ; sortie au-dessus de 55.')
    add('Bollinger cassure', cross(c,v.BB_UP), c<v.SMA20, 'Close croise SMA20+2 écarts types ; sortie sous SMA20. Famille cassure, distincte du Z-score de retour à la moyenne.')
    add('Z-score', v.Z20<-2, v.Z20>=0, 'Z-score20 sous -2 ; sortie à zéro. Écart type population.')
    add('Stochastique', cross(v.STOCH_K,v.STOCH_D)&(v.STOCH_K<30), (v.STOCH_K>80)|cross(v.STOCH_D,v.STOCH_K), 'K14 croise D3 sous 30 ; sortie K>80 ou croisement inverse.')
    add('ADX directionnel', (v.ADX14>25)&cross(v.DI_PLUS,v.DI_MINUS), (v.DI_PLUS<v.DI_MINUS)|(v.ADX14<20), 'ADX Wilder14>25 et +DI croise -DI ; sortie inverse ou ADX<20.')
    for n in (20,55):
        add(f'Donchian {n}', c>v[f'HIGH{n}'], c<v[f'LOW{n}'], f'Close dépasse le plus haut des {n} bougies antérieures ; sortie sous plus bas antérieur.')
    add('Cassure hauts 100', (c>v.HIGH100)&(d.volume>d.volume.rolling(20).mean()), c<v.SMA50, 'Cassure HIGH100 antérieur avec volume>moyenne20 ; sortie close<SMA50.')
    add('ATR breakout', c>c.shift()+2*v.ATR14.shift(), c<v.EMA20, 'Choc haussier : close>close antérieure+2 ATR14 antérieur ; sortie close<EMA20.')
    add('ATR trailing', c>v.EMA50, c<v.EMA50, 'Entrée close>EMA50 ; sortie close<EMA50 ou stop suiveur 3 ATR14 Wilder sous le plus haut depuis entrée, jamais abaissé et révisé pour la bougie suivante.')
    add('Supertrend', cross(v.SUPERTREND,0), v.SUPERTREND<0, 'Supertrend ATR14 multiplicateur3 ; entrée bascule positive, sortie négative.')
    add('Keltner', cross(c,v.KC_UP), c<v.EMA20, 'Close croise EMA20+2 ATR14 ; sortie sous EMA20.')
    squeeze = (v.BB_UP<v.KC_UP)&(v.BB_LOW>v.KC_LOW)
    add('Volatility squeeze', squeeze.shift(fill_value=False)&~squeeze&(c>v.BB_UP), c<v.SMA20, 'Sortie de compression Bollinger dans Keltner et close>BB haute ; sortie sous SMA20.')
    add('ROC momentum', cross(v.ROC10,2), v.ROC10<0, 'ROC10 franchit 2% ; sortie ROC10<0.')
    add('Moyenne volatilité', cross(c,v.SMA50)&(v.VOL20<0.03), (c<v.SMA50)|(v.VOL20>0.05), 'Close croise SMA50 avec volatilité rendements20<3% ; sortie sous SMA50 ou volatilité>5%.')
    add('Tendance multiple', (c>v.EMA200)&(v.EMA20>v.EMA50)&(v.ADX14>25)&(v.RSI14>55), (c<v.EMA50)|(v.RSI14<45), 'Close>EMA200, EMA20>EMA50, ADX14>25, RSI14>55 ; sortie close<EMA50 ou RSI<45.')
    add('EMA RSI', cross(v.EMA20,v.EMA50)&(v.RSI14>50), (v.EMA20<v.EMA50)|(v.RSI14<40), 'EMA20 croise EMA50 avec RSI14>50 ; sortie EMA20<EMA50 ou RSI14<40.')
    add('Achat-conservation', pd.Series(True,index=d.index), pd.Series(False,index=d.index), 'Achat à la première ouverture après la première bougie ; mêmes frais et contraintes ; conservation jusqu’à la fin.')
    add('Liquidités', pd.Series(False,index=d.index), pd.Series(False,index=d.index), 'Capital conservé sans intérêt.')
    return out

def custom_signals(d, rule):
    if not isinstance(rule, dict) or not {'entry','exit'} <= set(rule) or set(rule)-{'entry','exit','risk'}:
        raise ValueError('Règle : entry et exit obligatoires, aucun code accepté.')
    if 'risk' in rule and (set(rule['risk']) != {'stop','target','trailing'} or any(not isinstance(x,(int,float)) or not np.isfinite(x) or not 0<=x<1 for x in rule['risk'].values())):
        raise ValueError('Stops JSON invalides.')
    v = indicators(d)
    def series(name):
        if name in v:
            return v[name]
        match = re.fullmatch(r'(SMA|EMA|RSI|ROC)([0-9]{1,3})',str(name))
        if not match or not 2<=int(match[2])<=500:
            raise ValueError('Indicateur ou période invalide : '+str(name))
        kind,n = match[1],int(match[2])
        c = d.close
        if kind=='SMA': return c.rolling(n).mean()
        if kind=='EMA': return c.ewm(span=n,adjust=False,min_periods=n).mean()
        if kind=='ROC': return c.pct_change(n)*100
        up=c.diff().clip(lower=0).ewm(alpha=1/n,adjust=False,min_periods=n).mean()
        down=(-c.diff().clip(upper=0)).ewm(alpha=1/n,adjust=False,min_periods=n).mean()
        return (100-100/(1+up/down)).where(down.ne(0),100).where(up.ne(0)|down.ne(0),50)
    def group(g):
        if set(g) != {'mode','conditions'} or g['mode'] not in ('ET','OU') or not 1 <= len(g['conditions']) <= 10:
            raise ValueError('Groupe invalide.')
        values = []
        for r in g['conditions']:
            if set(r) != {'left','op','right'} or r['op'] not in ('>','<','croise au-dessus','croise au-dessous'):
                raise ValueError('Condition invalide.')
            a = series(r['left'])
            try:
                b = float(r['right'])
            except (ValueError,TypeError):
                b = series(r['right'])
            if np.isscalar(b) and not np.isfinite(b):
                raise ValueError('Seuil non fini.')
            values.append({'>' : lambda:a>b, '<':lambda:a<b, 'croise au-dessus':lambda:cross(a,b), 'croise au-dessous':lambda:cross(-a,-b)}[r['op']]().fillna(False))
        result = values[0]
        for value in values[1:]:
            result = result & value if g['mode']=='ET' else result | value
        return result
    return group(rule['entry']), group(rule['exit']), 'Règles JSON validées ; signaux à la clôture, exécution à l’ouverture suivante.'
