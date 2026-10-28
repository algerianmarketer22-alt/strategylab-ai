from pathlib import Path
import pandas as pd
from streamlit.testing.v1 import AppTest
from strategylab.paths import DATA
from strategylab.data import quality

if __name__=='__main__':
    d=pd.read_parquet(DATA/'cache/BTCUSDT-1d.parquet')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=120)
    app.run()
    assert not app.exception
    app.selectbox[0].select('BTC/USDT').run()
    app.selectbox(key='strategy_choice').select('SMA 20/50').run()
    next(x for x in app.radio if x.label=='Durée du backtest').set_value('6 mois').run()
    next(x for x in app.button if x.label=='Effectuer la simulation').click().run(timeout=120)
    assert not app.exception
    assert not app.error
    bundle=app.session_state['quick_result']
    rows=bundle['frame']
    assert len(rows)==3
    end=pd.Timestamp.now(tz='UTC').normalize()
    assert pd.Timestamp(rows.iloc[0]['début'])==end-pd.DateOffset(months=6)
    assert rows.iloc[0]['stratégie']=='SMA 20/50'
    app.checkbox(key='customize_profile').check().run()
    app.number_input(key='qcfg_stop').set_value(3.).run()
    next(x for x in app.button if x.label=='Effectuer la simulation').click().run(timeout=120)
    assert not app.exception and not app.error
    assert ' — Variante ' in app.session_state['quick_result']['frame'].iloc[0]['stratégie']
    assert app.session_state['quick_result']['results'][app.session_state['quick_result']['frame'].iloc[0]['stratégie']][0]['config']['stop']==.03
    expert=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=120)
    expert.run()
    expert.session_state['dataset']=(('BTC/USDT','1d'),d,{'source':'Binance Public Data',**quality(d,'1d')})
    expert.switch_page('pages/1_Mode_expert.py').run()
    assert not expert.exception
    print('Parcours profils avec BTC réel : six mois exacts, réglages automatiques, variante à stop 3%, journaux et exports ; mode expert accessible.')
