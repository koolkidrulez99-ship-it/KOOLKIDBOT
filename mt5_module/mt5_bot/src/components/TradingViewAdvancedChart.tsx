import { useEffect, useRef, useState } from 'react';
import { createDerivTradingViewDatafeed } from '../services/tradingViewDerivDatafeed';
import { createTradingViewLocalStorageAdapter } from '../services/tradingViewLocalStorage';

function intervalFromSeconds(seconds: number): string {
  if (seconds >= 86400) return '1D';
  return String(Math.max(1, Math.round(seconds / 60)));
}

/**
 * Optional host for TradingView Advanced Charts.
 * The proprietary TradingView runtime is intentionally NOT bundled with this
 * project. If the owner adds the licensed charting_library runtime, this
 * component supplies Deriv public market data through our custom datafeed.
 */
export default function TradingViewAdvancedChart({ symbol, seconds }: { symbol: string; seconds: number }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetRef = useRef<any>(null);
  const [theme, setTheme] = useState<'Dark' | 'Light'>(() => document.documentElement.classList.contains('light-theme') ? 'Light' : 'Dark');

  useEffect(() => {
    const root = document.documentElement;
    const observer = new MutationObserver(() => setTheme(root.classList.contains('light-theme') ? 'Light' : 'Dark'));
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const TradingView = (window as any).TradingView;
    const container = containerRef.current;
    if (!container || !TradingView?.widget) return;

    container.innerHTML = '';
    const widget = new TradingView.widget({
      symbol: `DERIV:${symbol}`,
      interval: intervalFromSeconds(seconds),
      container,
      datafeed: createDerivTradingViewDatafeed(),
      library_path: `${import.meta.env.BASE_URL || '/'}charting_library/`,
      locale: 'en',
      timezone: 'Etc/UTC',
      autosize: true,
      fullscreen: false,
      theme,
      enabled_features: [
        'study_templates', 'header_saveload', 'header_symbol_search', 'header_compare',
        'header_chart_type', 'header_indicators', 'header_settings', 'header_undo_redo',
        'header_screenshot', 'left_toolbar', 'use_localstorage_for_settings',
      ],
      disabled_features: ['header_widget_dom_node'],
      save_load_adapter: createTradingViewLocalStorageAdapter(),
      load_last_chart: true,
      auto_save_delay: 5,
      study_count_limit: 64,
      client_id: 'koolkid-mt5-hub',
      user_id: 'local-user',
    });
    widgetRef.current = widget;

    return () => {
      try { widgetRef.current?.remove?.(); } catch { /* runtime cleanup */ }
      widgetRef.current = null;
      if (container) container.innerHTML = '';
    };
  }, [symbol, seconds, theme]);

  return <div ref={containerRef} className="w-full min-h-[545px]" />;
}
