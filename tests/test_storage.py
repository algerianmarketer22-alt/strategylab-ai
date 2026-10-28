from types import SimpleNamespace
import streamlit as st
from strategylab import storage


def test_linux_data_is_isolated_and_not_persisted(monkeypatch):
    first, second = {}, {}
    monkeypatch.setattr(storage, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setattr(st, 'session_state', first)
    monkeypatch.setattr(storage, 'connect', lambda: (_ for _ in ()).throw(AssertionError('SQLite shared')))
    storage.save('ma strategie', {'entry': 'test'})
    assert storage.saved() == {'ma strategie': {'entry': 'test'}}
    storage.record({'capital': 100})
    monkeypatch.setattr(st, 'session_state', second)
    assert storage.saved() == {}
