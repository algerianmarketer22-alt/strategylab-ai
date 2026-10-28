from io import BytesIO
import hashlib
import zipfile
import pandas as pd
import pytest
from strategylab import data

def test_archive_checksum_and_timestamp_precision(tmp_path,monkeypatch):
    monkeypatch.setattr(data,'CACHE',tmp_path)
    buf=BytesIO()
    # Deux formats successifs représentés uniquement par une fixture de test.
    with zipfile.ZipFile(buf,'w') as z:
        z.writestr('bars.csv','1735603200000,10,12,9,11,5\n1735689600000000,11,13,10,12,6\n')
    raw=buf.getvalue()
    class Response:
        status_code=200
        content=raw
        text=hashlib.sha256(raw).hexdigest()+'  archive.zip'
        def raise_for_status(self): pass
    calls=[]
    def get(url,timeout):
        calls.append(url)
        return Response()
    monkeypatch.setattr(data.requests,'get',get)
    d=data.archive('BTCUSDT','1d','2025-01','monthly')
    assert d.index[1]-d.index[0]==pd.Timedelta(days=1)
    data.archive('BTCUSDT','1d','2025-01','monthly')
    assert len(calls)==2
    next(tmp_path.glob('*.zip')).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='corrompu'):
        data.archive('BTCUSDT','1d','2025-01','monthly')

def test_csv_mapping_and_timezone():
    csv=BytesIO(b'date;o;h;l;c;v\n2024-01-01 12:00;10,5;12,0;9,0;11,0;8\n')
    m=dict(zip(['date','open','high','low','close','volume'],['date','o','h','l','c','v']))
    d=data.import_csv(csv,m,'Europe/Paris',',',';')
    assert d.open.iloc[0]==10.5
    assert d.index[0]==pd.Timestamp('2024-01-01 11:00',tz='UTC')

def test_duplicate_conflict_and_missing_date():
    d=pd.DataFrame({'open':[10,11],'high':[12,12],'low':[9,9],'close':[11,11],'volume':[1,1]},index=pd.to_datetime(['2024-01-01','2024-01-01'],utc=True))
    with pytest.raises(ValueError,match='contradictoires'): data.clean(d)
    d.index=pd.DatetimeIndex([pd.NaT,pd.Timestamp('2024-01-01',tz='UTC')])
    with pytest.raises(ValueError): data.clean(d)
