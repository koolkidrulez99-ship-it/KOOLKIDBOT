import json
import time
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from collections import deque

import pytest
from flask import Flask, session

from deriv_backtest.engine import ResearchEngine, supported_tick_contracts
from deriv_backtest.statistics import accumulate, empty, report, WINDOWS
from deriv_backtest.store import Store, Secrets
from deriv_backtest.strategies import Strategy, REGISTRY, absence, evaluate
from deriv_backtest.transport import Feed, ResearchError
from deriv_backtest.web import register, validate_setup


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'research.sqlite3')


@pytest.fixture
def app(store):
    app = Flask(__name__, template_folder='../templates')
    app.secret_key = 'isolated-test'
    register(app, lambda: bool(session.get('user')), lambda: session.get('user') == 'admin', store)
    return app


def paper(index, won=True, ratio=1.8, origin='forward'):
    return dict(id=str(index), symbol='R_25', strategy='probe', entry_seq=index-1,
                analysis_start_seq=index-1, exit_seq=index, created=index,
                won=won, payout_ratio=ratio, profit=(ratio-1 if won else -1) if ratio else None,
                origin=origin)


def test_transport_forbids_execution_before_touching_socket():
    feed = Feed('global-secret', 'global-app')
    for payload in ({'buy':'id','price':1}, {'sell':'id'}, {'proposal':1,'buy':'id'},
                    {'authorize':'global-secret'}, {'cashier':1}, {'balance':1,'ping':1}):
        with pytest.raises(ResearchError, match='not allowed'):
            feed.request(payload)


def test_local_encryption_survives_new_store(store, monkeypatch):
    monkeypatch.delenv('KOOLKID_INTELLIGENCE_KEY', raising=False)
    Secrets(store).save('test-demo-pat')
    assert Secrets(Store(store.path)).load() == 'test-demo-pat'
    assert 'test-demo-pat' not in store.get('encrypted_pat')


@pytest.mark.parametrize('account', [
    {'account_id': 'real', 'account_type': 'real'},
    {'account_id': 'real', 'is_virtual': 'false'},
])
def test_research_refuses_real_only_accounts(monkeypatch, account):
    feed = Feed('test-pat', 'app')
    monkeypatch.setattr(feed, 'rest', lambda *args: {'data': [account]})
    with pytest.raises(ResearchError, match='demo Options account'):
        feed.connect()


def test_research_refuses_real_otp_url(monkeypatch):
    feed = Feed('test-pat', 'app')
    responses = iter([{'data': [{'account_id': 'demo', 'account_type': 'demo'}]},
                      {'data': {'url': 'wss://api.derivws.com/trading/v1/options/ws/real?otp=secret'}}])
    monkeypatch.setattr(feed, 'rest', lambda *args: next(responses))
    with pytest.raises(ResearchError, match='unexpected WebSocket URL'):
        feed.connect()


def test_supported_markets_must_offer_the_actual_paper_duration():
    rows=[{'contract_type':'DIGITUNDER','min_contract_duration':'1t','max_contract_duration':'10t'},
          {'contract_type':'DIGITOVER','min_contract_duration':'5t','max_contract_duration':'10t'},
          {'contract_type':'CALL','min_contract_duration':'1m'}]
    assert supported_tick_contracts({'available':rows})==['DIGITUNDER']


def test_signal_requires_ten_absent_then_target():
    assert absence([1]*10+[9],9,'DIGITUNDER') == ('DIGITUNDER',9)
    assert absence([1]*9+[9],9,'DIGITUNDER') is None
    assert absence([1]*5+[9]+[1]*4+[9],9,'DIGITUNDER') is None
    assert absence([1]*10+[0],0,'DIGITOVER') == ('DIGITOVER',0)


def test_paper_waits_for_next_tick_no_lookahead(store):
    strategy = Strategy('probe','Probe',1,('DIGITUNDER',),lambda d: ('DIGITUNDER',9))
    engine = ResearchEngine(store, (strategy,))
    engine.set_market('R_25','V25',2,['DIGITUNDER'])
    engine.ingest('R_25','100.19',1,2)
    assert not engine.totals
    engine.ingest('R_25','100.12',2,2)
    assert engine.totals['R_25:probe']['wins'] == 1
    assert engine.totals['R_25:probe']['priced'] == 0
    engine.ingest('R_25','100.12',2,2)
    assert engine.totals['R_25:probe']['trades'] == 1


def test_price_precision_preserves_trailing_zero(store):
    engine = ResearchEngine(store)
    engine.set_market('R_25','V25',3,['DIGITUNDER'])
    engine.ingest('R_25',100.12,1,3,analyze=False)
    assert engine.buffers['R_25'][-1]['digit'] == 0


@pytest.mark.parametrize('window',WINDOWS)
def test_window_uses_actual_tick_boundaries(store,window):
    strategy=Strategy('probe','Probe',1,('DIGITUNDER',),lambda d:None)
    e=ResearchEngine(store,(strategy,))
    e.set_market('R_25','V25',2,['DIGITUNDER'])
    e.seq['R_25']=600
    rows=[paper(i,won=i>500) for i in range(2,601)]
    e.recent['R_25:probe']=deque(rows[-500:],maxlen=500)
    stats=empty()
    for row in rows: accumulate(stats,row)
    e.totals['R_25:probe']=stats
    e.snapshots()
    row=store.snapshot(window)['rows'][0]
    expected=599 if window=='ALL' else int(window)-1
    assert row['paper_trades']==expected
    assert row['sample_count']==(600 if window=='ALL' else int(window))


def test_rankings_change_with_window_and_low_sample_protection(store):
    strategy=Strategy('probe','Probe',1,('DIGITUNDER',),lambda d:None)
    e=ResearchEngine(store,(strategy,))
    e.set_market('R_25','V25',2,['DIGITUNDER'])
    e.seq['R_25']=500
    rows=[paper(i,i>450) for i in range(2,501)]
    e.recent['R_25:probe']=deque(rows)
    stats=empty()
    for row in rows:accumulate(stats,row)
    e.totals['R_25:probe']=stats
    e.snapshots()
    assert store.snapshot('50')['rows'][0]['score'] != store.snapshot('500')['rows'][0]['score']
    small=empty()
    for i in range(9):accumulate(small,paper(i))
    assert report(small,50)['status']=='INSUFFICIENT_DATA'
    assert report(small,50)['score']<10


def test_restart_restores_all_data_after_raw_retention(store):
    e=ResearchEngine(store)
    e.set_market('R_25','V25',2,['DIGITUNDER'])
    for i,d in enumerate([1]*10+[9,2],1):e.ingest('R_25','100.'+str(d),i,1,received=1)
    e.snapshots()
    before=store.snapshot('ALL')['rows']
    store.prune(1)
    restored=ResearchEngine(store)
    restored.snapshots()
    assert store.snapshot('ALL')['rows']==before


def test_100_viewers_read_snapshots_without_feeds_or_tick_queries(app,store,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Reader opened a feed')
    monkeypatch.setattr(Feed,'connect',forbidden)
    with store.connect() as db:
        db.execute('INSERT INTO snapshots VALUES(?,?,?)',('50',time.time(),'[]'))
    queries=[]
    original=store.connect
    @contextmanager
    def traced():
        with original() as db:
            db.set_trace_callback(queries.append)
            yield db
    monkeypatch.setattr(store,'connect',traced)
    def view(index):
        with app.test_client() as client:
            with client.session_transaction() as s:s['user']=f'user{index}';s['api_token']='user-pat'
            response=client.get('/backtest-tools/api/rankings?window=50')
            assert response.status_code==200
            assert 'user-pat' not in response.get_data(as_text=True)
            with client.session_transaction() as s:assert s['api_token']=='user-pat'
    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(view,range(100)))
    assert not any('FROM TICKS' in sql.upper() for sql in queries)


def test_admin_only_and_csrf(app,store):
    with app.test_client() as client:
        assert client.get('/backtest-tools/api/rankings').status_code==401
        with client.session_transaction() as s:s['user']='tester'
        assert client.post('/admin/intelligence/start').status_code==403
        with client.session_transaction() as s:s['user']='admin'
        assert client.post('/admin/intelligence/start').status_code==403
        csrf=client.get('/admin/intelligence/status').json['csrf']
        assert client.post('/admin/intelligence/stop',headers={'X-Intelligence-CSRF':csrf}).status_code==200
        assert store.get('enabled') is False


def test_encrypted_secret_never_returned(app,store,monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv('KOOLKID_INTELLIGENCE_KEY',Fernet.generate_key().decode())
    Secrets(store).save('dedicated-global-secret')
    assert 'dedicated-global-secret' not in store.get('encrypted_pat')
    assert Secrets(store).load()=='dedicated-global-secret'
    with app.test_client() as c:
        with c.session_transaction() as s:s['user']='admin';s['oauth_token']='user-oauth'
        assert 'dedicated-global-secret' not in c.get('/admin/intelligence/status').get_data(as_text=True)
        with c.session_transaction() as s:assert s['oauth_token']=='user-oauth'


def test_stale_engine_cannot_approve(store):
    store.set('health',dict(state='READY',updated=1,connected=True))
    assert validate_setup(store,'under9','R_25')['decision']=='WAIT'


def test_payout_is_unknown_until_observed_and_never_backfilled(store):
    strategy=Strategy('probe','Probe',1,('DIGITUNDER',),lambda d:('DIGITUNDER',9))
    e=ResearchEngine(store,(strategy,))
    e.set_market('R_25','V25',2,['DIGITUNDER'])
    e.ingest('R_25',100.1,1,1,received=100)
    e.payouts[('R_25','DIGITUNDER',9,1)]={'ratio':1.1,'observed':101}
    e.ingest('R_25',100.1,2,1,received=102)
    assert e.totals['R_25:probe']['priced']==0
    e.ingest('R_25',100.1,3,1,received=103)
    assert e.totals['R_25:probe']['priced']==1


def test_historical_cannot_use_current_payout(store):
    e=ResearchEngine(store)
    e.set_market('R_25','V25',1,['DIGITUNDER'])
    e.payouts[('R_25','DIGITUNDER',9,1)]={'ratio':1.1,'observed':time.time()}
    for i,d in enumerate([1]*10+[9,2],1):e.ingest('R_25',f'100.{d}',i,1,origin='historical')
    assert e.totals['R_25:under9']['priced']==0


def test_setup_lookback_must_fit_inside_window(store):
    s=Strategy('probe','Probe',20,('DIGITUNDER',),lambda d:None)
    e=ResearchEngine(store,(s,));e.set_market('R_25','V25',1,['DIGITUNDER']);e.seq['R_25']=100
    row=paper(60);row['analysis_start_seq']=40
    e.recent['R_25:probe']=deque([row]);e.snapshots()
    assert store.snapshot('50')['rows'][0]['paper_trades']==0
    assert store.snapshot('100')['rows'][0]['paper_trades']==1


def test_only_one_daemon_can_own_data_directory(tmp_path):
    env={**os.environ,'KOOLKID_INTELLIGENCE_DIR':str(tmp_path),'KOOLKID_GLOBAL_DERIV_PAT':''}
    store=Store(tmp_path/'research.sqlite3');store.set('enabled',False)
    options=dict(env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if os.name=='nt':options['creationflags']=subprocess.CREATE_NO_WINDOW
    first=subprocess.Popen([sys.executable,'-m','deriv_backtest'],**options)
    second=None
    try:
        deadline=time.time()+10
        while time.time()<deadline and not store.get('health'):
            time.sleep(.05)
        assert store.get('health')['state']=='STOPPED'
        second=subprocess.Popen([sys.executable,'-m','deriv_backtest'],**options)
        assert second.wait(timeout=10)==0
        assert first.poll() is None
    finally:
        first.terminate();first.wait(timeout=10)
        if second and second.poll() is None:second.terminate();second.wait(timeout=10)


def test_reconnect_marker_never_resolves_missing_tick(store):
    strategy=Strategy('probe','Probe',1,('DIGITUNDER',),lambda d:('DIGITUNDER',9))
    e=ResearchEngine(store,(strategy,));e.set_market('R_25','V25',1,['DIGITUNDER'])
    e.ingest('R_25',100.1,1,1)
    e.connection='replacement-socket'
    e.ingest('R_25',100.1,2,1)
    assert not e.totals


def test_global_module_has_no_user_execution_or_mt5_imports():
    import ast
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]/'deriv_backtest'
    for path in root.glob('*.py'):
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):
                assert not (node.module or '').startswith(('server','mt5_module'))
            if isinstance(node,ast.Import):
                assert not any(n.name.startswith(('server','mt5_module')) for n in node.names)


def test_secret_save_requires_https_for_remote_admin(app,store,monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv('KOOLKID_INTELLIGENCE_KEY',Fernet.generate_key().decode())
    with app.test_client() as c:
        with c.session_transaction() as s:s['user']='admin';s['intelligence_csrf']='test'
        response=c.post('/admin/intelligence/save',base_url='http://localhost',
            headers={'Host':'untrusted.example','X-Intelligence-CSRF':'test'},json={'pat':'secret-global'})
        assert response.status_code in {400,403}
