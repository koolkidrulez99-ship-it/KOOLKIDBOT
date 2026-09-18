import json, sys, urllib.request
from pathlib import Path
root = Path(r'C:\Users\jjmje\Desktop\deriv-bot-site')
sys.path.insert(0, str(root / 'mt5_module'))
from hub_auth import internal_workspace_signature
ws = 'ws_07f90f433b0144d5bddf17c8f27e07cc'
req = urllib.request.Request('http://127.0.0.1:8002/accounts', headers={
    'X-MT5-Workspace': ws,
    'X-MT5-Internal-Signature': internal_workspace_signature(ws),
    'Origin': 'http://127.0.0.1:5055',
})
with urllib.request.urlopen(req, timeout=10) as r:
    print('STATUS', r.status)
    print('ACAO', r.headers.get('Access-Control-Allow-Origin'))
    print(r.read().decode())
