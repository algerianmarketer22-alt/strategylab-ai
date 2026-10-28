from .data import clean
import requests
import pandas as pd

def binance_filters(symbol):
    if symbol not in ('BTCUSDT','ETHUSDT'):
        raise ValueError('Symbole non autorisé.')
    r=requests.get('https://api.binance.com/api/v3/exchangeInfo',params={'symbol':symbol},timeout=15)
    r.raise_for_status()
    instrument=r.json()['symbols'][0]
    if instrument['symbol']!=symbol or instrument['status']!='TRADING' or not instrument.get('isSpotTradingAllowed',False):
        raise ValueError('Instrument spot non négociable selon la réponse publique.')
    filters={x['filterType']:x for x in instrument['filters']}
    lot=filters['LOT_SIZE']
    notional=filters.get('NOTIONAL',filters.get('MIN_NOTIONAL'))
    if not notional:
        raise ValueError('Minimum notionnel indisponible.')
    return {'minimum':float(notional['minNotional']),'step':float(lot['stepSize']),'min_qty':float(lot['minQty']),
            'source':'https://api.binance.com/api/v3/exchangeInfo?symbol='+symbol,'vérifié_utc':str(pd.Timestamp.now(tz='UTC'))}

def physical_usdjpy(data):
    """Valorise les JPY détenus en USD : conversion USD -> JPY, puis JPY -> USD."""
    d = clean(data)
    out = d.copy()
    out['open'] = 1/d.open
    out['close'] = 1/d.close
    out['high'] = 1/d.low
    out['low'] = 1/d.high
    return clean(out)
