from pathlib import Path
import re, json, difflib
ROOT=Path(r'C:\Users\jjmje\Music\Primordial_Family_Full')
files=sorted(ROOT.glob('Primordial_*.mq5'))

def extract(path):
    text=path.read_text(encoding='utf-8-sig', errors='ignore')
    lines=text.splitlines()
    desc=re.findall(r'#property\s+description\s+"([^"]+)"', text)
    inputs=[]
    for m in re.finditer(r'^input\s+([^;=]+?)\s+(\w+)\s*=\s*([^;]+);', text, re.M):
        inputs.append((m.group(1).strip(),m.group(2),m.group(3).strip()))
    funcs=[]
    pat=r'^(?:bool|void|int|double|string|datetime|BiasState|ConfluenceState|EntrySignal|ZoneData)\s+(\w+)\s*\(([^\n]*)'
    for m in re.finditer(pat,text,re.M): funcs.append(m.group(1))
    inds=sorted(set(re.findall(r'\b(i(?:ATR|MA|RSI|MACD|ADX|Stochastic|Bands|CCI|MFI|WPR|Momentum|Ichimoku|Fractals|Highest|Lowest))\s*\(',text)))
    calls=[]
    for token in ['trade.Buy','trade.Sell','PositionClosePartial','PositionModify','OrderSend','CopyBuffer']:
        if token in text: calls.append(token)
    return {'file':path.name,'lines':len(lines),'desc':desc,'inputs':inputs,'funcs':funcs,'inds':inds,'calls':calls,'text':text,'lines_text':lines}

data=[extract(p) for p in files]
for d in data:
    print('\n###',d['file'],'lines',d['lines'])
    print('DESC:', ' | '.join(d['desc']))
    print('INDICATORS:', ', '.join(d['inds']) or 'none')
    print('TRADE CALLS:', ', '.join(d['calls']) or 'none')
    print('INPUTS:')
    for t,n,v in d['inputs']: print(f'  {n}={v}')
    print('FUNCTIONS:', ', '.join(d['funcs']))
