# TradingView Advanced Charts setup for KOOLKID Deriv charts

KOOLKID v4.2 already includes a Deriv public-market datafeed adapter and a TradingView Advanced Charts host component. The official TradingView Advanced Charts runtime is proprietary and is not bundled in this project.

## What is already implemented

- Deriv active-symbol discovery and search
- Deriv candle history
- Deriv tick streaming
- TradingView symbol resolution
- historical `getBars`
- real-time `subscribeBars`
- multiple intraday/daily resolutions
- chart workspace persistence on the KOOLKID side

Files:

```text
src/services/derivMarketService.ts
src/services/tradingViewDerivDatafeed.ts
src/components/TradingViewAdvancedChart.tsx
src/components/DerivAdvancedChart.tsx
```

## When official TradingView access is available

Place the licensed TradingView `charting_library` distribution under:

```text
public/charting_library/
```

Then set `VITE_TRADINGVIEW_ADVANCED=1` in the frontend environment. KOOLKID will try to load `/charting_library/charting_library.js`; once `window.TradingView.widget` exists, it automatically enables the **TradingView Advanced** button in the Deriv chart workspace. If the library version you receive uses a different loader path, follow that version's TradingView instructions and expose `window.TradingView.widget` before opening the chart.

The chart is created with the KOOLKID Deriv datafeed, so the visual/charting engine is TradingView while the prices/bars come from Deriv.

## Important

Do not copy a random TradingView Advanced Charts package from another website or repository. Use the files provided to you under your own TradingView access/license.

The built-in KOOLKID Deriv chart remains available even when the TradingView runtime is absent, so Deriv candles, streaming ticks, EMA/Bollinger overlays and basic drawing markup still work without it.
