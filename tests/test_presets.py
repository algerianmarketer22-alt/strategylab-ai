from dataclasses import asdict, replace
import pandas as pd
import pytest
from strategylab.presets import catalogue, identity, bounds, configuration_table, PERIODS

def test_every_profile_has_exact_rules_and_valid_defaults():
    profiles=catalogue()
    assert len(profiles)==28
    for name,p in profiles.items():
        assert p['purpose'] and len(p['logic'])>20,name
        assert p['explanations'],name
        p['config'].validate()
        assert p['config'].capital==100
        assert p['config'].size==1
        assert identity(name,p['config'],p['config'])==(name,{})
        assert 'Capital initial' in configuration_table(p['config'],'USDT')
    assert profiles['ATR trailing']['config'].atr_multiple==3
    assert profiles['RSI retour moyenne']['config'].stop!=profiles['SMA 50/200']['config'].stop

@pytest.mark.parametrize('field,value', [('capital',200.),('size',.5),('stop',.02),('target',.1),('trailing',.03),('commission',.002),('spread',.0003),('slippage',.0002),('minimum',10.),('min_qty',.001),('step',.0001),('mode','montant'),('interval','4h'),('atr_multiple',2.)])
def test_each_setting_creates_a_reproducible_variant(field,value):
    ref=catalogue()['SMA 20/50']['config']
    cfg=replace(ref,**{field:value})
    name,changes=identity('SMA 20/50',cfg,ref)
    assert name.startswith('SMA 20/50 — Variante ')
    assert changes=={field:value}
    assert identity('SMA 20/50',cfg,ref)[0]==name
    assert identity('SMA 20/50',replace(cfg,capital=float(cfg.capital)),ref)[0]==name
    assert ref.stop==.08 and ref.capital==100

def test_periods_are_calendar_windows_not_approximate_days():
    for label,months in PERIODS.items():
        start,end=bounds(label,'2026-10-28')
        assert end==pd.Timestamp('2026-10-28',tz='UTC')
        assert start==end-pd.DateOffset(months=months)
    with pytest.raises(ValueError): bounds('5 ans','2026-10-28')
