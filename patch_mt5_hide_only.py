from pathlib import Path
p = Path(r'C:\Users\jjmje\Desktop\deriv-bot-site\mt5_module\mt5_multi_account\worker.py')
s = p.read_text(encoding='utf-8-sig')
s = s.replace('import ctypes, os, queue, subprocess, threading, time, traceback', 'import ctypes, os, queue, threading, time, traceback')
start = s.index('def hide_terminal_windows(terminal_path):')
end = s.index('def plain(obj):', start)
new = '''def hide_terminal_windows(terminal_path):
    if os.name != "nt" or not terminal_path:
        return
    target = os.path.normcase(os.path.abspath(terminal_path))
    target_dir = os.path.dirname(target)
    allowed = {"terminal64.exe", "metaeditor64.exe", "metatester64.exe"}
    user32, kernel = ctypes.windll.user32, ctypes.windll.kernel32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def hide_if_target(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x1000, False, pid.value)
        if handle:
            try:
                size = wintypes.DWORD(32768)
                buffer = ctypes.create_unicode_buffer(size.value)
                if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                    image = os.path.normcase(os.path.abspath(buffer.value))
                    if os.path.dirname(image) == target_dir and os.path.basename(image).lower() in allowed:
                        user32.ShowWindow(hwnd, 0)
            finally:
                kernel.CloseHandle(handle)
        return True

    user32.EnumWindows(hide_if_target, 0)


def keep_terminal_hidden(terminal_path):
    started = time.monotonic()
    while True:
        hide_terminal_windows(terminal_path)
        time.sleep(0.01 if time.monotonic() - started < 5 else 0.20)

'''
s = s[:start] + new + s[end:]
old = '''            if os.name == "nt" and terminal_path:
                threading.Thread(target=keep_terminal_hidden, args=(terminal_path,), daemon=True).start()
                try:
                    start_terminal_hidden(terminal_path, bool(config.get("portable")))
                    time.sleep(0.35)
                except OSError:
                    pass
            kwargs = {
'''
replacement = '''            if os.name == "nt" and terminal_path:
                threading.Thread(target=keep_terminal_hidden, args=(terminal_path,), daemon=True).start()
            kwargs = {
'''
if old not in s:
    raise SystemExit('prelaunch block not found')
s = s.replace(old, replacement, 1)
p.write_text(s, encoding='utf-8')
print('HIDE_PATCH_OK')
