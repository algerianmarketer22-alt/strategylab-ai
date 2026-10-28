"""Test d'intégration réseau explicite, aucun remplacement par des données factices."""
import json
import argparse
from dataclasses import replace
from pathlib import Path
from strategylab.data import download
from strategylab.strategies import signals, RISK_OVERRIDES
from strategylab.simulation import Config
from strategylab.validation import evaluate
from strategylab.paths import DATA

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--symbol',choices=['BTCUSDT','ETHUSDT'],default='BTCUSDT')
    args=parser.parse_args()
    d,meta=download(args.symbol)
    rows=[]
    library=signals(d)
    for name,signal in library.items():
        cfg=Config(stop=0) if name in ('Achat-conservation','Liquidités') else Config()
        cfg=replace(cfg,**RISK_OVERRIDES.get(name,{}))
        m,*_=evaluate(d,signal,cfg)
        rows.append({'stratégie':name,**m})
    report={'données':meta,'résultats':rows}
    DATA.mkdir(parents=True,exist_ok=True)
    (DATA/f'verification_{args.symbol}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
