import json
import sqlite3
import zlib
from pathlib import Path
from .paths import DATA

def connect():
    DATA.mkdir(parents=True,exist_ok=True)
    db = sqlite3.connect(DATA / 'strategylab.sqlite')
    db.execute('CREATE TABLE IF NOT EXISTS strategies (name TEXT PRIMARY KEY, rule TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS artifacts (run_id INTEGER NOT NULL, strategy TEXT NOT NULL, kind TEXT NOT NULL, content BLOB NOT NULL)')
    return db

def saved():
    with connect() as db:
        return {n:json.loads(r) for n,r in db.execute('SELECT name,rule FROM strategies ORDER BY name')}

def save(name, rule):
    if not name.strip() or len(name)>100:
        raise ValueError('Nom requis, 100 caractères maximum.')
    with connect() as db:
        db.execute('INSERT INTO strategies VALUES (?,?) ON CONFLICT(name) DO UPDATE SET rule=excluded.rule',(name,json.dumps(rule,allow_nan=False)))

def record(payload, results=None):
    with connect() as db:
        run_id = db.execute('INSERT INTO runs(payload) VALUES (?)',(json.dumps(payload,allow_nan=False,default=str),)).lastrowid
        for name,value in (results or {}).items():
            result=value[0]
            db.execute('INSERT INTO artifacts VALUES (?,?,?,?)',(run_id,name,'configuration',zlib.compress(json.dumps({'configuration':result['config'],'logique':result.get('rule_documentation','')},ensure_ascii=False,allow_nan=False).encode('utf-8'))))
            for kind in ('equity','events','trades'):
                blob=zlib.compress(result[kind].to_json(orient='split',date_format='iso').encode('utf-8'))
                db.execute('INSERT INTO artifacts VALUES (?,?,?,?)',(run_id,name,kind,blob))
