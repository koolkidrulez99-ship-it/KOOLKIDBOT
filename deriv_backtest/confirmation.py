"""Read-only pre-buy confirmation. Never alters a strategy, stake or contract."""
import math
import time

from .store import Store

DEFAULT_POLICY = dict(enabled=True, window='500', min_trades=20, min_forward=10,
                      min_coverage=.95, min_score=10., max_drawdown=5., max_losing_streak=5)
MANUAL_MODES = {'MANUAL', 'MANUAL_TRADE', 'HUMAN_MANUAL_CONTRACT',
                'HUMAN_DUAL_MARKET_CONTRACTS', 'KOOLKID_PAIR_MANUAL', 'HUMAN_RF', 'AI_INTELLIGENCE'}
BACKTEST_EXEMPT_MODES = {
    'KOOLKID_SINGLE_MARTINGALE',
    'KOOLKID_SINGLE_MARTINGALE_PAIR',
    'KOOLKID_TARGET_PROFIT_MARTINGALE',
    'KOOLKID_OVER3_UNDER6_PAIR_MARTINGALE',
}
_store = None


def store():
    global _store
    if _store is None:
        _store = Store()
    return _store


def policy(db):
    return {**DEFAULT_POLICY, **db.get('confirmation_policy', {})}


def automated(meta):
    mode = str(meta.get('mode') or '').strip().upper()
    # The KOOLKID Single Contract Martingale family intentionally keeps its
    # original execution flow and is never gated by Backtest Confirmation.
    if mode in BACKTEST_EXEMPT_MODES:
        return False
    # Explicit automation wins over ordinary manual labels. Unknown named modes are guarded.
    if meta.get('automated') or meta.get('cloud_signal_id') or meta.get('auto_cycle_id'):
        return True
    source = str(meta.get('entry_source') or '').upper()
    if source and source not in {'MANUAL', 'MANUAL_TRADE'}:
        return True
    return bool(mode and mode not in MANUAL_MODES)


def strategy_for(meta):
    mode = str(meta.get('mode') or '').upper()
    cloud = str(meta.get('cloud_strategy') or '').lower()
    if cloud == 'under9':
        return 'under9'
    if cloud == 'over0':
        return 'over0'
    # Only map verified research adapters, never infer a strategy from a barrier.
    # Golden Card and SAFE Differ include user-specific filters; an explicit
    # supported research configuration is required before those can approve.
    return None


def requires_adapter():
    """Backend profiles currently lack equivalent stateful research adapters.

    Check before consuming a signal: several legacy detectors increment sequence
    counters while returning it. Never call those detectors merely to reject them.
    """
    try:
        return bool(policy(store())['enabled'])
    except Exception:
        return True


def signature(contract, barrier, duration=1, unit='t'):
    return f'{contract}:{barrier}:{duration}:{unit}'


def assess(db, strategy, symbol, contract_key=None, now=None):
    now = time.time() if now is None else now
    p = policy(db)
    result = dict(decision='WAIT', reason='', strategy=strategy,
                  symbol=symbol, window=p['window'], created=now, statistics=None)
    if not p['enabled']:
        return {**result, 'decision': 'BYPASS', 'reason': 'Confirmation disabled by admin'}
    if not strategy:
        return {**result, 'reason': 'Waiting for an exact strategy research adapter'}
    h = db.get('health', {})
    snap = db.snapshot(p['window'])
    result['data_age'] = max(0, now - (snap.get('updated') or 0))
    if (not db.get('enabled', True) or h.get('state') != 'READY'
            or not h.get('connected') or not h.get('authorized')
            or not 0 <= now - h.get('updated', 0) <= 30 or result['data_age'] > 30):
        return {**result, 'reason': 'Research connection or results are unavailable or stale'}
    row = next((r for r in snap['rows'] if r['strategy'] == strategy and r['symbol'] == symbol), None)
    if not row or not row.get('market_live') or not 0 <= now - (row.get('latest_market_tick') or 0) <= 30:
        return {**result, 'reason': 'Waiting for fresh research on this market'}
    stats = (row.get('variants') or {}).get(contract_key) if contract_key else row
    if stats is None:
        return {**result, 'reason': 'No matching contract, barrier and duration research'}
    result['statistics'] = {k: stats.get(k) for k in (
        'score', 'paper_trades', 'forward_samples', 'data_quality', 'ev',
        'max_drawdown', 'longest_losing_streak', 'win_rate')}
    if stats.get('paper_trades', 0) < p['min_trades'] or stats.get('forward_samples', 0) < p['min_forward']:
        return {**result, 'reason': f"Collecting samples: need {p['min_trades']} outcomes, including {p['min_forward']} live"}
    values = [stats.get(k) for k in ('data_quality', 'ev', 'score', 'max_drawdown', 'longest_losing_streak')]
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        return {**result, 'reason': 'Complete priced research is not available'}
    if stats['data_quality'] < p['min_coverage']:
        return {**result, 'reason': 'Waiting for sufficient observed payout coverage'}
    for failed, reason in (
        (stats['ev'] <= 0, 'Expected value is not positive'),
        (stats['score'] < p['min_score'], 'Research score is below the confirmation threshold'),
        (stats['max_drawdown'] > p['max_drawdown'], 'Paper drawdown exceeds the confirmation limit'),
        (stats['longest_losing_streak'] > p['max_losing_streak'], 'Losing streak exceeds the confirmation limit'),
    ):
        if failed:
            return {**result, 'decision': 'REJECT', 'reason': reason}
    return {**result, 'decision': 'APPROVE', 'reason': 'Fresh matching research passed all confirmation checks'}


def check(state, meta, db=None):
    if not automated(meta):
        return None
    try:
        db = db or store()
        contract = str(meta.get('deriv_contract_type') or meta.get('contract_type') or meta.get('type') or '').upper()
        contract = {'UNDER': 'DIGITUNDER', 'OVER': 'DIGITOVER', 'DIFFERS': 'DIGITDIFF'}.get(contract, contract)
        key = signature(contract, meta.get('barrier'), meta.get('duration', 1), meta.get('duration_unit', 't'))
        result = assess(db, strategy_for(meta), meta.get('symbol'), key)
        result.update(profile=str(meta.get('profile') or ''), mode=str(meta.get('mode') or ''), contract=key)
        db.record_decision(str(state.get('username') or ''), result)
    except Exception:
        result = dict(decision='WAIT', reason='Research confirmation unavailable; trade was not sent',
                      created=time.time(), profile=str(meta.get('profile') or ''), mode=str(meta.get('mode') or ''))
    state['backtest_confirmation'] = result
    meta['backtest_confirmation'] = result
    if result['decision'] in {'APPROVE', 'BYPASS'}:
        return None
    return 'Backtest ' + result['decision'] + ': ' + result['reason']
