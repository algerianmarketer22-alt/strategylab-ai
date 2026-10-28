"""Prix réels du titre IAU et taux EUR/USD de référence BCE, sans compte."""
from io import StringIO
import hashlib
import json
import requests
import pandas as pd
import numpy as np
import exchange_calendars as xcals
from .data import clean, CACHE

IAU_DOCUMENT = 'https://www.ishares.com/us/literature/fact-sheet/iau-ishares-gold-trust-fund-fact-sheet-en-us.pdf'
FX_SOURCE = 'https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A'

def sessions(start, end):
    start,end = pd.Timestamp(start),pd.Timestamp(end)
    calendar = xcals.get_calendar('XNYS',start=(start-pd.Timedelta(days=30)).date(),end=(end+pd.Timedelta(days=30)).date())
    return pd.to_datetime(calendar.sessions_in_range(start.date(),end.date()),utc=True)

def cached_response(name,url,params):
    CACHE.mkdir(parents=True,exist_ok=True)
    path = CACHE/name
    digest = path.with_suffix(path.suffix+'.sha256')
    if path.exists() and digest.exists():
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest.read_text():
            raise ValueError('Cache corrompu : '+str(path))
        return raw
    response=requests.get(url,params=params,headers={'User-Agent':'StrategyLabAI local historical research'},timeout=30)
    response.raise_for_status()
    raw=response.content
    # Le hash local contrôle le cache, pas une signature officielle du fournisseur.
    path.write_bytes(raw)
    digest.write_text(hashlib.sha256(raw).hexdigest())
    return raw

def gold_data(end):
    end=pd.Timestamp(end)
    start=end-pd.DateOffset(years=4)
    url='https://query1.finance.yahoo.com/v8/finance/chart/IAU'
    raw=cached_response(f'IAU-{end.date()}.json',url,{'period1':int(start.timestamp()),'period2':int(end.timestamp()),'interval':'1d','events':'splits,div'})
    chart=json.loads(raw)['chart']
    if chart.get('error') or not chart.get('result'):
        raise ValueError('Historique IAU indisponible : '+str(chart.get('error')))
    payload=chart['result'][0]
    meta=payload['meta']
    if meta.get('symbol')!='IAU' or meta.get('currency')!='USD' or meta.get('exchangeName')!='PCX':
        raise ValueError('Instrument ou devise IAU inattendu.')
    if payload.get('events',{}).get('splits') or payload.get('events',{}).get('dividends'):
        raise ValueError('Opération sur titre détectée : traitement requis avant simulation, aucun ajustement inventé.')
    quotes=payload['indicators']['quote'][0]
    dates=pd.to_datetime(payload['timestamp'],unit='s',utc=True).tz_convert('America/New_York').date
    data=pd.DataFrame({k:quotes[k] for k in ('open','high','low','close','volume')},index=pd.to_datetime(dates,utc=True))
    data=clean(data.loc[data.index<end])
    expected=sessions(data.index[0],end-pd.Timedelta(days=1))
    missing=expected.difference(data.index)
    if len(data.index.difference(expected)):
        raise ValueError('Dates hors calendrier de cotation dans les données IAU.')
    return data,{'source':url,'instrument':'IAU — iShares Gold Trust, titre coté NYSE Arca adossé à l’or physique ; distinct du prix XAU/USD','document instrument':IAU_DOCUMENT,'devise de cotation':'USD','calendrier':'XNYS (séances NYSE/Arca)','séances absentes':[str(x.date()) for x in missing],'début':str(data.index[0]),'fin':str(data.index[-1]),'bougies':len(data),'traitement':'OHLC non ajusté ; aucun split ni distribution détecté sur la période chargée'}

def fx_rates(end):
    end=pd.Timestamp(end)
    raw=cached_response(f'ECB-EURUSD-{end.date()}.csv',FX_SOURCE,{'startPeriod':str((end-pd.DateOffset(years=4)-pd.Timedelta(days=20)).date()),'endPeriod':str((end-pd.Timedelta(days=1)).date()),'format':'csvdata'})
    table=pd.read_csv(StringIO(raw.decode('utf-8-sig')))
    if not {'TIME_PERIOD','OBS_VALUE','CURRENCY','CURRENCY_DENOM'}<=set(table):
        raise ValueError('Format de taux BCE inattendu.')
    if not table.CURRENCY.eq('USD').all() or not table.CURRENCY_DENOM.eq('EUR').all():
        raise ValueError('Devise inattendue dans les taux BCE.')
    rates=pd.Series(pd.to_numeric(table.OBS_VALUE,errors='raise').to_numpy(),index=pd.to_datetime(table.TIME_PERIOD,utc=True)).sort_index()
    if rates.empty or rates.index.has_duplicates or not np.isfinite(rates).all() or (rates<=0).any():
        raise ValueError('Taux EUR/USD invalides.')
    return rates

def prior_rates(rates, dates):
    """Taux publié avant la journée : jamais le fixing du jour connu après l'ouverture."""
    dates=pd.DatetimeIndex(dates)
    locations=rates.index.searchsorted(dates,side='left')-1
    if (locations<0).any():
        raise ValueError('Taux BCE antérieur indisponible.')
    observed=rates.index[locations]
    if ((dates-observed)>pd.Timedelta(days=7)).any():
        raise ValueError('Taux BCE trop ancien ; conversion bloquée.')
    return pd.Series(rates.iloc[locations].to_numpy(),index=dates)

def in_euros(raw, rates, initial_eur, fee=.001):
    """Deux conversions explicites ; le portefeuille intermédiaire reste en USD."""
    if not 0<=fee<1 or initial_eur<=0:
        raise ValueError('Paramètres de conversion invalides.')
    out={**raw,'equity':raw['equity'].copy(),'trades':raw['trades'].copy(),'events':raw['events'].copy(),'config':{**raw['config'],'capital':initial_eur},'execution_config':raw['config']}
    daily=prior_rates(rates,out['equity'].index)
    first,last=float(daily.iloc[0]),float(daily.iloc[-1])
    if not np.isclose(raw['config']['capital'],initial_eur*first*(1-fee)):
        raise ValueError('Capital en USD incompatible avec la conversion initiale en EUR.')
    for column in ('capital','liquidités'):
        out['equity'][column]=out['equity'][column]/daily
    final_conversion=float(raw['equity'].capital.iloc[-1])/last*fee
    out['equity'].iloc[-1,out['equity'].columns.get_loc('capital')]-=final_conversion
    out['equity'].iloc[-1,out['equity'].columns.get_loc('liquidités')]-=final_conversion
    out['fees']=initial_eur*fee+final_conversion
    if len(out['events']):
        event_rates=prior_rates(rates,pd.DatetimeIndex(out['events']['date'])).to_numpy()
        out['events']['frais_usd']=out['events']['frais'] if 'frais' in out['events'] else np.nan
        out['events']['frais']=out['events']['frais_usd']/event_rates
        out['fees']+=float(out['events']['frais'].sum())
    if len(out['trades']):
        exit_rates=prior_rates(rates,pd.DatetimeIndex(out['trades']['sortie'])).to_numpy()
        out['trades']['pnl_usd']=out['trades']['pnl']
        out['trades']['pnl']=out['trades']['pnl_usd']/exit_rates
    pnl_usd=float(raw['equity'].capital.iloc[-1]-raw['config']['capital'])
    out['conversion']={'source':FX_SOURCE,'règle':'dernier taux BCE strictement antérieur à chaque journée ; taux de référence, pas un prix de change de courtier','USD pour 1 EUR au départ':first,'USD pour 1 EUR à la fin':last,'frais par conversion':fee,'résultat opérations en EUR au taux final':pnl_usd/last,'effet du change en EUR':initial_eur*(first/last-1),'coût des deux conversions en EUR au taux final':initial_eur*first*fee/last+final_conversion,'hypothèse':'capital converti en USD au départ ; liquidités restantes conservées en USD ; conversion finale en EUR, frais de change 0,1 % par côté'}
    return out
