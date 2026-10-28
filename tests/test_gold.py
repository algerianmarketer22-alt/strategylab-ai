from dataclasses import replace
import pandas as pd
import pytest
from strategylab.gold import prior_rates, in_euros
from strategylab.simulation import Config, simulate

def test_bce_uses_only_prior_rate():
    rates=pd.Series([1.1,1.2],index=pd.to_datetime(['2024-01-04','2024-01-05'],utc=True))
    assert prior_rates(rates,pd.to_datetime(['2024-01-05'],utc=True)).iloc[0]==1.1
    with pytest.raises(ValueError): prior_rates(rates,pd.to_datetime(['2024-01-20'],utc=True))

def test_weekend_and_currency_accounting():
    dates=pd.to_datetime(['2024-01-05','2024-01-08','2024-01-09'],utc=True)
    d=pd.DataFrame({'open':[50,50,55],'high':[51,51,56],'low':[49,49,54],'close':[50,50,55],'volume':[100]*3},index=dates)
    e=pd.Series([True,False,False],index=dates)
    x=pd.Series(False,index=dates)
    rates=pd.Series([1.1,1.2],index=pd.to_datetime(['2024-01-04','2024-01-08'],utc=True))
    cfg=Config(capital=100*1.1*.999,calendar='XNYS',step=1,min_qty=1,minimum=0,stop=0,commission=0,spread=0,slippage=0)
    raw=simulate(d,e,x,cfg)
    assert raw['events'].iloc[0]['date']==dates[1]
    result=in_euros(raw,rates,100)
    c=result['conversion']
    assert result['equity'].capital.iloc[-1]==pytest.approx(100+c['résultat opérations en EUR au taux final']+c['effet du change en EUR']-c['coût des deux conversions en EUR au taux final'])
    assert (result['equity'].liquidités>=0).all()
