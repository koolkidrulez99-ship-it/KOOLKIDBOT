import sys
from pathlib import Path
root = Path(r'C:\Users\jjmje\Desktop\deriv-bot-site')
sys.path.insert(0, str(root / 'mt5_module'))
from hub_auth import set_workspace, reset_workspace
from mt5_multi_account.app import isolated_terminal
ws = 'ws_07f90f433b0144d5bddf17c8f27e07cc'
tok = set_workspace(ws)
try:
    path = Path(isolated_terminal(f'{ws}--session-32321374', ''))
    print('TERMINAL', path)
    cfg = path.parent / 'config'
    print('ACCOUNTS_DAT', (cfg / 'accounts.dat').exists())
    print('SERVERS_DAT', (cfg / 'servers.dat').exists())
    print('MQL5_MQ5', len(list((path.parent / 'MQL5').rglob('*.mq5'))))
    print('MQL5_EX5', len(list((path.parent / 'MQL5').rglob('*.ex5'))))
finally:
    reset_workspace(tok)
