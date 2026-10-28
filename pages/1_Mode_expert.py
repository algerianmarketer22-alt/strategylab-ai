import json
import html
import re
import hashlib
from dataclasses import asdict, replace
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from strategylab.data import download, import_csv, quality
from strategylab.strategies import signals, indicators, custom_signals, RISK_OVERRIDES
from strategylab.simulation import Config, simulate
from strategylab.statistics import metrics
from strategylab.validation import evaluate, walk_forward
from strategylab.storage import saved, save, record
from strategylab.instruments import physical_usdjpy, binance_filters

st.set_page_config(page_title='StrategyLab AI', page_icon='📊', layout='wide')
st.page_link('app.py', label='← Retour aux stratégies prêtes à tester')
st.title('StrategyLab AI — Mode expert')
st.caption('Laboratoire local • spot sans emprunt • aucune connexion de courtage')
st.warning('Une performance historique positive ne garantit aucun gain futur. USD et USDT sont distincts : aucun taux 1:1 implicite.')
with st.sidebar:
    st.header('Marché et données')
    market = st.selectbox('Marché', ['BTC/USDT','ETH/USDT','XAU/USD','EUR/USD','USD/JPY'])
    interval = st.selectbox('Unité', ['1d','4h','1h'], format_func=lambda x:{'1d':'D1','4h':'H4','1h':'H1'}[x])
    today = pd.Timestamp.now(tz='UTC').normalize()
    dates = st.date_input('Période (fin exclusive)', (today.date()-pd.DateOffset(years=3), today.date()))
    currency = 'USDT' if market.endswith('USDT') else 'USD'
    capital = st.number_input(f'Capital initial ({currency})',min_value=1.,value=100.)
    st.header('Exécution et risque')
    mode = st.selectbox('Taille', ['fraction','risque','montant'],format_func=lambda x:{'fraction':'Fraction des liquidités','risque':'Capital risqué jusqu’au stop','montant':'Montant fixe'}[x])
    size = st.number_input('Taille (% ou montant selon mode)',min_value=0.01,value=100. if mode=='fraction' else 1.)
    stop = st.number_input('Stop-loss (%) ; 0 = désactivé',min_value=0.,max_value=99.,value=5.)
    target = st.number_input('Take-profit (%) ; 0 = désactivé',min_value=0.,max_value=99.,value=0.)
    trailing = st.number_input('Stop suiveur (%) ; 0 = désactivé',min_value=0.,max_value=99.,value=0.)
    commission = st.number_input('Commission par côté (%)',min_value=0.,max_value=99.,value=0.1,format='%.4f')
    spread = st.number_input('Spread total (%)',min_value=0.,max_value=99.,value=0.02,format='%.4f')
    slippage = st.number_input('Slippage par côté (%)',min_value=0.,max_value=99.,value=0.01,format='%.4f')
    if market.endswith('USDT') and st.button('Lire les règles spot actuelles (API publique)'):
        try:
            st.session_state['filters_'+market] = binance_filters(market.replace('/',''))
        except Exception as e:
            st.error('Règles indisponibles : '+str(e))
    filters = st.session_state.get('filters_'+market,{})
    minimum = st.number_input('Minimum notionnel (devise de cotation)',min_value=0.,value=filters.get('minimum',5.))
    step = st.number_input('Incrément de quantité (actif de base)',min_value=0.00000001,value=filters.get('step',0.00001),format='%.8f')
    min_qty = st.number_input('Quantité minimale',min_value=0.,value=filters.get('min_qty',0.),format='%.8f')
    if filters:
        st.caption(f"Source vérifiée {filters['vérifié_utc']} : règles actuelles, validité historique non établie.")
    st.caption('Minimums et incréments ci-dessus : hypothèses utilisateur, pas règles Binance certifiées historiques. Modèle de coûts constant, sans carnet d’ordres.')
    cfg = Config(capital=capital,commission=commission/100,spread=spread/100,slippage=slippage/100,stop=stop/100,target=target/100,trailing=trailing/100,mode=mode,size=size if mode=='montant' else size/100,minimum=minimum,step=step,min_qty=min_qty,interval=interval,executable=market.endswith('USDT'))

data_tab, edit_tab, result_tab, help_tab = st.tabs(['Données','Constructeur','Comparaison','Méthode'])
key = (market,interval)
with data_tab:
    if market.endswith('USDT'):
        st.info('Archives spot Binance publiques, bougies terminées en UTC. Les archives indisponibles sont signalées, jamais remplacées.')
        if st.button('Télécharger / charger le cache'):
            bar = st.progress(0.)
            try:
                if len(dates)!=2:
                    raise ValueError('Sélectionnez deux dates.')
                d, meta = download(market.replace('/',''), interval,*dates,progress=bar.progress)
                st.session_state['dataset'] = (key,d,meta)
            except Exception as e:
                st.error(f'Données indisponibles : {e}')
    else:
        st.warning(f'NON EXÉCUTABLE AVEC {capital:g} USD tant que l’instrument et ses règles ne sont pas documentés. Forex : conversion physique uniquement, sans financement emprunté. Or : XAU/USD seul est un prix de référence ; aucun CFD assimilé à du métal détenu.')
    upload = st.file_uploader('Importer un CSV OHLCV réel (aucun exemple synthétique)',type=['csv'])
    if upload:
        sep = st.selectbox('Séparateur',[',',';','\t'])
        decimal = st.selectbox('Séparateur décimal',['.',','])
        timezone = st.text_input('Fuseau des dates naïves','UTC')
        source = st.text_input('Source et instrument exact du CSV')
        instrument_source = st.text_input('Source des conditions de transaction (URL ou référence de document)') if not market.endswith('USDT') else ''
        physical = st.checkbox('Je confirme : instrument au comptant réellement négociable, propriété des devises ou du métal, aucun CFD ni emprunt ; minimum et incrément renseignés selon le document cité') if not market.endswith('USDT') else False
        if market=='USD/JPY':
            st.info('Conversion physique : les USD achètent des JPY. Simulation et indicateurs sur 1/(USD/JPY), en USD par JPY ; quantité en JPY. Minimum notionnel en USD. Le volume CSV reste un filtre de volume, sans conversion artificielle.')
        elif market=='XAU/USD':
            st.info('Sans confirmation documentée, le CSV reste une référence non exécutable. Avec confirmation, prix requis en USD par once troy d’or réellement détenu ; incrément et minimum du produit physique, pas ceux d’un CFD.')
        try:
            upload.seek(0)
            columns = list(pd.read_csv(upload,sep=sep,nrows=0).columns)
            mapping = {}
            cols = st.columns(3)
            for i,k in enumerate(['date','open','high','low','close','volume']):
                mapping[k] = cols[i%3].selectbox(k,columns,index=columns.index(k) if k in columns else 0)
            if st.button('Valider l’import'):
                if not source.strip():
                    raise ValueError('Renseignez la provenance réelle des données.')
                upload.seek(0)
                d = import_csv(upload,mapping,timezone,decimal,sep)
                if len(dates)==2:
                    d = d.loc[(d.index>=pd.Timestamp(dates[0],tz='UTC'))&(d.index<pd.Timestamp(dates[1],tz='UTC'))]
                if d.empty:
                    raise ValueError('Aucune bougie dans la période.')
                if physical and not instrument_source.strip():
                    raise ValueError('Citez les conditions de transaction pour activer une simulation physique.')
                if market=='USD/JPY':
                    d = physical_usdjpy(d)
                st.session_state['dataset'] = (key,d,{'source':source,'conditions instrument':instrument_source,'physique déclaré par utilisateur':physical,'devise du capital':currency,'unité prix':'USD par JPY (inverse)' if market=='USD/JPY' else market,**quality(d,interval)})
        except Exception as e:
            st.error(str(e))
    dataset = st.session_state.get('dataset')
    if dataset and dataset[0]==key:
        st.json(dataset[2])
        st.dataframe(dataset[1].tail(10))

dataset = st.session_state.get('dataset')
d = dataset[1] if dataset and dataset[0]==key else None
with edit_tab:
    st.subheader('Règles visuelles sans code')
    st.caption('Une position maximum. SMA, EMA, RSI et ROC : périodes configurables de 2 à 500. Les stops de la barre latérale sont sauvegardés avec la règle.')
    rules = saved()
    selected = st.selectbox('Stratégie à modifier ou dupliquer',['Nouvelle']+list(rules))
    default = {'entry':{'mode':'ET','conditions':[{'left':'EMA20','op':'croise au-dessus','right':'EMA50'}]},'exit':{'mode':'ET','conditions':[{'left':'EMA20','op':'croise au-dessous','right':'EMA50'}]}}
    base = rules.get(selected,default)
    if 'risk' in base:
        st.caption('Stops sauvegardés : '+str(base['risk']))
    name = st.text_input('Nom (changer pour dupliquer)',selected if selected!='Nouvelle' else 'Ma stratégie')
    schema = pd.DataFrame({k:pd.Series(dtype=float) for k in ['open','high','low','close','volume']},index=pd.DatetimeIndex([],tz='UTC'))
    available = list(indicators(schema).columns)
    rule = {}
    for side,label in [('entry','Entrée'),('exit','Sortie')]:
        st.markdown(f'**{label}**')
        old = base[side]
        mode_group = st.selectbox('Combinaison',['ET','OU'],index=['ET','OU'].index(old['mode']),key=f'{selected}{side}mode')
        count = st.number_input('Nombre de conditions',1,10,len(old['conditions']),key=f'{selected}{side}count')
        conditions = []
        for i in range(count):
            previous = old['conditions'][min(i,len(old['conditions'])-1)]
            a,b,c = st.columns(3)
            options = list(dict.fromkeys(available+[previous['left']]))
            left = a.selectbox('Indicateur',options,index=options.index(previous['left']),key=f'{selected}{side}{i}a')
            match = re.fullmatch(r'(SMA|EMA|RSI|ROC)([0-9]+)',left)
            if match:
                period = a.number_input('Période',2,500,int(match[2]),key=f'{selected}{side}{i}period')
                left = match[1]+str(period)
            ops = ['>','<','croise au-dessus','croise au-dessous']
            op = b.selectbox('Relation',ops,index=ops.index(previous['op']),key=f'{selected}{side}{i}b')
            right = c.text_input('Indicateur ou seuil numérique',str(previous['right']),key=f'{selected}{side}{i}c')
            conditions.append({'left':left,'op':op,'right':right})
        rule[side] = {'mode':mode_group,'conditions':conditions}
    riskcols = st.columns(3)
    rule['risk'] = {}
    for col,k,label in zip(riskcols,['stop','target','trailing'],['Stop manuel (%)','Objectif manuel (%)','Suiveur manuel (%)']):
        rule['risk'][k] = col.number_input(label,0.,99.,float(base.get('risk',{}).get(k,getattr(cfg,k))*100),key=f'{selected}{k}manual')/100
    if st.button('Enregistrer / dupliquer'):
        try:
            probe = d if d is not None else schema
            custom_signals(probe,rule)
            save(name,rule)
            st.success('Stratégie sauvegardée dans SQLite.')
        except Exception as e:
            st.error(str(e))
    st.download_button('Exporter les règles JSON',json.dumps(rule,ensure_ascii=False,indent=2),'strategie.json','application/json')

with result_tab:
    if d is None:
        st.info('Chargez d’abord des données réelles dans l’onglet Données.')
    else:
        library = signals(d)
        for n,r in saved().items():
            library['Manuelle : '+n] = custom_signals(d,r)
        chosen = st.multiselect('Stratégies',list(library),default=['SMA 20/50','EMA 9/21','MACD','RSI momentum','Donchian 20','Achat-conservation','Liquidités'])
        phase = st.radio('Phase de recherche',['Exploration : 24 premiers mois','Validation : réglages gelés'],horizontal=True)
        boundary = d.index[0]+pd.DateOffset(months=24)
        fingerprint = hashlib.sha256(pd.util.hash_pandas_object(d,index=True).values.tobytes()).hexdigest()
        spec = hashlib.sha256(json.dumps({'data':fingerprint,'marché':market,'configuration':asdict(cfg),'stratégies':chosen,'règles':saved(),'instrument':dataset[2]},sort_keys=True,default=str).encode()).hexdigest()
        if st.button('Geler les réglages après exploration'):
            if st.session_state.get('explored_spec')!=spec:
                st.error('Exécutez d’abord l’exploration avec ces réglages et cette sélection.')
            else:
                st.session_state['frozen_spec'] = spec
                st.success('Réglages gelés. Vous pouvez sélectionner la phase Validation.')
        st.caption('Après consultation des résultats de validation, toute nouvelle sélection doit être considérée exploratoire ; un nouveau test indépendant exige de nouvelles données.')
        sensitivity = st.checkbox('Sensibilité : périodes SMA/EMA ±1, paramètres non sélectionnés sur ces résultats',value=True)
        windows = st.checkbox('Fenêtres walk-forward de 6 mois après 24 mois, paramètres gelés',value=False)
        st.caption('Paramètres prédéfinis et gelés. Aucun ajustement automatique sur les 12 derniers mois. Validation stricte seulement avec 36 mois continus ; sinon classement insuffisamment validé.')
        if st.button('Lancer les backtests',type='primary'):
            try:
                cfg.validate()
                if phase.startswith('Validation') and st.session_state.get('frozen_spec')!=spec:
                    raise ValueError('Les réglages doivent être explorés puis gelés avant validation. Toute modification exige une nouvelle exploration.')
                run_data = d.loc[d.index<boundary] if phase.startswith('Exploration') else d
                if interval!='1d' and (d.index[-1]-d.index[0]<pd.Timedelta(days=1094) or quality(d,interval)['ruptures']):
                    raise ValueError('H1/H4 exige trois ans de couverture continue vérifiable.')
                rows,results = [],{}
                variants = {delta:signals(d,delta) for delta in (-1,1)} if sensitivity else {}
                bar = st.progress(0.)
                st.caption('Annuler : bouton Arrêter de Streamlit en haut à droite ; résultats publiés uniquement quand le lot est terminé.')
                for i,n in enumerate(chosen):
                    run_cfg = replace(cfg,executable=cfg.executable or dataset[2].get('physique déclaré par utilisateur',False))
                    run_cfg = replace(run_cfg,**RISK_OVERRIDES.get(n,{}))
                    if n in ('Achat-conservation','Liquidités'):
                        run_cfg = replace(run_cfg,stop=0,target=0,trailing=0,mode='fraction',size=1)
                        if n=='Liquidités':
                            run_cfg = replace(run_cfg,executable=True)
                    elif n.startswith('Manuelle : '):
                        run_cfg = replace(run_cfg,**saved()[n[len('Manuelle : '):]].get('risk',{}))
                    m,r,monthly,annual,oos = evaluate(run_data,library[n],run_cfg)
                    r['data_metadata'] = dataset[2]
                    r['rule_documentation'] = library[n][2]
                    if sensitivity and n in library and not n.startswith('Manuelle : ') and n not in ('Achat-conservation','Liquidités'):
                        for delta in (-1,1):
                            variant = simulate(run_data,*variants[delta][n][:2],run_cfg)
                            m[f'rendement_MA_{delta:+d}_pct'] = metrics(variant)[0]['rendement_pct']
                    if windows:
                        r['walk_forward'] = walk_forward(run_data,library[n],run_cfg)
                    rows.append({'stratégie':n,**m})
                    results[n]=(r,monthly,annual,oos,library[n][2])
                    bar.progress((i+1)/len(chosen),text=n)
                frame = pd.DataFrame(rows)
                if frame.empty:
                    raise ValueError('Sélectionnez au moins une stratégie.')
                record({'phase':phase,'gel':spec,'marché':market,'devise':currency,'données':dataset[2],'empreinte_bougies':fingerprint,'configuration':asdict(cfg),'règles':saved(),'résultats':rows},results)
                st.session_state['results'] = (key,frame,results,run_data,currency,asdict(cfg))
                if phase.startswith('Exploration'):
                    st.session_state['explored_spec'] = spec
            except Exception as e:
                st.error(f'Simulation interrompue : {e}')
        bundle = st.session_state.get('results')
        if bundle and bundle[0]==key:
            _,frame,results,rd,unit,used_cfg = bundle
            st.caption(f'Résultats du dernier lot enregistré en {unit}. Ils conservent leurs réglages même si la barre latérale change.')
            with st.expander('Configuration réellement simulée'):
                st.json(used_cfg)
            cats = st.multiselect('Filtrer les catégories',frame['catégorie'].unique(),default=list(frame['catégorie'].unique()))
            view = frame[frame['catégorie'].isin(cats)].sort_values('score_prudent',ascending=False,na_position='last')
            st.dataframe(view,hide_index=True,width='stretch')
            st.caption('Score prudent = rendement OOS − drawdown OOS (points). Au moins 10 trades OOS requis pour « prometteuse ». Robustesse aux frais affichée séparément. Benchmarks : 100% financé, stops désactivés. Ce classement ne constitue pas une recommandation.')
            st.download_button('Exporter le classement CSV',frame.to_csv(index=False).encode('utf-8-sig'),'classement.csv')
            name_result = st.selectbox('Détail',list(results))
            r,monthly,annual,oos,doc = results[name_result]
            st.info(doc)
            st.json(r['config'],expanded=False)
            if 'walk_forward' in r:
                st.subheader('Fenêtres walk-forward : règles gelées, capital réinitialisé')
                st.dataframe(r['walk_forward'])
            equity = r['equity'].capital
            st.plotly_chart(go.Figure(go.Scatter(x=equity.index,y=equity,name=f'Capital {unit}')).update_layout(title='Courbe de capital'),width='stretch')
            drawdown = equity/equity.cummax().clip(lower=used_cfg['capital'])-1
            st.plotly_chart(go.Figure(go.Scatter(x=drawdown.index,y=drawdown*100,fill='tozeroy')).update_layout(title='Drawdown (%)'),width='stretch')
            st.bar_chart(monthly*100)
            st.dataframe((annual*100).rename('Performance annuelle (%)'))
            fig = go.Figure(go.Candlestick(x=rd.index,open=rd.open,high=rd.high,low=rd.low,close=rd.close,name='OHLC réel'))
            for kind,symbol in [('achat','triangle-up'),('vente','triangle-down')]:
                events = r['events']
                if len(events):
                    subset = events[events.type==kind]
                    if len(subset):
                        fig.add_trace(go.Scatter(x=subset.date,y=subset.prix,mode='markers',name=kind,marker_symbol=symbol,marker_size=10))
            st.plotly_chart(fig,width='stretch')
            st.subheader('Journal des ordres, exécutions et rejets')
            st.dataframe(r['events'],hide_index=True)
            st.subheader('Transactions clôturées')
            st.dataframe(r['trades'],hide_index=True)
            st.download_button('Journal CSV',r['events'].to_csv(index=False).encode('utf-8-sig'),'journal.csv')
            report = '<html lang="fr"><meta charset="utf-8"><title>StrategyLab AI</title><h1>Rapport historique</h1><p>Aucune garantie future. '+html.escape(unit)+' ; aucune conversion USD/USDT.</p><p>'+html.escape(doc)+'</p><pre>'+html.escape(json.dumps({'configuration':r['config'],'données':r.get('data_metadata',{})},ensure_ascii=False,indent=2))+'</pre>'+frame.to_html(index=False)+go.Figure(go.Scatter(x=equity.index,y=equity)).to_html(full_html=False,include_plotlyjs=True)+fig.to_html(full_html=False,include_plotlyjs=False)+monthly.rename('rendement mensuel').to_frame().to_html()+annual.rename('rendement annuel').to_frame().to_html()+r['events'].to_html(index=False)+r['trades'].to_html(index=False)+'</html>'
            st.download_button('Rapport HTML',report.encode('utf-8'),'rapport.html','text/html')

with help_tab:
    st.markdown('''### Hypothèses contrôlables
Signaux à clôture, ordres à l’ouverture suivante uniquement si bougies consécutives. Une position long maximum, frais inclus dans le financement. Fractions arrondies vers le bas. Spread moitié par côté et slippage défavorable. Stop et objectif calculés sur le prix exécuté. Stop prioritaire si les deux sont touchés. Gap stop exécuté au prix d’ouverture défavorable ; objectif au prix limite prudent. Stop suiveur révisé pour la bougie suivante. Liquidation conventionnelle finale explicitement journalisée.

Les lacunes ne sont jamais remplies. Aucun ordre d’entrée issu d’un signal avant une lacune ; une position existante reste valorisée, son stop est exécuté au premier prix disponible si traversé. Cette incertitude interdit la validation OOS stricte. Pas de spread historique reconstitué, de dividendes, ni de rendement des liquidités.

24 mois d’exploration puis 12 mois hors échantillon : même définition gelée et indicateurs réchauffés sur le passé ; chaque segment démarre en liquidités. La valeur annualisée est absente pour les périodes de moins d’un an. Profit factor sans perte : non défini, jamais infini. Les benchmarks sont soumis aux mêmes coûts et tailles mais doivent être lancés sans stops pour une conservation pure.

Forex et or : ordres bloqués par défaut. L’import peut activer la conversion physique après déclaration explicite des conditions de transaction par l’utilisateur ; cette déclaration n’est pas une certification automatique. EUR/USD achète des EUR contre USD. USD/JPY est inversé pour acheter et valoriser des JPY en USD, sans emprunter. XAU/USD exige un prix effectivement négociable d’or détenu, pas un simple prix de référence. Aucun CFD n’est utilisé.

Limites actuelles : pas d’optimisation massive, pas de règles historiques de lot certifiées, pas d’IA prédictive. La sensibilité aux frais est calculée ; la sensibilité paramétrique doit être comparée avec les variantes du constructeur. Les résultats restent de la recherche historique.
''')

