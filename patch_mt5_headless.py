from pathlib import Path
root = Path(r'C:\Users\jjmje\Desktop\deriv-bot-site')
worker = root / 'mt5_module' / 'mt5_multi_account' / 'worker.py'
text = worker.read_text(encoding='utf-8-sig')
text = text.replace('import ctypes, os, queue, threading, time, traceback', 'import ctypes, os, queue, subprocess, threading, time, traceback')
old = '''def keep_terminal_hidden(terminal_path):\n    while True:\n        hide_terminal_windows(terminal_path)\n        time.sleep(0.15)\n'''
new = '''def keep_terminal_hidden(terminal_path):\n    while True:\n        hide_terminal_windows(terminal_path)\n        time.sleep(0.05)\n\ndef start_terminal_hidden(terminal_path, portable=True):\n    if os.name != "nt" or not terminal_path:\n        return None\n    startup = subprocess.STARTUPINFO()\n    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW\n    startup.wShowWindow = subprocess.SW_HIDE\n    args = [str(terminal_path)]\n    if portable:\n        args.append("/portable")\n    return subprocess.Popen(args, cwd=os.path.dirname(str(terminal_path)), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startup, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))\n'''
if old not in text: raise SystemExit('worker keep block not found')
text = text.replace(old, new, 1)
old = '''            terminal_path = config.get("terminal_path")\n            if os.name == "nt" and terminal_path:\n                threading.Thread(target=keep_terminal_hidden, args=(terminal_path,), daemon=True).start()\n            kwargs = {\n'''
new = '''            terminal_path = config.get("terminal_path")\n            if os.name == "nt" and terminal_path:\n                threading.Thread(target=keep_terminal_hidden, args=(terminal_path,), daemon=True).start()\n                try:\n                    start_terminal_hidden(terminal_path, bool(config.get("portable")))\n                    time.sleep(0.35)\n                except OSError:\n                    pass\n            kwargs = {\n'''
if old not in text: raise SystemExit('worker launch block not found')
text = text.replace(old, new, 1)
worker.write_text(text, encoding='utf-8')

app = root / 'mt5_module' / 'mt5_multi_account' / 'app.py'
text = app.read_text(encoding='utf-8-sig')
text = text.replace('TERMINALS = BASE / "data" / "terminals"\n', 'TERMINALS = BASE / "data" / "terminals"\nTEMPLATE_MQL5 = TERMINALS / "_worker_template" / "MQL5"\n', 1)
old = '''    with TERMINAL_LOCK:\n        if source != terminal and not terminal.is_file():\n            target_dir.parent.mkdir(parents=True, exist_ok=True)\n            shutil.copytree(source.parent, target_dir, dirs_exist_ok=True)\n        if not marker.is_file():\n            _CORE_POOL._stop_terminal(str(terminal))\n            source_data = source_data_dir(source)\n            if source_data and source_data.resolve() != target_dir.resolve():\n                source_config = source_data / "config"\n                if source_config.is_dir():\n                    shutil.copytree(source_config, target_dir / "config", dirs_exist_ok=True)\n            marker.write_text("Account terminal seeded from the original MT5 profile.\\n", encoding="ascii")\n'''
new = '''    with TERMINAL_LOCK:\n        if source != terminal and not terminal.is_file():\n            target_dir.parent.mkdir(parents=True, exist_ok=True)\n            shutil.copytree(source.parent, target_dir, dirs_exist_ok=True)\n            if TEMPLATE_MQL5.is_dir():\n                shutil.copytree(TEMPLATE_MQL5, target_dir / "MQL5", dirs_exist_ok=True)\n        if not marker.is_file():\n            _CORE_POOL._stop_terminal(str(terminal))\n            source_data = source_data_dir(source)\n            if source_data and source_data.resolve() != target_dir.resolve():\n                source_config = source_data / "config"\n                target_config = target_dir / "config"\n                target_config.mkdir(parents=True, exist_ok=True)\n                for name in ("servers.dat", "terminal.lic", "dnsperf.dat"):\n                    candidate = source_config / name\n                    if candidate.is_file():\n                        shutil.copy2(candidate, target_config / name)\n            marker.write_text("Account terminal seeded without account credentials.\\n", encoding="ascii")\n'''
if old not in text: raise SystemExit('app seed block not found')
text = text.replace(old, new, 1)
app.write_text(text, encoding='utf-8')
print('PATCH_OK')
