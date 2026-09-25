import copy
import json
import time
from types import SimpleNamespace

import pytest

import server
from deriv_backtest import confirmation as gate
from deriv_backtest.store import Store


@pytest.fixture
def ready(isolated_confirmation_store):
    db = isolated_confirmation_store
    db.set('confirmation_policy', {})
    db.set('enabled', True)
    db.set('health', dict(state='READY', connected=True, authorized=True, updated=time.time()))
    stats = dict(paper_trades=100, forward_samples=100, data_quality=1., ev=.1,
                 score=75., max_drawdown=2., longest_losing_streak=2, win_rate=95.)
    row = dict(strategy='under9', symbol='R_25', market='Volatility 25', market_live=True,
               latest_market_tick=time.time(), variants={'DIGITUNDER:9:1:t': stats}, **stats)
    with db.connect() as conn:
        conn.execute('INSERT OR REPLACE INTO snapshots VALUES(?,?,?)', ('500', time.time(), json.dumps([row])))
    return db, row


def write_row(db, row, updated=None):
    with db.connect() as conn:
        conn.execute('INSERT OR REPLACE INTO snapshots VALUES(?,?,?)', ('500', updated or time.time(), json.dumps([row])))


def meta(**changes):
    return dict(profile='CLOUD', mode='CLOUD_REINVEST_100', cloud_strategy='under9',
                symbol='R_25', deriv_contract_type='DIGITUNDER', barrier=9, duration=1,
                duration_unit='t', stake=3.5, **changes)


def test_default_is_required_without_saved_policy(ready):
    db, _ = ready
    assert gate.policy(db)['enabled'] is True
    assert gate.policy(db)['window'] == '500'


def test_approval_keeps_stake_and_strategy_state_and_persists_private_audit(ready):
    db, _ = ready
    state = {'username': 'alice', 'current_stake': 3.5, 'martingale_step': 4}
    order = meta()
    assert gate.check(state, order, db) is None
    assert order['stake'] == 3.5 and state['martingale_step'] == 4
    assert db.decisions('alice')[0]['decision'] == 'APPROVE'
    assert db.decisions('bob') == []


@pytest.mark.parametrize('field,value,decision', [
    ('paper_trades', 19, 'WAIT'), ('forward_samples', 9, 'WAIT'),
    ('data_quality', .94, 'WAIT'), ('ev', 0, 'REJECT'), ('ev', -.1, 'REJECT'),
    ('ev', float('nan'), 'WAIT'), ('score', 9, 'REJECT'),
    ('max_drawdown', 6, 'REJECT'), ('longest_losing_streak', 6, 'REJECT'),
])
def test_exact_contract_statistics_enforced(ready, field, value, decision):
    db, row = ready
    row['variants']['DIGITUNDER:9:1:t'][field] = value
    write_row(db, row)
    state = {'username': 'alice', 'martingale_step': 2, 'current_stake': 4}
    assert gate.check(state, meta(), db).startswith('Backtest ' + decision)
    assert (state['martingale_step'], state['current_stake']) == (2, 4)


@pytest.mark.parametrize('change', [
    {'symbol': 'R_50'}, {'duration': 2}, {'barrier': 8}, {'duration_unit': 's'},
    {'cloud_strategy': 'unknown'}, {'cloud_strategy': 'under9_reinvest'},
    {'cloud_strategy': None, 'mode': 'golden_card'},
])
def test_other_markets_strategies_and_contracts_cannot_approve(ready, change):
    db, _ = ready
    order = meta(); order.update(change)
    assert gate.check({}, order, db).startswith('Backtest WAIT')


@pytest.mark.parametrize('failure', ['health_stale', 'cache_stale', 'market_stale', 'paused', 'disconnected', 'unauthorized'])
def test_stale_or_disconnected_data_blocks(ready, failure):
    db, row = ready
    h = db.get('health')
    if failure == 'health_stale': h['updated'] = time.time() - 31
    if failure == 'disconnected': h['connected'] = False
    if failure == 'unauthorized': h['authorized'] = False
    if failure == 'paused': db.set('enabled', False)
    if failure == 'market_stale': row['latest_market_tick'] = time.time() - 31
    db.set('health', h)
    write_row(db, row, time.time() - 31 if failure == 'cache_stale' else None)
    assert gate.check({}, meta(), db).startswith('Backtest WAIT')


def test_store_failure_never_allows_auto_or_blocks_manual(monkeypatch):
    def broken(): raise OSError('private database path must not escape')
    monkeypatch.setattr(gate, 'store', broken)
    state = {}
    assert gate.check(state, meta()).startswith('Backtest WAIT')
    assert 'private' not in state['backtest_confirmation']['reason']
    assert gate.check({}, {'mode': 'MANUAL'}) is None


def test_admin_bypass_is_explicit_and_audited(ready):
    db, _ = ready
    db.set('confirmation_policy', {'enabled': False})
    assert gate.check({'username': 'alice'}, {'mode': 'unknown_auto'}, db) is None
    assert db.decisions('alice')[0]['decision'] == 'BYPASS'


@pytest.mark.parametrize('mode', [None, 'MANUAL', 'manual_trade', 'human_rf', 'AI_INTELLIGENCE'])
def test_manual_intents_unaffected(mode):
    assert gate.automated({'mode': mode}) is False
    assert gate.automated({'mode': mode, 'automated': True}) is True


class Socket:
    def __init__(self): self.messages = []
    def send(self, text): self.messages.append(json.loads(text))


@pytest.mark.parametrize('token_type', ['pat', 'oauth'])
def test_common_execution_rejects_before_routing_or_socket(ready, monkeypatch, token_type):
    state = {'ws': Socket(), 'api_token_type': token_type, 'req_meta': {}, 'username': 'alice'}
    monkeypatch.setattr(server, '_ensure_trade_socket_ready', lambda *a, **k: (True, ''))
    monkeypatch.setattr(server, '_execute_oauth_options_trade_engine', lambda *a, **k: pytest.fail('Rejected intent reached broker engine'))
    request = dict(client_id='cid', state=state, contract_type='DIGITUNDER', stake=2,
                   symbol='R_25', barrier=9, duration=1, mode='unknown_auto')
    ok, message = server.execute_deriv_trade(request)
    assert not ok and message.startswith('Backtest WAIT')
    assert state['ws'].messages == []


def test_final_proposal_check_revalidates_after_data_expires(ready):
    db, _ = ready
    state = {'ws': Socket(), 'username': 'alice', 'req_meta': {1: meta()}}
    assert gate.check(state, state['req_meta'][1], db) is None
    h = db.get('health'); h['updated'] = time.time() - 60; db.set('health', h)
    ok, msg = server._send_buy_from_proposal('cid', state, 1, {'id': 'quoted', 'ask_price': 3.5}, 3.5)
    assert not ok and msg.startswith('Backtest WAIT')
    assert state['ws'].messages == []


def test_approved_proposal_sends_original_order(ready):
    state = {'ws': Socket(), 'username': 'alice', 'req_meta': {1: meta()}}
    ok, _ = server._send_buy_from_proposal('cid', state, 1, {'id': 'quoted', 'ask_price': 3.5}, 3.5)
    assert ok
    assert state['ws'].messages == [{'req_id': 1, 'buy': 'quoted', 'price': 3.5}]


def test_missing_final_provenance_fails_closed(ready):
    state = {'ws': Socket(), 'req_meta': {}}
    ok, msg = server._send_buy_from_proposal('cid', state, 1, {'id': 'quoted'}, 1)
    assert not ok and msg.startswith('Backtest WAIT') and not state['ws'].messages


def test_stateful_signal_not_consumed_without_adapter(ready, monkeypatch):
    strategy = SimpleNamespace(check_auto_trade_signal=lambda: pytest.fail('Sequence consumed'), step=3)
    state = {'strategies': {'JOKERJOE': strategy}, 'active_profile': 'JOKERJOE', 'auto_stake': 8}
    monkeypatch.setattr(server, '_should_emit_ui_event', lambda *a: True)
    server.run_auto_trade('cid', state)
    assert strategy.step == 3 and state['auto_stake'] == 8


def test_variant_totals_persist_and_do_not_mix_barriers(tmp_path):
    from deriv_backtest.engine import ResearchEngine
    from deriv_backtest.strategies import Strategy
    from collections import deque
    db = Store(tmp_path / 'research.sqlite3')
    strat = Strategy('probe', 'Probe', 1, ('DIGITUNDER',), lambda d: None)
    e = ResearchEngine(db, (strat,)); e.set_market('R_25', 'Volatility 25', 2, ['DIGITUNDER'])
    e.seq['R_25'] = 30
    for i in range(1, 21):
        p = dict(id=str(i), symbol='R_25', strategy='probe', contract='DIGITUNDER', barrier=9 if i <= 10 else 8,
                 duration=1, entry_seq=i, exit_seq=i+1, created=i, won=i<=10,
                 profit=.1 if i<=10 else -1, payout_ratio=1.1, origin='forward')
        e.settle('R_25:probe', p)
    e.snapshots(); fresh = ResearchEngine(db, (strat,)); fresh.snapshots()
    for window in ['500', 'ALL']:
        variants = db.snapshot(window)['rows'][0]['variants']
        assert variants['DIGITUNDER:9:1:t']['wins'] == 10
        assert variants['DIGITUNDER:8:1:t']['losses'] == 10


@pytest.mark.parametrize('mode', [
    'koolkid_single_martingale',
    'koolkid_single_martingale_pair',
    'koolkid_target_profit_martingale',
    'koolkid_over3_under6_pair_martingale',
])
def test_koolkid_single_contract_martingale_family_bypasses_backtest_confirmation(mode):
    assert gate.automated({'mode': mode}) is False
    assert gate.automated({'mode': mode, 'automated': True}) is False
    assert gate.check({}, {'mode': mode, 'automated': True}) is None
