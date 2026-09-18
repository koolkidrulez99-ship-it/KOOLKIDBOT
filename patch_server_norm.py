from pathlib import Path
p=Path(r'C:\Users\jjmje\Desktop\deriv-bot-site\mt5_module\mt5_multi_account\app.py')
t=p.read_text(encoding='utf-8')
anchor='''def source_data_dir(terminal: Path) -> Path | None:\n'''
helper='''def normalize_mt5_server(value: str) -> str:\n    server = str(value or "").strip()\n    compact = re.sub(r"\\s+", "", server).lower()\n    if compact == "deriv-demo":\n        return "Deriv-Demo"\n    if compact == "deriv-real":\n        return "Deriv-Real"\n    return server\n\n\n'''
if helper not in t:
    if anchor not in t: raise SystemExit('source anchor missing')
    t=t.replace(anchor,helper+anchor,1)
old='''    POOL.connect(dict(cfg), _saved_password(cfg))\n'''
new='''    prepared = dict(cfg)\n    prepared["server"] = normalize_mt5_server(prepared.get("server") or "")\n    POOL.connect(prepared, _saved_password(cfg))\n'''
if old not in t: raise SystemExit('saved connect anchor missing')
t=t.replace(old,new,1)
old2='''        cfg = req.model_dump(exclude={"password"})\n        cfg["auto_reconnect"] = True\n'''
new2='''        cfg = req.model_dump(exclude={"password"})\n        cfg["server"] = normalize_mt5_server(cfg.get("server") or "")\n        cfg["auto_reconnect"] = True\n'''
if old2 not in t: raise SystemExit('connect cfg anchor missing')
t=t.replace(old2,new2,1)
p.write_text(t,encoding='utf-8')
print('SERVER_NORMALIZE_PATCHED')
