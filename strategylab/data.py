from pathlib import Path
from io import BytesIO
import hashlib
import zipfile
import requests
import pandas as pd
import numpy as np
from .paths import DATA

CACHE = DATA / 'cache'
COLS = ['open', 'high', 'low', 'close', 'volume']

def clean(df):
    df = df.copy()
    df.index = pd.to_datetime(df.index, utc=True)
    df = df[COLS].apply(pd.to_numeric, errors='raise').sort_index()
    if df.index.has_duplicates:
        for _, group in df.groupby(level=0):
            if len(group.drop_duplicates()) > 1:
                raise ValueError('Bougies contradictoires pour une même date.')
        df = df[~df.index.duplicated()]
    if df.empty or df.index.hasnans or not np.isfinite(df.to_numpy()).all():
        raise ValueError('Données vides, manquantes ou non finies.')
    if ((df[COLS[:4]] <= 0).any(axis=1) | (df.volume < 0) | (df.high < df[COLS[:4]].max(axis=1)) | (df.low > df[COLS[:4]].min(axis=1))).any():
        raise ValueError('OHLCV incohérent.')
    return df

def quality(df, interval):
    step = pd.Timedelta(interval)
    gaps = df.index.to_series().diff().gt(step)
    return {'début': str(df.index.min()), 'fin': str(df.index.max()), 'bougies': len(df),
            'ruptures': int(gaps.sum()), 'bougies absentes': int(sum(max(0, int(x / step)-1) for x in df.index.to_series().diff().dropna()))}

def archive(symbol, interval, stamp, kind):
    name = f'{symbol}-{interval}-{stamp}.zip'
    url = f'https://data.binance.vision/data/spot/{kind}/klines/{symbol}/{interval}/{name}'
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    check = CACHE / (name + '.CHECKSUM')
    if not path.exists() or not check.exists():
        r = requests.get(url, timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        c = requests.get(url + '.CHECKSUM', timeout=30)
        c.raise_for_status()
        expected = c.text.split()[0]
        if hashlib.sha256(r.content).hexdigest() != expected:
            raise ValueError('Checksum Binance incorrect : ' + name)
        tmp = path.with_suffix('.tmp')
        tmp.write_bytes(r.content)
        tmp.replace(path)
        check.write_text(c.text)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != check.read_text().split()[0]:
        raise ValueError('Cache corrompu : ' + str(path))
    with zipfile.ZipFile(BytesIO(raw)) as z:
        if sum(x.file_size for x in z.infolist()) > 100_000_000:
            raise ValueError('Archive trop volumineuse.')
        df = pd.read_csv(z.open(z.namelist()[0]), header=None)
    ts = pd.to_numeric(df.iloc[:, 0], errors='coerce')
    df = df.loc[ts.notna()].copy()
    ts = ts.dropna()
    df.index = pd.to_datetime(np.where(ts > 1e14, ts / 1000, ts), unit='ms', utc=True)
    df = df.iloc[:, 1:6]
    df.columns = COLS
    return clean(df)

def download(symbol='BTCUSDT', interval='1d', start=None, end=None, progress=None):
    if symbol not in ('BTCUSDT', 'ETHUSDT') or interval not in ('1d', '4h', '1h'):
        raise ValueError('Marché ou unité non autorisé.')
    end = pd.Timestamp(end or pd.Timestamp.now(tz='UTC').normalize())
    end = end.tz_localize('UTC') if end.tzinfo is None else end.tz_convert('UTC')
    start = pd.Timestamp(start) if start is not None else end - pd.DateOffset(years=3)
    start = start.tz_localize('UTC') if start.tzinfo is None else start.tz_convert('UTC')
    if start >= end or end-start > pd.Timedelta(days=1097):
        raise ValueError('Période invalide : trois ans maximum, fin exclusive.')
    months = pd.date_range(start.normalize().replace(day=1), end, freq='MS')
    frames = []
    missing = []
    for i, month in enumerate(months):
        part = archive(symbol, interval, month.strftime('%Y-%m'), 'monthly') if month + pd.offsets.MonthBegin() <= end else None
        if part is not None:
            frames.append(part)
        else:
            for day in pd.date_range(max(start.normalize(), month), min(end-pd.Timedelta(days=1), month+pd.offsets.MonthEnd()), freq='D'):
                daily = archive(symbol, interval, day.strftime('%Y-%m-%d'), 'daily')
                if daily is None:
                    missing.append(str(day.date()))
                else:
                    frames.append(daily)
        if progress:
            progress((i+1)/len(months))
    if not frames:
        raise ValueError('Aucune donnée Binance disponible.')
    result = clean(pd.concat(frames))
    result = result.loc[(result.index >= start) & (result.index < end)]
    result.to_parquet(CACHE / f'{symbol}-{interval}.parquet')
    return result, {'source': 'Binance Public Data spot, UTC', 'archives absentes': missing, **quality(result, interval)}

def import_csv(file, mapping, timezone='UTC', decimal='.', sep=','):
    raw = pd.read_csv(file, sep=sep, decimal=decimal)
    dates = pd.to_datetime(raw[mapping['date']], errors='raise')
    dates = dates.dt.tz_localize(timezone, ambiguous='raise', nonexistent='raise') if dates.dt.tz is None else dates.dt.tz_convert('UTC')
    df = raw[[mapping[k] for k in COLS]].copy()
    df.columns = COLS
    df.index = pd.DatetimeIndex(dates)
    return clean(df)
