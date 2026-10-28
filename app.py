import hashlib
import html
import json
from dataclasses import asdict, replace
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from strategylab.data import download, quality
from strategylab.presets import catalogue, bounds, identity, configuration_table, PERIODS
from strategylab.simulation import simulate
from strategylab.statistics import metrics
from strategylab.storage import record
from strategylab.strategies import signals
from strategylab.gold import gold_data, fx_rates, prior_rates, sessions, in_euros
from strategylab.explanation import explain

st.set_page_config(page_title='StrategyLab AI',page_icon='📊',layout='wide')
st.title('StrategyLab AI')
st.caption('Choisissez une stratégie, puis découvrez ce que votre capital serait devenu. Aucun ordre réel.')
profiles = catalogue()

def reset_settings():
    for key in list(st.session_state):
        if key.startswith('qcfg_'):
            del st.session_state[key]
    st.session_state['customize_profile'] = False

def choose_profile(name):
    st.session_state['strategy_choice'] = name
    reset_settings()

with st.sidebar:
    st.page_link('pages/1_Mode_expert.py',label='Mode expert : import CSV, constructeur et validation')
    st.caption('Historique réel, sans emprunt. USD, EUR et USDT sont des devises distinctes.')

market = st.selectbox('Marché',['XAU/USD','BTC/USDT','ETH/USDT','EUR/USD','USD/JPY'])
period = st.radio('Durée du backtest',list(PERIODS),horizontal=True)
selected = st.selectbox('Stratégie',list(profiles),index=None,placeholder='Choisissez une stratégie pour voir son fonctionnement',key='strategy_choice',on_change=reset_settings)
if selected is None:
    st.info('XAU/USD et trois ans sont présélectionnés. Choisissez une stratégie, lisez son fonctionnement, puis effectuez la simulation.')
    st.stop()

profile = profiles[selected]
reference = profile['config']
is_gold = market=='XAU/USD'
if is_gold:
    reference = replace(reference,minimum=0.,step=1.,min_qty=1.,calendar='XNYS')
currency = 'EUR' if is_gold else ('USDT' if market.endswith('USDT') else 'USD')
end = pd.Timestamp.now(tz='UTC').normalize()
start,end = bounds(period,end)
st.write(profile['purpose'])

customize = st.checkbox('Personnaliser les réglages : créer une variante',key='customize_profile')
config = reference
if customize:
    with st.expander('Réglages de la variante',expanded=True):
        st.button('Rétablir le profil de référence',on_click=reset_settings)
        a,b,c = st.columns(3)
        capital = a.number_input(f'Capital initial ({currency})',min_value=1.,value=float(reference.capital),key='qcfg_capital')
        modes = ['fraction','risque','montant']
        mode = b.selectbox('Mode de taille',modes,format_func=lambda x:{'fraction':'Fraction des liquidités','risque':'Risque jusqu’au stop','montant':'Montant fixe'}[x],key='qcfg_mode')
        size = c.number_input('Allocation / risque (%) ou montant fixe',min_value=.01,value=float(reference.size*100),key='qcfg_size')
        changes = {}
        for i,(field,label) in enumerate([('stop','Stop-loss fixe (%)'),('target','Take-profit fixe (%)'),('trailing','Stop suiveur (%)'),('commission','Commission par côté (%)'),('spread','Spread total (%)'),('slippage','Slippage par côté (%)')]):
            changes[field] = [a,b,c][i%3].number_input(label,min_value=0.,max_value=99.,value=float(getattr(reference,field)*100),format='%.4f',key='qcfg_'+field)/100
        changes['atr_multiple'] = a.number_input('Stop suiveur : multiplicateur ATR14',min_value=0.,max_value=100.,value=float(reference.atr_multiple),key='qcfg_atr_multiple')
        changes['minimum'] = b.number_input(f'Minimum notionnel ({currency})',min_value=0.,value=float(reference.minimum),key='qcfg_minimum')
        changes['step'] = c.number_input('Incrément de quantité',min_value=.00000001,value=float(reference.step),format='%.8f',key='qcfg_step')
        changes['min_qty'] = a.number_input('Quantité minimale',min_value=0.,value=float(reference.min_qty),format='%.8f',key='qcfg_min_qty')
        changes['interval'] = b.selectbox('Unité',['1d','4h','1h'],format_func=lambda x:{'1d':'D1','4h':'H4','1h':'H1'}[x],key='qcfg_interval')
        config = replace(reference,capital=capital,mode=mode,size=size if mode=='montant' else size/100,**changes)

active_name,changes = identity(selected,config,reference)
effective_logic = profile['logic']
if selected=='ATR trailing':
    effective_logic = 'Entrée : clôture au-dessus de l’EMA50. Sortie sur signal : clôture sous l’EMA50.'
    if config.atr_multiple:
        effective_logic += f' Stop ATR : {config.atr_multiple:g} × ATR14 Wilder sous le plus haut depuis l’entrée, jamais abaissé et actualisé pour la bougie suivante.'
if selected=='Achat-conservation' and any((config.stop,config.target,config.trailing,config.atr_multiple)):
    effective_logic = 'Variante à signal d’achat permanent : achat à la première ouverture négociable, sortie par les protections configurées ou à la fin. Après une sortie par stop ou objectif, une nouvelle entrée peut avoir lieu dès la bougie suivante. Ce n’est plus une conservation pure.'
st.caption(active_name)
if changes:
    st.warning('Variante personnalisée : le profil de référence reste intact. Chaque combinaison de réglages possède un nom distinct et reproductible.')
    labels = {'capital':'capital initial','size':'taille de position','mode':'mode de taille','stop':'stop-loss','target':'take-profit','trailing':'stop suiveur','atr_multiple':'multiplicateur ATR','commission':'commission','spread':'spread','slippage':'slippage','minimum':'minimum notionnel','step':'incrément','min_qty':'quantité minimale','interval':'unité'}
    st.caption('Réglages modifiés : '+', '.join(labels[k] for k in changes))
else:
    st.caption('Réglages du profil appliqués automatiquement.')
settings = configuration_table(config,currency)
with st.expander('Description détaillée de la stratégie et de ses réglages',expanded=st.session_state.get('quick_result') is None):
    st.write(effective_logic)
    for explanation in profile['explanations']:
        st.write(explanation)
    st.write('Signaux confirmés à la clôture, exécution à l’ouverture négociable suivante. Une seule position long, frais compris dans le financement. Stop prioritaire en cas d’ambiguïté intrabar. Liquidation conventionnelle finale. Les données antérieures disponibles préparent les indicateurs sans opération avant la période demandée.')
    st.dataframe(pd.DataFrame(settings.items(),columns=['Réglage','Valeur appliquée']),hide_index=True,width='stretch')
    if is_gold:
        st.write('Instrument : IAU — iShares Gold Trust, titre NYSE Arca adossé à l’or physique ; distinct du prix XAU/USD, sans CFD ni détention directe de lingots. Hypothèse : parts entières, minimum une part, aucun emprunt. Capital de 100 € converti en USD au départ puis reconverti en EUR à la fin, au dernier taux BCE connu avant la journée concernée, avec 0,1 % de frais par conversion. Les taux BCE sont des références, pas des prix de courtier. Les liquidités intermédiaires restent en USD. Disponibilité commerciale du titre selon le pays et le courtier non certifiée.')
    st.caption('Protections pédagogiques, coûts et minimums explicites, non optimisés et sans certification des conditions historiques d’un courtier. Aucune garantie future. Le protocole hors échantillon reste en mode expert.')
if is_gold:
    st.caption('Or simulé via IAU (iShares Gold Trust), coté en USD — résultat en euros avec taux BCE réels. Hypothèse : parts entières, aucun levier.')
specification = {'stratégie':active_name,'référence':selected,'marché':market,'durée':period,'début':str(start),'fin_exclusive':str(end),'configuration':asdict(config),'logique':effective_logic,'écarts':changes}
spec_key = hashlib.sha256(json.dumps(specification,sort_keys=True).encode()).hexdigest()
if not market.endswith('USDT') and not is_gold:
    st.warning(f'NON EXÉCUTABLE AVEC {config.capital:g} USD sans données et conditions d’instrument documentées. Utilisez le mode expert pour importer un CSV et déclarer les conditions d’une conversion physique ou d’un achat d’or détenu. Aucun CFD ni emprunt.')
if st.button('Effectuer la simulation',type='primary',disabled=not (market.endswith('USDT') or is_gold)):
    try:
        config.validate()
        if is_gold and (config.step < 1 or config.step % 1 or config.min_qty < 1):
            raise ValueError('IAU exige ici des parts entières : incrément et quantité minimale au moins égaux à une part.')
        bar = st.progress(0.,text='Chargement des vraies données Binance…')
        if is_gold:
            data,meta=gold_data(end)
            rates=fx_rates(end)
        else:
            data,meta = download(market.replace('/',''),config.interval,end=end,progress=lambda x:bar.progress(x*.5,text='Vérification des archives Binance…'))
        if config.interval!='1d' and (data.index[-1]-data.index[0]<pd.Timedelta(days=1094) or quality(data,config.interval)['ruptures']):
            raise ValueError('H1/H4 nécessite trois ans de couverture continue vérifiée.')
        available = data.loc[(data.index>=start)&(data.index<end)]
        if available.empty:
            raise ValueError('Aucune bougie réelle dans la période choisie.')
        expected=sessions(start,end-pd.Timedelta(days=1)) if is_gold else pd.date_range(start,end-pd.Timedelta(config.interval),freq=config.interval)
        if not available.index.equals(expected):
            raise ValueError('La couverture réelle ne permet pas la durée demandée. Aucune extrapolation : vérifiez la source dans le mode expert.')
        library = signals(data)
        results,rows = {},[]
        names = list(dict.fromkeys([selected,'Achat-conservation','Liquidités']))
        for i,name in enumerate(names):
            # Le profil choisi est respecté même si l'utilisateur personnalise un benchmark.
            cfg = config if name==selected else replace(config,stop=0,target=0,trailing=0,atr_multiple=0,mode='fraction',size=1)
            alias = active_name if name==selected else name+' (benchmark)'
            signal = library[name]
            if is_gold and name!='Liquidités':
                first_rate=float(prior_rates(rates,available.index[:1]).iloc[0])
                usd_cfg=replace(cfg,capital=cfg.capital*first_rate*(1-.001),size=cfg.size*first_rate*(1-.001) if cfg.mode=='montant' else cfg.size,minimum=cfg.minimum*first_rate)
                raw=simulate(data,*signal[:2],usd_cfg,start=start,end=end)
                result=in_euros(raw,rates,cfg.capital)
            else:
                result = simulate(data,*signal[:2],cfg,start=start,end=end)
            summary,monthly,annual = metrics(result)
            logic = effective_logic if name==selected else signal[2]
            result['rule_documentation'] = logic
            result['data_metadata'] = meta
            results[alias] = (result,monthly,annual,None,logic)
            rows.append({'stratégie':alias,**summary})
            bar.progress(.5+(i+1)/len(names)*.5,text=alias)
        frame = pd.DataFrame(rows)
        record({'parcours':'profil préconfiguré','scénario':specification,'source':meta,'empreinte_bougies':hashlib.sha256(pd.util.hash_pandas_object(data,index=True).values.tobytes()).hexdigest(),'résultats':rows},results)
        st.session_state['quick_result'] = {'spec':spec_key,'frame':frame,'results':results,'data':available,'source':meta,'scenario':specification}
    except Exception as error:
        st.error('Backtest impossible : '+str(error))

bundle = st.session_state.get('quick_result')
if bundle and bundle['spec']!=spec_key:
    st.info('Le scénario ou ses réglages ont changé. Relancez le backtest pour afficher les résultats correspondants.')
if bundle and bundle['spec']==spec_key:
    st.subheader('Résultat historique de ce scénario')
    frame,results = bundle['frame'],bundle['results']
    result,monthly,annual,_,logic = results[active_name]
    summary = frame.iloc[0]
    st.metric('Résultat de la simulation', f"{config.capital:.2f} {currency} → {summary['capital_final']:.2f} {currency}", delta=f"{summary['profit_net']:+.2f} {currency} ({summary['rendement_pct']:+.2f} %)")
    st.caption(f"{active_name} • {period} • {summary['trades']} transactions • du {summary['début'][:10]} au {summary['fin'][:10]}")
    if st.button('Voir les détails de la simulation'):
        st.session_state['detail_spec'] = spec_key
    if st.session_state.get('detail_spec') == spec_key:
        st.subheader('Comprendre le résultat')
        for line in explain(result, currency):
            st.write(line)
        st.dataframe(frame,hide_index=True,width='stretch')
        st.caption('Les benchmarks utilisent le même capital et les mêmes coûts, une allocation de 100 % et aucun stop. Si le profil choisi est lui-même un benchmark personnalisé, ses réglages sont respectés et son nom devient une variante.')
        equity = result['equity'].capital
        equity_fig = go.Figure(go.Scatter(x=equity.index,y=equity,name=f'Capital ({currency})')).update_layout(title='Évolution du capital')
        st.plotly_chart(equity_fig,width='stretch')
        drawdown = (equity/equity.cummax().clip(lower=config.capital)-1)*100
        st.plotly_chart(go.Figure(go.Scatter(x=drawdown.index,y=drawdown,fill='tozeroy')).update_layout(title='Baisse depuis le sommet du capital (%)'),width='stretch')
        st.bar_chart((monthly*100).rename('Rendement mensuel (%)'))
        st.dataframe((annual*100).rename('Rendement annuel (%)'))
        prices = bundle['data']
        candles = go.Figure(go.Candlestick(x=prices.index,open=prices.open,high=prices.high,low=prices.low,close=prices.close,name='Cours réel'))
        for side,symbol in [('achat','triangle-up'),('vente','triangle-down')]:
            if not result['events'].empty:
                executions = result['events'].loc[result['events'].type==side]
                if len(executions):
                    candles.add_trace(go.Scatter(x=executions.date,y=executions.prix,mode='markers',name=side,marker_symbol=symbol,marker_size=10))
        st.plotly_chart(candles,width='stretch')
        with st.expander('Journal complet, transactions et qualité des données'):
            st.json(bundle['source'])
            st.dataframe(result['events'],hide_index=True)
            st.dataframe(result['trades'],hide_index=True)
        report = '<!doctype html><html lang="fr"><meta charset="utf-8"><title>StrategyLab AI</title><h1>'+html.escape(active_name)+'</h1><p>'+html.escape(logic)+'</p><p>Backtest historique ; aucune garantie future ni validation hors échantillon implicite.</p><pre>'+html.escape(json.dumps(bundle['scenario'],ensure_ascii=False,indent=2))+'</pre>'+pd.DataFrame(settings.items(),columns=['Réglage','Valeur']).to_html(index=False)+frame.to_html(index=False)+equity_fig.to_html(full_html=False,include_plotlyjs=True)+candles.to_html(full_html=False,include_plotlyjs=False)+result['events'].to_html(index=False)+result['trades'].to_html(index=False)+'</html>'
        st.download_button('Exporter le résultat CSV',frame.to_csv(index=False).encode('utf-8-sig'),'resultat.csv')
        st.download_button('Exporter le journal CSV',result['events'].to_csv(index=False).encode('utf-8-sig'),'journal.csv')
        st.download_button('Télécharger le rapport HTML',report.encode('utf-8'),'rapport.html','text/html')
