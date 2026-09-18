import ctypes, os, sys
from ctypes import wintypes
sys.path.insert(0,r'C:\Users\jjmje\Desktop\deriv-bot-site\mt5_module')
from mt5_multi_account.worker import hide_terminal_windows
path=r'C:\Users\jjmje\Desktop\deriv-bot-site\mt5_module\mt5_multi_account\data\terminals\ws_07f90f433b0144d5bddf17c8f27e07cc--session-202177726\terminal64.exe'
hide_terminal_windows(path)
user32,kernel=ctypes.windll.user32,ctypes.windll.kernel32
target=os.path.normcase(os.path.abspath(path)); found=[]
CB=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
@CB
def cb(hwnd,_):
    pid=wintypes.DWORD(); user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    handle=kernel.OpenProcess(0x1000,False,pid.value)
    if handle:
        try:
            size=wintypes.DWORD(32768); buf=ctypes.create_unicode_buffer(size.value)
            if kernel.QueryFullProcessImageNameW(handle,0,buf,ctypes.byref(size)) and os.path.normcase(os.path.abspath(buf.value))==target:
                found.append((int(hwnd),bool(user32.IsWindowVisible(hwnd))))
        finally: kernel.CloseHandle(handle)
    return True
user32.EnumWindows(cb,0)
print(found)
