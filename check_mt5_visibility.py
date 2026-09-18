import ctypes, os, psutil
from ctypes import wintypes
needle = r'ws_07f90f433b0144d5bddf17c8f27e07cc--session-202177726\terminal64.exe'.lower()
proc = next(x for x in psutil.process_iter(['pid','exe']) if x.info.get('exe') and x.info['exe'].lower().endswith(needle))
found=[]
CB=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
@CB
def cb(hwnd,_):
    pid=wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    if int(pid.value)==proc.pid:
        found.append((int(hwnd), bool(ctypes.windll.user32.IsWindowVisible(hwnd))))
    return True
ctypes.windll.user32.EnumWindows(cb,0)
print('PID',proc.pid,'WINDOWS',found)
