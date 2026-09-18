from pathlib import Path
p=Path(r'C:\Users\jjmje\Desktop\deriv-bot-site\mt5_module\mt5_multi_account\worker.py')
t=p.read_text(encoding='utf-8')
start=t.index('def hide_terminal_windows(terminal_path):')
end=t.index('\ndef keep_terminal_hidden(terminal_path):', start)
new='''def hide_terminal_windows(terminal_path):\n    if os.name != "nt" or not terminal_path:\n        return\n    target_dir = os.path.normcase(os.path.dirname(os.path.abspath(terminal_path)))\n    allowed = {"terminal64.exe", "metaeditor64.exe", "metatester64.exe"}\n    pids = set()\n    try:\n        import psutil\n        for proc in psutil.process_iter(["pid", "exe", "name"]):\n            try:\n                image = os.path.normcase(os.path.abspath(proc.info.get("exe") or ""))\n                if os.path.dirname(image) == target_dir and os.path.basename(image).lower() in allowed:\n                    pids.add(int(proc.info["pid"]))\n            except (psutil.Error, OSError, ValueError):\n                pass\n    except Exception:\n        pass\n    if not pids:\n        return\n    user32 = ctypes.windll.user32\n    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)\n\n    @callback_type\n    def hide_if_target(hwnd, _):\n        pid = wintypes.DWORD()\n        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))\n        if int(pid.value) in pids:\n            user32.ShowWindowAsync(hwnd, 0)\n            user32.ShowWindow(hwnd, 0)\n            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0080)\n        return True\n\n    user32.EnumWindows(hide_if_target, 0)\n\n'''
t=t[:start]+new+t[end+1:]
p.write_text(t,encoding='utf-8')
print('WORKER_HIDE_PATCHED')
