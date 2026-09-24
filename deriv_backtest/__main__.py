"""Run: python -m deriv_backtest. One daemon per shared data directory."""
import os
from .store import data_dir


def main():
    handle = open(data_dir() / 'engine.lock', 'a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            handle.seek(0)
            handle.write(b'0')
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        handle.close()
        return
    try:
        from .engine import run_engine
        run_engine()
    finally:
        handle.close()


if __name__ == '__main__':
    main()
