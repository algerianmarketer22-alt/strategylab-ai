import os
from pathlib import Path

# Stockage applicatif Windows hors Documents, qui peut être protégé contre les écritures.
DATA = Path(os.environ.get('STRATEGYLAB_DATA', str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'StrategyLabAI')))
