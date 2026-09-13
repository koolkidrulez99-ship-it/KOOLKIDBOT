const PREFIX = 'koolkid_workspace:';

function key(name: string) { return `${PREFIX}${name}`; }

export const workspaceService = {
  get<T>(name: string, fallback: T): T {
    try {
      const raw = localStorage.getItem(key(name));
      return raw == null ? fallback : { ...((typeof fallback === 'object' && fallback !== null) ? fallback as object : {}), ...((JSON.parse(raw) as any) ?? {}) } as T;
    } catch {
      try {
        const raw = localStorage.getItem(key(name));
        return raw == null ? fallback : JSON.parse(raw) as T;
      } catch { return fallback; }
    }
  },
  getRaw<T>(name: string, fallback: T): T {
    try {
      const raw = localStorage.getItem(key(name));
      return raw == null ? fallback : JSON.parse(raw) as T;
    } catch { return fallback; }
  },
  set<T>(name: string, value: T) {
    try { localStorage.setItem(key(name), JSON.stringify(value)); } catch { /* storage unavailable */ }
  },
  remove(name: string) {
    try { localStorage.removeItem(key(name)); } catch { /* ignore */ }
  },
  clear() {
    try {
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const k = localStorage.key(i);
        if (k?.startsWith(PREFIX)) localStorage.removeItem(k);
      }
    } catch { /* ignore */ }
  },
};
