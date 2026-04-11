(function () {
  if (window.__koolkidAutoTradeRuntimeBooted) {
    console.info('auto_session_runtime_duplicate_init_skipped');
    return;
  }
  window.__koolkidAutoTradeRuntimeBooted = true;
  const catalog = Array.isArray(window.AUTO_SESSION_CATALOG) ? window.AUTO_SESSION_CATALOG : [];
  const initialStatus = window.AUTO_SESSION_INITIAL_STATUS || {};
  const initialDashboard = window.KOOLKID_AUTO_TRADE_DASHBOARD || {};
  const marketUniverse = Array.isArray(window.AUTO_SESSION_MARKETS) ? window.AUTO_SESSION_MARKETS : [];
  const username = String(window.AUTO_SESSION_USERNAME || 'Trader');
  const DEFAULT_PROFILE_ID = 'KOOLKID';
  const HISTORY_RENDER_MAX_ITEMS = 120;
  const runtimeIntervals = [];

  function registerRuntimeInterval(label, fn, delay) {
    const timer = window.setInterval(fn, delay);
    runtimeIntervals.push({ label: label, timer: timer });
    console.info('auto_session_active_interval_count', {
      reason: label + '_started',
      count: runtimeIntervals.length,
      intervals: runtimeIntervals.map(function (item) { return item.label; })
    });
    return timer;
  }

  function clearRuntimeIntervals(reason) {
    while (runtimeIntervals.length) {
      const item = runtimeIntervals.pop();
      try { window.clearInterval(item.timer); } catch (_err) {}
    }
    console.info('auto_session_active_interval_count', {
      reason: reason || 'runtime_cleanup',
      count: runtimeIntervals.length,
      intervals: []
    });
  }

  const refs = {
    mode: document.getElementById('autoSessionMode'),
    modeSingle: document.getElementById('autoSessionModeSingleBtn'),
    modeDual: document.getElementById('autoSessionModeDualBtn'),
    strategy1: document.getElementById('autoSessionStrategy1'),
    strategy2: document.getElementById('autoSessionStrategy2'),
    strategy2Wrap: document.getElementById('autoSessionStrategy2Wrap'),
    budget: document.getElementById('autoSessionBudget'),
    sl: document.getElementById('autoSessionSl'),
    tp: document.getElementById('autoSessionTp'),
    start: document.getElementById('autoSessionStartBtn'),
    stop: document.getElementById('autoSessionStopBtn'),
    notice: document.getElementById('autoSessionNotice'),
    connection: document.getElementById('autoSessionConnectionValue'),
    balance: document.getElementById('autoSessionBalanceValue'),
    serverTime: document.getElementById('autoSessionServerTime'),
    userInitials: document.getElementById('autoSessionUserInitials'),
    scannerStatus: document.getElementById('autoSessionScannerStatusText'),
    scannerCards: document.getElementById('autoSessionScannerCards'),
    volatilityValue: document.getElementById('autoSessionVolatilityValue'),
    volatilityFill: document.getElementById('autoSessionVolatilityFill'),
    status: document.getElementById('autoSessionStatusValue'),
    statusDetail: document.getElementById('autoSessionStatusDetailValue'),
    liveFlag: document.getElementById('autoSessionLiveFlag'),
    confidence: document.getElementById('autoSessionConfidenceValue'),
    confidenceMirror: document.getElementById('autoSessionConfidenceValueMirror'),
    confidenceRing: document.getElementById('autoSessionConfidenceRing'),
    confidenceGrade: document.getElementById('autoSessionConfidenceGrade'),
    market: document.getElementById('autoSessionMarketValue'),
    marketMirror: document.getElementById('autoSessionMarketValueMirror'),
    strategy: document.getElementById('autoSessionStrategyValue'),
    strategyMirror: document.getElementById('autoSessionStrategyValueMirror'),
    why: document.getElementById('autoSessionWhyValue'),
    tag1: document.getElementById('autoSessionSetupTag1'),
    tag2: document.getElementById('autoSessionSetupTag2'),
    tag3: document.getElementById('autoSessionSetupTag3'),
    chartSvg: document.getElementById('autoSessionChartSvg'),
    chartLinePrimary: document.getElementById('autoSessionChartLinePrimary'),
    chartLineSecondary: document.getElementById('autoSessionChartLineSecondary'),
    chartLineTertiary: document.getElementById('autoSessionChartLineTertiary'),
    chartBars: document.getElementById('autoSessionChartBars'),
    chartLeftCopy: document.getElementById('autoSessionChartLeftCopy'),
    chartRightCopy: document.getElementById('autoSessionChartRightCopy'),
    budgetValue: document.getElementById('autoSessionBudgetValue'),
    budgetHero: document.getElementById('autoSessionBudgetHero'),
    remaining: document.getElementById('autoSessionRemainingValue'),
    stake: document.getElementById('autoSessionStakeValue'),
    pnl: document.getElementById('autoSessionPnlValue'),
    wins: document.getElementById('autoSessionWinsValue'),
    losses: document.getElementById('autoSessionLossesValue'),
    tpValue: document.getElementById('autoSessionTpValue'),
    tpHero: document.getElementById('autoSessionTpHero'),
    slValue: document.getElementById('autoSessionSlValue'),
    slHero: document.getElementById('autoSessionSlHero'),
    stakeGuide: document.getElementById('autoSessionStakeGuideCopy'),
    tierLow: document.getElementById('autoSessionStakeTierLow'),
    tierMid: document.getElementById('autoSessionStakeTierMid'),
    tierHigh: document.getElementById('autoSessionStakeTierHigh'),
    tierMax: document.getElementById('autoSessionStakeTierMax'),
    historyClear: document.getElementById('autoTradeHistoryClearBtn'),
    historyClearMobile: document.getElementById('autoTradeHistoryClearBtnMobile'),
    historySwipeToggleMobile: document.getElementById('autoTradeHistorySwipeToggleMobile'),
    historyTotal: document.getElementById('autoTradeHistoryTotal'),
    historyWins: document.getElementById('autoTradeHistoryWins'),
    historyLosses: document.getElementById('autoTradeHistoryLosses'),
    historyWinRate: document.getElementById('autoTradeHistoryWinRate'),
    historyNetPnl: document.getElementById('autoTradeHistoryNetPnl'),
    historyBody: document.getElementById('autoTradeHistoryBody'),
    historyWinsMobile: document.getElementById('autoTradeHistoryWinsMobile'),
    historyLossesMobile: document.getElementById('autoTradeHistoryLossesMobile'),
    historyWinRateMobile: document.getElementById('autoTradeHistoryWinRateMobile'),
    historyNetPnlMobile: document.getElementById('autoTradeHistoryNetPnlMobile'),
    historyBodyMobile: document.getElementById('autoTradeHistoryBodyMobile'),
    predictionConfidence: document.getElementById('autoSessionPredictionConfidence'),
    predictionHigher: document.getElementById('autoSessionPredictionHigher'),
    predictionLower: document.getElementById('autoSessionPredictionLower'),
    predictionAction: document.getElementById('autoSessionPredictionAction'),
    predictionGap: document.getElementById('autoSessionPredictionGap'),
    predictionSummary: document.getElementById('autoSessionPredictionSummary'),
    predictionMeta: document.getElementById('autoSessionPredictionMeta'),
    predictionSimulation: document.getElementById('autoSessionPredictionSimulation'),
    predictionDirection: document.getElementById('autoSessionPredictionDirection'),
    predictionStrength: document.getElementById('autoSessionPredictionStrength'),
    predictionPersistence: document.getElementById('autoSessionPredictionPersistence'),
    predictionQuality: document.getElementById('autoSessionPredictionQuality')
  };

  const runtime = {
    lastStatus: initialStatus || {},
    chartTick: 0,
    mobileHistorySwipeOn: true,
    predictionTimer: null,
    predictionSignature: '',
    predictionLoading: false,
    historySignature: '',
    lastHistoryLogAt: 0
  };

  const draftConfig = {
    mode: initialStatus.mode === 'dual' ? 'dual' : 'single',
    strategy1: Array.isArray(initialStatus.selected_strategies) && initialStatus.selected_strategies[0] ? String(initialStatus.selected_strategies[0].id || '') : DEFAULT_PROFILE_ID,
    strategy2: Array.isArray(initialStatus.selected_strategies) && initialStatus.selected_strategies[1] ? String(initialStatus.selected_strategies[1].id || '') : '',
    budget: Number(initialStatus.budget || 100),
    sl: Number(initialStatus.sl || 0),
    tp: Number(initialStatus.tp || 0),
    dirty: false
  };

  function currencyPayload(payload) {
    return payload || runtime.lastStatus || (initialDashboard && initialDashboard.stats) || {};
  }

  function syncCurrency(payload) {
    return currencyPayload(payload);
  }

  function money(value, payload) {
    const num = Number(value || 0);
    try { if (typeof formatCurrencyAmount === 'function') return formatCurrencyAmount(num, currencyPayload(payload)); } catch (_err) {}
    return Number.isFinite(num) ? `$${Math.abs(num).toFixed(2)}` : '—';
  }

  function signedMoney(value, payload) {
    const num = Number(value || 0);
    try { if (typeof formatSignedCurrencyAmount === 'function') return formatSignedCurrencyAmount(num, currencyPayload(payload)); } catch (_err) {}
    if (!Number.isFinite(num)) return '—';
    return (num >= 0 ? '+' : '-') + '$' + Math.abs(num).toFixed(2);
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, Number(value || 0)));
  }

  function formatPercent(value) {
    return Number(value || 0).toFixed(1) + '%';
  }

  function selectedProfileText(status) {
    const selected = Array.isArray(status && status.selected_strategies) ? status.selected_strategies : [];
    const labels = selected
      .map(function (item) { return String((item && item.label) || '').replace(/\s+Profile$/i, '').trim(); })
      .filter(Boolean);
    if (!labels.length) return 'selected profiles';
    return labels.join(' + ');
  }

  function getLiveBalance() {
    const latest = Number(runtime.lastStatus && runtime.lastStatus.balance);
    if (Number.isFinite(latest) && latest > 0) return latest;
    return 0;
  }

  function effectiveBudgetCap() {
    const live = getLiveBalance();
    if (live > 0) return Math.max(1, Math.min(2000, live));
    return 2000;
  }

  function enforceBudgetCap(showNotice) {
    if (!refs.budget) return;
    const cap = effectiveBudgetCap();
    refs.budget.max = String(cap);
    const current = Number(refs.budget.value || 0);
    if (Number.isFinite(current) && current > cap) {
      refs.budget.value = cap.toFixed(2);
      draftConfig.budget = cap;
      if (showNotice) {
        setNotice('Session budget cannot be above your current balance.');
      }
    }
    if (Number(refs.budget.value || 0) < 1) {
      refs.budget.value = '1.00';
      draftConfig.budget = 1;
    }
  }

  function initialsFromName(name) {
    const parts = String(name || 'Trader').trim().split(/\s+/).filter(Boolean);
    return (parts[0] ? parts[0][0] : 'T') + (parts[1] ? parts[1][0] : (parts[0] && parts[0][1] ? parts[0][1] : 'R'));
  }

  function formatMarketLabel(symbol) {
    const raw = String(symbol || '').trim();
    const vix = raw.match(/^R_(\d+)$/i);
    if (vix) return 'Volatility ' + vix[1];
    const jump = raw.match(/^JD?(\d+)$/i);
    if (jump) return 'Jump ' + jump[1];
    const hz = raw.match(/^1HZ(\d+)V$/i);
    if (hz) return 'Volatility ' + hz[1] + ' (1s)';
    return raw || 'Market Scan';
  }

  function setNotice(text) {
    if (refs.notice) refs.notice.textContent = text || 'Ready';
  }

  function syncMobileHistorySwipe() {
    const panel = refs.historyBodyMobile ? refs.historyBodyMobile.closest('.mobile-trade-history-panel') : null;
    if (panel) panel.classList.toggle('history-swipe-off', !runtime.mobileHistorySwipeOn);
    if (refs.historySwipeToggleMobile) {
      refs.historySwipeToggleMobile.classList.toggle('active', !!runtime.mobileHistorySwipeOn);
      refs.historySwipeToggleMobile.setAttribute('aria-pressed', runtime.mobileHistorySwipeOn ? 'true' : 'false');
      refs.historySwipeToggleMobile.setAttribute('title', runtime.mobileHistorySwipeOn ? 'Swipe scrolling enabled' : 'Swipe scrolling disabled');
    }
  }

  function optionExists(select, value) {
    if (!select || value === undefined || value === null || value === '') return false;
    return Array.from(select.options || []).some(function (option) { return option.value === String(value); });
  }

  function syncMode() {
    const dual = refs.mode && refs.mode.value === 'dual';
    if (refs.strategy2Wrap) refs.strategy2Wrap.classList.toggle('hidden', !dual);
    if (refs.modeSingle) refs.modeSingle.classList.toggle('active', !dual);
    if (refs.modeDual) refs.modeDual.classList.toggle('active', dual);
  }

  function applyDraftConfig() {
    if (refs.mode) refs.mode.value = draftConfig.mode === 'dual' ? 'dual' : 'single';
    if (refs.strategy1 && optionExists(refs.strategy1, draftConfig.strategy1)) refs.strategy1.value = draftConfig.strategy1;
    if (refs.strategy2 && optionExists(refs.strategy2, draftConfig.strategy2)) refs.strategy2.value = draftConfig.strategy2;
    if (refs.budget && !refs.budget.matches(':focus')) refs.budget.value = Number(draftConfig.budget || refs.budget.value || 100);
    if (refs.sl && !refs.sl.matches(':focus')) refs.sl.value = Number(draftConfig.sl || refs.sl.value || 0);
    if (refs.tp && !refs.tp.matches(':focus')) refs.tp.value = Number(draftConfig.tp || refs.tp.value || 0);
    syncMode();
    enforceBudgetCap(false);
  }

  function captureDraftConfig() {
    if (refs.mode) draftConfig.mode = refs.mode.value === 'dual' ? 'dual' : 'single';
    if (refs.strategy1) draftConfig.strategy1 = String(refs.strategy1.value || '');
    if (refs.strategy2) draftConfig.strategy2 = String(refs.strategy2.value || '');
    if (refs.budget) draftConfig.budget = Number(refs.budget.value || draftConfig.budget || 100);
    if (refs.sl) draftConfig.sl = Number(refs.sl.value || 0);
    if (refs.tp) draftConfig.tp = Number(refs.tp.value || 0);
    draftConfig.dirty = true;
    syncMode();
  }

  function syncDraftFromStatus(status) {
    const selected = Array.isArray(status && status.selected_strategies) ? status.selected_strategies : [];
    draftConfig.mode = status && status.mode === 'dual' ? 'dual' : 'single';
    if (selected[0] && selected[0].id) draftConfig.strategy1 = String(selected[0].id);
    else if (!draftConfig.strategy1) draftConfig.strategy1 = DEFAULT_PROFILE_ID;
    if (selected[1] && selected[1].id) draftConfig.strategy2 = String(selected[1].id);
    else if (!draftConfig.strategy2 && refs.strategy2) draftConfig.strategy2 = String(refs.strategy2.value || '');
    draftConfig.budget = Number((status && status.budget) || draftConfig.budget || 100);
    draftConfig.sl = Number((status && status.sl) || draftConfig.sl || 0);
    draftConfig.tp = Number((status && status.tp) || draftConfig.tp || 0);
  }

  function contractText(row) {
    const parts = [];
    if (row && row.button_label) parts.push(String(row.button_label));
    if (row && row.symbol) parts.push(formatMarketLabel(row.symbol));
    let typeText = row && row.type ? String(row.type) : 'TRADE';
    if (row && row.barrier !== undefined && row.barrier !== null && row.barrier !== '') {
      typeText += ' ' + String(row.barrier);
    }
    parts.push(typeText);
    if (row && row.duration !== undefined && row.duration !== null && row.duration !== '') {
      parts.push(String(row.duration) + String(row.duration_unit || ''));
    }
    return parts.join(' • ');
  }

  function resultClass(row) {
    if (row && row.pending) return 'pending';
    return String((row && row.result) || '').toUpperCase() === 'WIN' ? 'won' : 'lost';
  }

  function renderHistory(dashboard) {
    const stats = (dashboard && dashboard.stats) || {};
    const fullHistory = Array.isArray(dashboard && dashboard.history) ? dashboard.history : [];
    const history = fullHistory.slice(0, HISTORY_RENDER_MAX_ITEMS);
    syncCurrency(stats);
    const historyMarkup = history.length ? history.map(function (row) {
      const payout = row && row.payout !== undefined && row.payout !== null ? money(row.payout, row) : 'Payout --';
      const profitNum = Number((row && row.profit) || 0);
      const profitText = signedMoney(profitNum, row);
      const profitClass = profitNum >= 0 ? 'profit-green' : 'profit-red';
      const resultText = row && row.pending ? 'PENDING' : String((row && row.result) || 'LOSS');
      return '' +
        '<div class="history-item">' +
          '<div class="history-result ' + resultClass(row) + '">' + resultText + '</div>' +
          '<div class="history-details">' +
            '<strong>' + contractText(row) + '</strong>' +
            '<span>' + String((row && row.time) || '-') + '</span>' +
          '</div>' +
          '<div class="history-money">' +
            '<div class="history-metric">' +
              '<span class="metric-label">Stake</span>' +
              '<span class="metric-value">' + money((row && row.stake) || 0) + '</span>' +
            '</div>' +
            '<div class="history-metric">' +
              '<span class="metric-label">Payout</span>' +
              '<span class="metric-value">' + payout.replace('Payout ', '') + '</span>' +
            '</div>' +
            '<div class="history-metric">' +
              '<span class="metric-label">Profit</span>' +
              '<span class="metric-value profit ' + profitClass + '">' + profitText + '</span>' +
            '</div>' +
          '</div>' +
        '</div>';
    }).join('') : '<div class="empty-state">No Auto Trading Session trades yet.</div>';

    if (refs.historyTotal) refs.historyTotal.textContent = String(stats.total_trades || 0);
    if (refs.historyWins) refs.historyWins.textContent = String(stats.wins || 0);
    if (refs.historyWinsMobile) refs.historyWinsMobile.textContent = String(stats.wins || 0);
    if (refs.historyLosses) refs.historyLosses.textContent = String(stats.losses || 0);
    if (refs.historyLossesMobile) refs.historyLossesMobile.textContent = String(stats.losses || 0);
    if (refs.historyWinRate) refs.historyWinRate.textContent = formatPercent(stats.winrate || 0);
    if (refs.historyWinRateMobile) refs.historyWinRateMobile.textContent = formatPercent(stats.winrate || 0);
    if (refs.historyNetPnl) {
      const pnl = Number(stats.net_pnl || 0);
      refs.historyNetPnl.textContent = money(pnl);
      refs.historyNetPnl.classList.remove('green', 'red');
      refs.historyNetPnl.classList.add(pnl >= 0 ? 'green' : 'red');
      if (refs.historyNetPnlMobile) {
        refs.historyNetPnlMobile.textContent = money(pnl);
        refs.historyNetPnlMobile.classList.remove('green', 'red');
        refs.historyNetPnlMobile.classList.add(pnl >= 0 ? 'green' : 'red');
      }
    }

    if (runtime.historySignature !== historyMarkup) {
      if (refs.historyBody) refs.historyBody.innerHTML = historyMarkup;
      if (refs.historyBodyMobile) refs.historyBodyMobile.innerHTML = historyMarkup;
      runtime.historySignature = historyMarkup;
    }
    if (Date.now() - Number(runtime.lastHistoryLogAt || 0) > 5000) {
      runtime.lastHistoryLogAt = Date.now();
      console.info('auto_session_trade_history_item_count', {
        rendered: history.length,
        total: fullHistory.length,
        cap: HISTORY_RENDER_MAX_ITEMS
      });
    }
  }

  function predictionBreakdownText(section) {
    const higher = Number(section && section.higher_score);
    const lower = Number(section && section.lower_score);
    const higherText = Number.isFinite(higher) ? higher.toFixed(0) : '?';
    const lowerText = Number.isFinite(lower) ? lower.toFixed(0) : '?';
    return 'H ' + higherText + ' / L ' + lowerText;
  }

  function inferPredictionDuration(status) {
    const history = status && status.koolkid_dashboard && Array.isArray(status.koolkid_dashboard.history)
      ? status.koolkid_dashboard.history
      : [];
    const latestTimedRow = history.find(function (row) {
      return row && row.duration !== undefined && row.duration !== null && row.duration !== '';
    });
    if (latestTimedRow) {
      return {
        duration: Number(latestTimedRow.duration || 5) || 5,
        duration_unit: String(latestTimedRow.duration_unit || 't').toLowerCase()
      };
    }
    return { duration: 5, duration_unit: 't' };
  }

  function buildPredictionRequest(status) {
    const durationInfo = inferPredictionDuration(status || {});
    const activeMarket = String((status && status.active_market) || '');
    const fallbackMarket = Array.isArray(status && status.scan_markets) && status.scan_markets.length
      ? String(status.scan_markets[0] || '')
      : (marketUniverse[0] || '');
    return {
      symbol: activeMarket || fallbackMarket,
      duration: durationInfo.duration,
      duration_unit: durationInfo.duration_unit
    };
  }

  function renderPrediction(prediction) {
    const data = prediction && typeof prediction === 'object' ? prediction : {};
    const ok = String(data.status || '').toLowerCase() === 'success';
    const higher = Number.isFinite(Number(data.higher_pct)) ? Number(data.higher_pct) : 50;
    const lower = Number.isFinite(Number(data.lower_pct)) ? Number(data.lower_pct) : 50;
    const confidence = String(data.confidence_label || 'Skip');
    const action = String(data.suggested_action || 'Skip');
    const gap = Number.isFinite(Number(data.gap)) ? Number(data.gap) : Math.abs(higher - lower);
    const summary = String(data.reasoning_summary || data.message || 'Waiting for enough market history to build the Higher / Lower prediction.');
    const source = String(data.source || '--').toUpperCase();
    const durationText = data.duration != null ? String(data.duration) + String(data.duration_unit || '').toUpperCase() : '--';
    const horizon = Number.isFinite(Number(data.horizon_ticks)) ? String(Number(data.horizon_ticks)) + ' ticks' : '--';
    const breakdown = data && typeof data.score_breakdown === 'object' ? data.score_breakdown : {};

    if (refs.predictionHigher) refs.predictionHigher.textContent = higher.toFixed(1) + '%';
    if (refs.predictionLower) refs.predictionLower.textContent = lower.toFixed(1) + '%';
    if (refs.predictionAction) refs.predictionAction.textContent = action;
    if (refs.predictionGap) refs.predictionGap.textContent = gap.toFixed(1) + '%';
    if (refs.predictionSummary) refs.predictionSummary.textContent = summary;
    if (refs.predictionMeta) refs.predictionMeta.textContent = 'Source: ' + source + ' | Duration: ' + durationText + ' | Horizon: ' + horizon;
    if (refs.predictionSimulation) refs.predictionSimulation.textContent = predictionBreakdownText(breakdown.simulation);
    if (refs.predictionDirection) refs.predictionDirection.textContent = predictionBreakdownText(breakdown.direction);
    if (refs.predictionStrength) refs.predictionStrength.textContent = predictionBreakdownText(breakdown.strength);
    if (refs.predictionPersistence) refs.predictionPersistence.textContent = predictionBreakdownText(breakdown.persistence);
    if (refs.predictionQuality) refs.predictionQuality.textContent = predictionBreakdownText(breakdown.market_quality);
    if (refs.predictionConfidence) {
      refs.predictionConfidence.textContent = confidence;
      refs.predictionConfidence.classList.remove('connected', 'disconnected');
      refs.predictionConfidence.style.background = confidence === 'Strong'
        ? 'rgba(78, 221, 145, .18)'
        : confidence === 'Good'
        ? 'rgba(89, 193, 255, .18)'
        : confidence === 'Weak'
        ? 'rgba(245, 166, 35, .18)'
        : 'rgba(127, 143, 175, .18)';
      refs.predictionConfidence.style.color = confidence === 'Strong'
        ? '#9bf6bc'
        : confidence === 'Good'
        ? '#9ad8ff'
        : confidence === 'Weak'
        ? '#ffd18a'
        : '#dce9ff';
    }
    if (refs.predictionAction) {
      refs.predictionAction.classList.remove('green', 'red');
      if (action.indexOf('Higher') !== -1) refs.predictionAction.classList.add('green');
      else if (action.indexOf('Lower') !== -1) refs.predictionAction.classList.add('red');
    }
    if (refs.predictionSummary) refs.predictionSummary.style.color = ok ? '#d8e6ff' : '#f5b4bb';
  }

  async function refreshPrediction(status) {
    const payload = buildPredictionRequest(status || runtime.lastStatus || {});
    if (!payload.symbol || runtime.predictionLoading) {
      renderPrediction({ status: 'error', message: 'Waiting for a market to analyze.' });
      return;
    }
    const signature = JSON.stringify(payload);
    runtime.predictionSignature = signature;
    runtime.predictionLoading = true;
    try {
      const response = await fetch('/higher_lower_prediction', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (signature !== runtime.predictionSignature) return;
      renderPrediction(data || null);
    } catch (_err) {
      renderPrediction({ status: 'error', message: 'Could not load Higher / Lower prediction right now.' });
    } finally {
      runtime.predictionLoading = false;
    }
  }

  function schedulePrediction(status, delay) {
    if (runtime.predictionTimer) {
      window.clearTimeout(runtime.predictionTimer);
      runtime.predictionTimer = null;
    }
    const snapshot = status || runtime.lastStatus || {};
    runtime.predictionTimer = window.setTimeout(function () {
      runtime.predictionTimer = null;
      refreshPrediction(snapshot);
    }, Math.max(100, Number(delay || 220)));
  }

  function renderScanner(status) {
    if (!refs.scannerCards) return;
    const active = String(status.active_market || '');
    const total = Number(status.total_markets || marketUniverse.length || 0);
    const seeded = Number(status.seeded_markets || 0);
    const scanRatio = total > 0 ? seeded / total : 0;
    const rotatingBatch = Array.isArray(status.scan_markets) && status.scan_markets.length ? status.scan_markets.slice() : null;
    const ordered = rotatingBatch && rotatingBatch.length
      ? rotatingBatch
      : (active ? [active].concat(marketUniverse.filter(function (symbol) { return symbol !== active; })) : marketUniverse.slice());
    const visible = ordered.slice(0, 5);
    const confidence = clamp(status.confidence || 0, 0, 99);
    const volatility = clamp(Math.round((confidence * 0.55) + (scanRatio * 45)), 18, 99);

    if (refs.volatilityValue) refs.volatilityValue.textContent = String(volatility) + '/100';
    if (refs.volatilityFill) refs.volatilityFill.style.width = String(volatility) + '%';

    refs.scannerCards.innerHTML = visible.map(function (symbol, index) {
      const isActive = active && symbol === active;
      const base = confidence > 0 ? confidence : (62 + (seeded * 2));
      const score = clamp(Math.round(base + (isActive ? 6 : 0) - (index * 5)), 55, 96);
      const stateText = isActive && status.running ? 'ACTIVE' : (scanRatio >= 1 ? 'READY' : 'SCANNING');
      return '' +
        '<div class="scanner-card' + (isActive ? ' active' : '') + '">' +
          '<span class="market-name">' + formatMarketLabel(symbol) + '</span>' +
          '<div class="score">' + score + '%</div>' +
          '<div class="meta">' + stateText + '</div>' +
        '</div>';
    }).join('');
  }

  function buildChartPoints(seed, amplitude, floor, ceiling, wobble) {
    const pts = [];
    const count = 14;
    for (let index = 0; index < count; index += 1) {
      const x = Math.round((320 / (count - 1)) * index);
      const waveA = Math.sin((index * 0.56) + seed) * amplitude;
      const waveB = Math.cos((index * 0.29) + seed * 1.2) * wobble;
      const y = Math.max(floor, Math.min(ceiling, 150 - waveA - waveB - (index * 4.8)));
      pts.push(x + ',' + Math.round(y));
    }
    return pts.join(' ');
  }

  function renderChartBars(seed, confidence) {
    if (!refs.chartBars) return;
    const bars = [];
    for (let index = 0; index < 13; index += 1) {
      const x = 20 + (index * 22);
      const base = 58 + (Math.sin(seed + (index * 0.45)) * 18) + (confidence * 0.35);
      const height = Math.max(36, Math.min(148, base));
      const y = 242 - height;
      bars.push('<rect x="' + x + '" y="' + y.toFixed(0) + '" width="12" height="' + height.toFixed(0) + '" fill="rgba(85,163,255,.35)"/>');
    }
    refs.chartBars.innerHTML = bars.join('');
  }

  function renderLiveChart(status) {
    if (!refs.chartLinePrimary || !refs.chartLineSecondary || !refs.chartLineTertiary) return;
    runtime.chartTick += 1;
    const confidence = clamp(status && status.confidence || 0, 0, 99);
    const activeBoost = status && status.running ? 1.1 : 0.7;
    const seed = (Date.now() / 900) + (runtime.chartTick * 0.015) + (confidence * 0.02);
    refs.chartLinePrimary.setAttribute('points', buildChartPoints(seed, 40 * activeBoost, 42, 214, 18));
    refs.chartLineSecondary.setAttribute('points', buildChartPoints(seed + 0.8, 22 * activeBoost, 72, 228, 10));
    refs.chartLineTertiary.setAttribute('points', buildChartPoints(seed + 1.5, 12 * activeBoost, 120, 236, 6));
    renderChartBars(seed, confidence);
  }

  function animateChart() {
    renderLiveChart(runtime.lastStatus || {});
  }
  function updateStakeGuide(status) {
    const budget = Number(status.budget || refs.budget && refs.budget.value || 0);
    const low = Math.max(0.35, budget * 0.10);
    const mid = Math.max(0.35, budget * 0.25);
    const high = Math.max(0.35, budget * 0.50);
    const max = Math.max(0.35, budget);
    if (refs.tierLow) refs.tierLow.textContent = money(low);
    if (refs.tierMid) refs.tierMid.textContent = money(mid);
    if (refs.tierHigh) refs.tierHigh.textContent = money(high);
    if (refs.tierMax) refs.tierMax.textContent = money(max);
    if (refs.stakeGuide) refs.stakeGuide.textContent = status && status.recovery_mode
      ? 'Recovery mode is active. The session stays smaller and only takes 75%+ confidence setups.'
      : 'First trade starts at $0.35, then the session ramps with budget and confidence.';
  }

  function syncActionButtons(status) {
    const running = !!(status && status.running);
    if (refs.start) {
      refs.start.classList.toggle('is-on', running);
      refs.start.innerHTML = running
        ? 'AUTO SESSION: ON<span>Tap again to stop the live session.</span>'
        : 'Start Auto Session<span>AI will scan and wait for the strongest valid setup.</span>';
    }
  }

  function applyStatus(status) {
    runtime.lastStatus = status || {};
    syncCurrency(status);
    const selected = Array.isArray(status.selected_strategies) ? status.selected_strategies : [];
    const confidence = clamp(status.confidence || 0, 0, 99);
    const activeMarket = status.active_market ? formatMarketLabel(status.active_market) : 'Scanning markets...';
    const activeStrategy = status.active_strategy || ('Scanning ' + selectedProfileText(status) + ' buttons');
    const detail = status.status_detail || ('Scanning ' + selectedProfileText(status) + ' for a valid setup...');
    const grade = confidence >= 90 ? 'Excellent' : confidence >= 80 ? 'Strong' : confidence >= 70 ? 'Ready' : confidence >= 60 ? 'Measured' : 'Standby';

    if (refs.connection) {
      refs.connection.textContent = status.connected ? 'API Connected' : 'API Disconnected';
      refs.connection.classList.toggle('connected', !!status.connected);
      refs.connection.classList.toggle('disconnected', !status.connected);
    }
    if (refs.balance) refs.balance.textContent = money(status.balance || 0, status);
    if (refs.status) refs.status.textContent = status.status || 'IDLE';
    if (refs.statusDetail) refs.statusDetail.textContent = detail;
    if (refs.liveFlag) refs.liveFlag.textContent = status.running ? 'Session Active' : 'Session Idle';
    if (refs.scannerStatus) {
      const batch = Array.isArray(status.scan_markets) && status.scan_markets.length
        ? ' • Batch: ' + status.scan_markets.map(formatMarketLabel).slice(0, 2).join(', ')
        : '';
      refs.scannerStatus.textContent = detail + batch;
    }
    if (refs.confidence) refs.confidence.textContent = Math.round(confidence) + '%';
    if (refs.confidenceMirror) refs.confidenceMirror.textContent = Math.round(confidence) + '%';
    if (refs.confidenceGrade) refs.confidenceGrade.textContent = grade;
    if (refs.confidenceRing) refs.confidenceRing.style.setProperty('--confidence', String(confidence));
    if (refs.market) refs.market.textContent = activeMarket;
    if (refs.marketMirror) refs.marketMirror.textContent = status.active_market || '-';
    if (refs.strategy) refs.strategy.textContent = activeStrategy;
    if (refs.strategyMirror) refs.strategyMirror.textContent = activeStrategy;
    if (refs.why) refs.why.textContent = detail;
    if (refs.tag1) refs.tag1.textContent = status.running ? 'Live Session' : 'Scanning';
    if (refs.tag2) refs.tag2.textContent = confidence >= 80 ? 'High Confidence' : confidence >= 60 ? 'Qualified Setup' : 'Waiting Edge';
    if (refs.tag3) refs.tag3.textContent = (refs.mode && refs.mode.value === 'dual') ? 'Dual Profile' : 'Single Profile';
    if (refs.chartLeftCopy) refs.chartLeftCopy.textContent = 'Active button: ' + (status.active_strategy || 'Scanning profile buttons');
    if (refs.chartRightCopy) refs.chartRightCopy.textContent = 'Remaining budget: ' + money(status.remaining_budget || 0, status) + ' • Protected profit: ' + money(status.profit_bank || 0, status);

    if (refs.budgetValue) refs.budgetValue.textContent = money(status.budget || 0, status);
    if (refs.budgetHero) refs.budgetHero.textContent = money(status.budget || 0, status);
    if (refs.remaining) refs.remaining.textContent = money(status.remaining_budget || 0, status);
    if (refs.stake) refs.stake.textContent = money(status.current_stake || 0.35, status);
    if (refs.pnl) {
      const pnl = Number(status.profit_bank != null ? status.profit_bank : (status.profit_loss || 0));
      refs.pnl.textContent = signedMoney(pnl, status);
      refs.pnl.classList.remove('green', 'red');
      refs.pnl.classList.add(pnl >= 0 ? 'green' : 'red');
    }
    if (refs.wins) refs.wins.textContent = String(status.wins || 0);
    if (refs.losses) refs.losses.textContent = String(status.losses || 0);
    if (refs.tpValue) refs.tpValue.textContent = money(status.tp || 0, status);
    if (refs.tpHero) refs.tpHero.textContent = money(status.tp || 0, status);
    if (refs.slValue) refs.slValue.textContent = money(status.sl || 0, status);
    if (refs.slHero) refs.slHero.textContent = money(status.sl || 0, status);

    syncActionButtons(status || {});
    setNotice(detail);
    enforceBudgetCap(false);
    renderLiveChart(status || {});

    if (status.running || !draftConfig.dirty) {
      syncDraftFromStatus(status || {});
      draftConfig.dirty = false;
    }
    applyDraftConfig();

    renderScanner(status || {});
    updateStakeGuide(status || {});
    if (status && status.koolkid_dashboard) renderHistory(status.koolkid_dashboard);
    schedulePrediction(status || {}, 140);
  }

  function tickClock() {
    const now = new Date();
    if (!refs.serverTime) return;
    refs.serverTime.textContent = now.toISOString().slice(11, 19) + ' UTC';
  }

  async function fetchStatus() {
    try {
      const response = await fetch('/auto-session/status', { credentials: 'same-origin' });
      const data = await response.json();
      applyStatus(data || {});
    } catch (_err) {
      setNotice('Unable to refresh session status right now.');
    }
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {})
    });
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || 'Request failed');
    return data;
  }

  async function startSession() {
    syncMode();
    captureDraftConfig();
    enforceBudgetCap(true);
    const payload = {
      strategy_1: refs.strategy1 ? refs.strategy1.value : '',
      strategy_2: refs.mode && refs.mode.value === 'dual' && refs.strategy2 ? refs.strategy2.value : '',
      budget: refs.budget ? refs.budget.value : 100,
      sl: refs.sl ? refs.sl.value : 0,
      tp: refs.tp ? refs.tp.value : 0
    };
    try {
      setNotice('Starting auto session...');
      const data = await postJson('/auto-session/start', payload);
      draftConfig.dirty = false;
      applyStatus((data && data.session) || {});
    } catch (err) {
      setNotice(err && err.message ? err.message : 'Could not start session.');
    }
  }

  async function stopSession() {
    try {
      setNotice('Stopping auto session...');
      const data = await postJson('/auto-session/stop', {});
      draftConfig.dirty = false;
      applyStatus((data && data.session) || {});
    } catch (err) {
      setNotice(err && err.message ? err.message : 'Could not stop session.');
    }
  }

  async function clearHistory() {
    try {
      setNotice('Clearing auto session history...');
      const data = await postJson('/auto-session/clear-history', {});
      if (data && data.dashboard) renderHistory(data.dashboard);
      await fetchStatus();
      setNotice('Auto session history cleared.');
    } catch (err) {
      setNotice(err && err.message ? err.message : 'Could not clear auto session history.');
    }
  }

  async function heartbeat() {
    try {
      await fetch('/heartbeat', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    } catch (_err) {}
  }

  function cleanupRuntime(reason) {
    clearRuntimeIntervals(reason || 'page_cleanup');
    if (runtime.predictionTimer) {
      try { window.clearTimeout(runtime.predictionTimer); } catch (_err) {}
      runtime.predictionTimer = null;
    }
    window.__koolkidAutoTradeRuntimeBooted = false;
  }

  window.addEventListener('pagehide', function (event) {
    if (event && event.persisted) return;
    cleanupRuntime('pagehide');
  });
  window.addEventListener('beforeunload', function () { cleanupRuntime('beforeunload'); });

  if (refs.userInitials) refs.userInitials.textContent = initialsFromName(username).slice(0, 2).toUpperCase();
  if (refs.modeSingle) refs.modeSingle.addEventListener('click', function () { if (refs.mode) refs.mode.value = 'single'; captureDraftConfig(); });
  if (refs.modeDual) refs.modeDual.addEventListener('click', function () { if (refs.mode) refs.mode.value = 'dual'; captureDraftConfig(); });
  if (refs.mode) refs.mode.addEventListener('change', captureDraftConfig);
  if (refs.strategy1) refs.strategy1.addEventListener('change', captureDraftConfig);
  if (refs.strategy2) refs.strategy2.addEventListener('change', captureDraftConfig);
  if (refs.budget) {
    refs.budget.addEventListener('input', function () { captureDraftConfig(); enforceBudgetCap(false); });
    refs.budget.addEventListener('change', function () { captureDraftConfig(); enforceBudgetCap(true); });
  }
  if (refs.sl) {
    refs.sl.addEventListener('input', captureDraftConfig);
    refs.sl.addEventListener('change', captureDraftConfig);
  }
  if (refs.tp) {
    refs.tp.addEventListener('input', captureDraftConfig);
    refs.tp.addEventListener('change', captureDraftConfig);
  }
  if (refs.start) {
    refs.start.addEventListener('click', function () {
      const running = !!(runtime.lastStatus && runtime.lastStatus.running);
      if (running) {
        stopSession();
      } else {
        startSession();
      }
    });
  }
  if (refs.stop) refs.stop.addEventListener('click', stopSession);
  if (refs.historyClear) refs.historyClear.addEventListener('click', clearHistory);
  if (refs.historyClearMobile) refs.historyClearMobile.addEventListener('click', clearHistory);
  if (refs.historySwipeToggleMobile) {
    refs.historySwipeToggleMobile.addEventListener('click', function () {
      runtime.mobileHistorySwipeOn = !runtime.mobileHistorySwipeOn;
      syncMobileHistorySwipe();
    });
  }

  applyStatus(initialStatus);
  renderHistory(initialDashboard);
  syncMobileHistorySwipe();
  syncMode();
  tickClock();
  animateChart();
  fetchStatus();
  registerRuntimeInterval('auto_session_status_poll', fetchStatus, 2500);
  registerRuntimeInterval('auto_session_heartbeat', heartbeat, 20000);
  registerRuntimeInterval('auto_session_clock', tickClock, 1000);
  registerRuntimeInterval('auto_session_chart_animation', animateChart, 800);
})();
