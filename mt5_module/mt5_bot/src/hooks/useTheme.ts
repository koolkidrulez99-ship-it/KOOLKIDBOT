import { useEffect, useState } from 'react';

export type ThemeMode = 'dark' | 'light';
const KEY = 'koolkid_mt5_theme';

function initialTheme(): ThemeMode {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch { /* ignore */ }
  return 'dark';
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeMode>(initialTheme);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('light-theme', theme === 'light');
    root.classList.toggle('dark-theme', theme === 'dark');
    root.style.colorScheme = theme;
    try { localStorage.setItem(KEY, theme); } catch { /* ignore */ }
  }, [theme]);

  return {
    theme,
    setTheme: (next: ThemeMode) => setThemeState(next),
    toggleTheme: () => setThemeState((cur) => cur === 'dark' ? 'light' : 'dark'),
  };
}
