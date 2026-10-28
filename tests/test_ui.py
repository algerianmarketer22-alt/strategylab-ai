from streamlit.testing.v1 import AppTest
from pathlib import Path

def test_page_starts():
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value=='StrategyLab AI'

def test_profile_selection_and_variant_reset():
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
    app.selectbox(key='strategy_choice').select('SMA 20/50').run()
    assert not app.exception
    assert app.radio[0].options==['3 ans','2 ans','1 an','6 mois']
    app.checkbox(key='customize_profile').check().run()
    assert app.number_input(key='qcfg_stop').value==8.
    app.number_input(key='qcfg_stop').set_value(3.).run()
    assert any('SMA 20/50 — Variante ' in x.value for x in app.caption)
    app.selectbox(key='strategy_choice').select('RSI retour moyenne').run()
    assert not app.checkbox(key='customize_profile').value
    assert not any('SMA 20/50 — Variante ' in x.value for x in app.caption)
    app.checkbox(key='customize_profile').check().run()
    assert app.number_input(key='qcfg_stop').value==4.
    assert app.number_input(key='qcfg_target').value==8.
    assert not app.exception
