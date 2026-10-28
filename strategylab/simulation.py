from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_DOWN
import math
import numpy as np
import pandas as pd
from .data import clean

@dataclass(frozen=True)
class Config:
    capital: float = 100
    commission: float = 0.001
    spread: float = 0.0002
    slippage: float = 0.0001
    stop: float = 0.05
    target: float = 0
    trailing: float = 0
    atr_multiple: float = 0
    mode: str = 'fraction'
    size: float = 1
    minimum: float = 5
    step: float = 0.00001
    min_qty: float = 0
    interval: str = '1d'
    executable: bool = True
    calendar: str = '24/7'

    def validate(self):
        if any(not isinstance(x, (int,float,bool)) or not math.isfinite(x) for k,x in asdict(self).items() if k not in ('mode','interval','calendar')):
            raise ValueError('Paramètres numériques non finis.')
        if self.capital<=0 or self.size<=0 or self.minimum<0 or self.step<=0 or self.min_qty<0:
            raise ValueError('Capital, taille et incrément doivent être positifs.')
        if any(not 0<=getattr(self,k)<1 for k in ('commission','spread','slippage','stop','target','trailing')):
            raise ValueError('Frais et stops doivent être compris entre 0 et 100% exclus.')
        if self.mode not in ('fraction','risque','montant') or (self.mode in ('fraction','risque') and self.size>1):
            raise ValueError('Taille de position invalide.')
        if self.mode=='risque' and not self.stop:
            raise ValueError('Le mode risque exige un stop-loss.')
        if not 0<=self.atr_multiple<=100:
            raise ValueError('Multiplicateur ATR invalide.')
        if self.interval not in ('1d','4h','1h'):
            raise ValueError('Unité invalide.')
        if self.calendar not in ('24/7','XNYS') or (self.calendar=='XNYS' and self.interval!='1d'):
            raise ValueError('Calendrier incompatible : IAU nécessite D1.')

def simulate(data, entry, exit, cfg=Config(), start=None, end=None):
    cfg.validate()
    d = clean(data)
    en, ex = entry.reindex(d.index).fillna(False), exit.reindex(d.index).fillna(False)
    if len(en)!=len(d):
        raise ValueError('Signaux invalides.')
    cash, qty, fees, stop, target, peak = cfg.capital, 0., 0., 0., 0., 0.
    trades, events, curve = [], [], []
    active = None
    step = pd.Timedelta(cfg.interval)
    session_positions=None
    if cfg.calendar=='XNYS':
        from .gold import sessions
        dates=sessions(d.index[0],d.index[-1])
        session_positions={date:i for i,date in enumerate(dates)}
        if any(date not in session_positions for date in d.index):
            raise ValueError('Bougie hors calendrier de cotation.')
    first = pd.Timestamp(start) if start is not None else d.index[0]
    last = pd.Timestamp(end) if end is not None else d.index[-1]+step
    if first.tzinfo is None:
        first = first.tz_localize('UTC')
    if last.tzinfo is None:
        last = last.tz_localize('UTC')
    friction = cfg.spread/2+cfg.slippage
    tr = pd.concat([d.high-d.low,(d.high-d.close.shift()).abs(),(d.low-d.close.shift()).abs()],axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    def sell(price, when, reason):
        nonlocal cash, qty, fees, active
        execution = price*(1-friction)
        fee = qty*execution*cfg.commission
        proceeds = qty*execution-fee
        cash += proceeds
        fees += fee
        events.append({'date':when,'type':'vente','quantité':qty,'prix':execution,'frais':fee,'motif':reason,'liquidités':cash})
        trades.append({**active,'sortie':when,'prix_sortie':execution,'frais_sortie':fee,'pnl':proceeds-active['coût'],'motif':reason})
        qty, active = 0., None
    for i,(date,row) in enumerate(d.iterrows()):
        if date<first or date>=last:
            continue
        consecutive = i>0 and (session_positions[date]-session_positions[d.index[i-1]]==1 if session_positions is not None else date-d.index[i-1]==step)
        exposed = qty>0
        # Après une lacune : annuler les signaux ; valoriser, sans inventer une exécution dans le trou.
        if qty:
            if stop and row.open<=stop:
                sell(row.open,date,'gap stop' if consecutive else 'stop après lacune : prix de reprise')
            elif target and row.open>=target:
                sell(target,date,'objectif à ouverture (prix prudent)')
            elif consecutive and bool(ex.iloc[i-1]):
                sell(row.open,date,'signal')
        elif consecutive and bool(en.iloc[i-1]):
            if not cfg.executable:
                events.append({'date':date,'type':'rejet','motif':'NON EXÉCUTABLE AVEC LE CAPITAL CHOISI : instrument non vérifié'})
            else:
                price = row.open*(1+friction)
                budget = cash*cfg.size if cfg.mode=='fraction' else (cfg.size if cfg.mode=='montant' else cash*cfg.size/(cfg.stop+2*friction+2*cfg.commission))
                budget = min(cash,budget)
                units = Decimal(str(budget/(price*(1+cfg.commission)))) / Decimal(str(cfg.step))
                q = float(units.to_integral_value(rounding=ROUND_DOWN)*Decimal(str(cfg.step)))
                cost = q*price*(1+cfg.commission)
                if q<=0 or q<cfg.min_qty or q*price<cfg.minimum or cost>cash:
                    events.append({'date':date,'type':'rejet','motif':'NON EXÉCUTABLE AVEC LE CAPITAL CHOISI : minimum ou fonds insuffisants'})
                else:
                    fee = q*price*cfg.commission
                    cash -= cost
                    qty, fees, peak = q, fees+fee, price
                    stop = price*(1-cfg.stop) if cfg.stop else 0
                    if cfg.trailing:
                        stop = max(stop,price*(1-cfg.trailing))
                    if cfg.atr_multiple and np.isfinite(atr.iloc[i-1]):
                        stop = max(stop,price-cfg.atr_multiple*atr.iloc[i-1])
                    target = price*(1+cfg.target) if cfg.target else 0
                    active = {'entrée':date,'prix_entrée':price,'quantité':q,'frais_entrée':fee,'coût':cost}
                    exposed = True
                    events.append({'date':date,'type':'achat','quantité':q,'prix':price,'frais':fee,'liquidités':cash,'motif':'signal'})
        if qty:
            # Stop prioritaire si les deux bornes sont touchées ; trailing actualisé pour la prochaine bougie.
            if stop and row.low<=stop:
                sell(min(row.open,stop),date,'stop (priorité prudente si ambiguïté)')
            elif target and row.high>=target:
                sell(target,date,'objectif')
            elif cfg.trailing or cfg.atr_multiple:
                peak = max(peak,row.high)
                if cfg.trailing:
                    stop = max(stop,peak*(1-cfg.trailing))
                if cfg.atr_multiple and np.isfinite(atr.iloc[i]):
                    stop = max(stop,peak-cfg.atr_multiple*atr.iloc[i])
        equity = cash+qty*row.close
        if cash < -1e-8 or equity < -1e-8:
            raise AssertionError('Violation du financement sans emprunt.')
        curve.append({'date':date,'capital':equity,'liquidités':cash,'quantité':qty,'exposé':exposed})
    if not curve:
        raise ValueError('Période sans bougie.')
    # Liquidation conventionnelle à la dernière clôture connue, identifiée dans le journal.
    if qty:
        date = curve[-1]['date']
        sell(d.loc[date,'close'],date,'fin : liquidation conventionnelle')
        curve[-1].update(capital=cash,liquidités=cash,quantité=0)
    return {'equity':pd.DataFrame(curve).set_index('date'), 'trades':pd.DataFrame(trades), 'events':pd.DataFrame(events), 'fees':fees, 'config':asdict(cfg)}
