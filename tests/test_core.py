from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from strategylab.simulation import Config, simulate
from strategylab.strategies import signals, custom_signals
from strategylab.statistics import metrics
from strategylab.data import clean

def prices(n=400):
    # Synthétique uniquement pour les tests ; jamais chargé par l'application.
    c = 100+np.arange(n)*.02+np.sin(np.arange(n)/5)*8
    return pd.DataFrame({'open':c,'high':c+2,'low':c-2,'close':c,'volume':1000},index=pd.date_range('2020',periods=n,tz='UTC'))

def flags(d):
    return pd.Series(True,index=d.index),pd.Series(False,index=d.index)

def test_all_strategies_causal():
    d = prices()
    before,after = signals(d.iloc[:300]), signals(d)
    assert len(before)>=27
    for n in before:
        for i in (0,1):
            pd.testing.assert_series_equal(before[n][i],after[n][i].iloc[:300])

def test_execution_next_open_and_financing():
    d = prices(5)
    e,x = flags(d)
    r = simulate(d,e,x,Config(stop=0))
    assert r['events'].iloc[0]['date']==d.index[1]
    assert (r['equity']['liquidités']>=0).all()
    assert r['events'].iloc[0]['prix']>d.open.iloc[1]
    assert r['fees']>0
    assert r['trades'].iloc[-1]['motif']=='fin : liquidation conventionnelle'

def test_stop_target_ambiguity():
    d=prices(3)
    d.iloc[:,:4]=100.
    d.loc[d.index[1],['high','low']]=[120,80]
    r=simulate(d,*flags(d),Config(stop=.05,target=.05,commission=0,spread=0,slippage=0))
    assert r['trades'].iloc[0]['prix_sortie']==95
    assert r['trades'].iloc[0]['pnl']<0

def test_gap_stop():
    d=prices(4)
    d.iloc[:,:4]=100.
    d.loc[d.index[2],['open','high','low','close']]=[80,82,78,80]
    r=simulate(d,*flags(d),Config(stop=.05,commission=0,spread=0,slippage=0))
    assert r['trades'].iloc[0]['prix_sortie']==80

def test_target_and_costs():
    d=prices(3)
    d.iloc[:,:4]=100.
    d.loc[d.index[1],'high']=110
    r=simulate(d,*flags(d),Config(stop=0,target=.05,commission=0,spread=0,slippage=0))
    assert r['trades'].iloc[0]['prix_sortie']==105
    expensive=simulate(d,*flags(d),Config(stop=0,target=.05,commission=.01,spread=.01,slippage=.01))
    assert metrics(expensive)[0]['capital_final']<metrics(r)[0]['capital_final']

def test_impossible_and_missing():
    d=prices(4)
    r=simulate(d,*flags(d),Config(minimum=1000))
    assert r['trades'].empty
    assert metrics(r)[0]['capital_final']==100
    e,x=flags(d)
    e[:]=False
    e.iloc[0]=True
    d=d.drop(d.index[1])
    assert simulate(d,e,x)['trades'].empty

def test_invalid_data_and_risk():
    d=prices(4)
    d.iloc[1,0]=np.nan
    with pytest.raises(ValueError): clean(d)
    with pytest.raises(ValueError): Config(mode='risque',stop=0).validate()
    with pytest.raises(ValueError): Config(size=2).validate()

def test_cash_and_nonexecutable():
    d=prices(10)
    lib=signals(d)
    r=simulate(d,*lib['Liquidités'][:2])
    m,_,_=metrics(r)
    assert m['capital_final']==100 and m['profit_factor'] is None and m['trades']==0
    assert simulate(d,*flags(d),Config(executable=False))['trades'].empty

def test_manual_validation():
    d=prices()
    rule={'entry':{'mode':'ET','conditions':[{'left':'EMA20','op':'>','right':'EMA50'}]},'exit':{'mode':'OU','conditions':[{'left':'RSI14','op':'<','right':40}]}}
    assert len(custom_signals(d,rule)[0])==len(d)
    rule['entry']['conditions'][0]['left']='__import__("os")'
    with pytest.raises(ValueError): custom_signals(d,rule)

def test_accounting():
    d=prices()
    for name,(en,ex,_) in signals(d).items():
        r=simulate(d,en,ex)
        assert abs(r['equity'].capital.iloc[-1]-100-(r['trades'].pnl.sum() if len(r['trades']) else 0))<1e-7,name
        assert r['equity']['liquidités'].min()>=0

def test_physical_currency_conversion():
    from strategylab.instruments import physical_usdjpy
    d=prices(5)
    d.iloc[:,:4]=150
    inverse=physical_usdjpy(d)
    r=simulate(inverse,*flags(inverse),Config(stop=0,commission=0,spread=0,slippage=0,step=1,minimum=1))
    # Le taux inverse flottant est arrondi prudemment, sans créditer un yen non finançable.
    assert 14999<=r['events'].iloc[0]['quantité']<=15000
    assert abs(r['equity'].capital.iloc[-1]-100)<1e-9

def test_oos_and_walk_forward():
    from strategylab.validation import evaluate,walk_forward
    d=prices(1096)
    s=signals(d)['Liquidités']
    m,*_=evaluate(d,s,Config())
    assert m['oos_pct']==0
    wf=walk_forward(d,s,Config())
    assert len(wf)==2 and (wf.capital_final==100).all()

def test_fraction_and_risk_sizes():
    d=prices(4)
    d.iloc[:,:4]=100
    for cfg,expected in [(Config(mode='fraction',size=.5,stop=.1),50),(Config(mode='montant',size=20),20),(Config(mode='risque',size=.01,stop=.1,commission=0,spread=0,slippage=0),10)]:
        r=simulate(d,*flags(d),cfg)
        first=r['events'].iloc[0]
        assert first['quantité']*first['prix']+first['frais']<=expected+1e-8

def test_trailing_uses_previous_bar_only():
    d=prices(4)
    d.iloc[:,:4]=100
    d.loc[d.index[1],['high','low','close']]=[120,99,115]
    d.loc[d.index[2],['open','high','low','close']]=[110,112,100,105]
    r=simulate(d,*flags(d),Config(stop=0,trailing=.1,commission=0,spread=0,slippage=0))
    assert r['trades'].iloc[0]['sortie']==d.index[2]
    assert r['trades'].iloc[0]['prix_sortie']==108

def test_atr_trailing_is_not_retroactive():
    d=prices(30)
    d.loc[:,'open']=100.
    d.loc[:,'high']=101.
    d.loc[:,'low']=99.
    d.loc[:,'close']=100.
    d.loc[d.index[20],['high','low','close']]=[120,99,115]
    d.loc[d.index[21],['open','high','low','close']]=[108,110,100,105]
    en,ex=flags(d)
    en[:]=False
    en.iloc[19]=True
    r=simulate(d,en,ex,Config(stop=0,atr_multiple=3,commission=0,spread=0,slippage=0))
    assert r['trades'].iloc[0]['entrée']==d.index[20]
    assert r['trades'].iloc[0]['sortie']==d.index[21]
    assert r['trades'].iloc[0]['prix_sortie']==108
