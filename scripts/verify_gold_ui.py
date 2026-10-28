from pathlib import Path
from streamlit.testing.v1 import AppTest

app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=120).run()
assert not app.exception
assert app.selectbox[0].value=='XAU/USD'
app.selectbox(key='strategy_choice').select('SMA 20/50').run()
next(x for x in app.button if x.label=='Effectuer la simulation').click().run(timeout=120)
assert not app.exception and not app.error, (app.exception,app.error)
assert len(app.metric)==1
assert '100.00 EUR' in app.metric[0].value
next(x for x in app.button if x.label=='Voir les détails de la simulation').click().run(timeout=120)
assert not app.exception and not app.error
print('IAU réel : simulation trois ans en EUR, résultat unique puis détails : OK')
