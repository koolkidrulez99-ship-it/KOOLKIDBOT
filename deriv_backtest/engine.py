import json
import math
import os
import queue
import time
import uuid
from collections import deque
from decimal import Decimal

from .statistics import WINDOWS, accumulate, empty, report
from .store import Secrets, Store
from .strategies import REGISTRY, evaluate
from .transport import Feed, ResearchError
from .confirmation import signature


class ResearchEngine:
    def __init__(self, store, registry=REGISTRY):
        self.store = store
        self.registry = registry
        self.markets = {}
        self.buffers = {}
        self.seq = {}
        self.last_epochs = {}
        self.pending = {}
        self.recent = {}
        self.totals = {}
        self.variant_totals = {}
        self.payouts = {}
        self.write_batch = []
        self.setup_batch = []
        self.paper_batch = []
        self.connection = uuid.uuid4().hex
        self.last_tick = 0.
        self.received = 0
        self.started = time.time()
        self.top = set()
        self.rank_at = 0.
        self.last_quote_request = 0.
        self.subscribed = set()
        self.quote_needed = deque(maxlen=100)
        self.restore()

    def restore(self):
        with self.store.connect() as db:
            for row in db.execute('SELECT symbol,value FROM markets'):
                self.markets[row[0]] = json.loads(row[1])
            self.totals = self.store.get('totals', {})
            self.variant_totals = self.store.get('variant_totals', {})
            self.seq = self.store.get('sequences', {})
            self.last_epochs = self.store.get('last_epochs', {})
            for symbol in self.markets:
                ticks = list(db.execute('SELECT * FROM ticks WHERE symbol=? ORDER BY seq DESC LIMIT 500', (symbol,)))
                ticks.reverse()
                self.buffers[symbol] = deque((dict(t) for t in ticks), maxlen=500)
                if ticks:
                    self.seq[symbol] = max(self.seq.get(symbol, 0), ticks[-1]['seq'])
                    self.last_epochs[symbol] = ticks[-1]['epoch']
                for strategy in self.registry:
                    key = symbol + ':' + strategy.id
                    rows = db.execute('SELECT value FROM papers WHERE symbol=? AND strategy=? AND exit_seq>? ORDER BY exit_seq',
                        (symbol, strategy.id, self.seq.get(symbol, 0) - 500))
                    self.recent[key] = deque((json.loads(r[0]) for r in rows), maxlen=500)

    def set_market(self, symbol, label, precision, contracts):
        value = dict(symbol=symbol, label=label, precision=precision, contracts=contracts)
        self.markets[symbol] = value
        self.buffers.setdefault(symbol, deque(maxlen=500))
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO markets VALUES(?,?)', (symbol, json.dumps(value)))

    def ingest(self, symbol, quote, epoch, precision, received=None, origin='forward', analyze=True):
        if symbol not in self.markets:
            return
        received = received or time.time()
        price = Decimal(str(quote))
        if not price.is_finite() or not 0 <= precision <= 12:
            return
        formatted = f'{price:.{precision}f}'
        digit = int(formatted[-1])
        buf = self.buffers[symbol]
        # Historical warm-start may overlap retained data. Live duplicate delivery is rejected too.
        if epoch <= self.last_epochs.get(symbol, 0):
            return
        self.last_epochs[symbol] = epoch
        seq = self.seq.get(symbol, 0) + 1
        self.seq[symbol] = seq
        tick = dict(symbol=symbol, quote=formatted, epoch=epoch, digit=digit, seq=seq, received=received, precision=precision)
        buf.append(tick)
        self.write_batch.append((symbol, epoch, formatted, precision, digit, received, self.connection, origin, seq))
        self.received += 1
        if origin == 'forward':
            self.last_tick = received
        for strategy in self.registry:
            key = symbol + ':' + strategy.id
            pending = self.pending.get(key)
            if pending and seq >= pending['entry_seq'] + strategy.duration:
                # Crossing a connection gap cannot count as a one-tick outcome.
                if pending['connection'] == self.connection:
                    pending.update(exit_seq=seq, exit_digit=digit, won=evaluate(pending['contract'], pending['barrier'], digit))
                    ratio = pending['payout_ratio']
                    pending['profit'] = (ratio - 1 if pending['won'] else -1.) if ratio is not None else None
                    self.settle(key, pending)
                del self.pending[key]
        if not analyze:
            return
        if received - self.rank_at >= 2:
            self.rank_at = received
            fresh = [s for s, b in self.buffers.items() if b and received-b[-1]['received'] <= 15]
            def cheap_score(s):
                digits = [t['digit'] for t in list(self.buffers[s])[-50:]]
                counts = [digits.count(d) for d in range(10)]
                return (max(counts)-min(counts)) / max(1, len(digits))
            ranked = sorted(fresh, key=cheap_score, reverse=True)
            self.top = set(ranked[:5])
        for strategy in self.registry:
            key = symbol + ':' + strategy.id
            if key in self.pending or len(buf) < strategy.required:
                continue
            if not all(c in self.markets[symbol]['contracts'] for c in strategy.contracts):
                continue
            if strategy.id in {'golden', 'differ_safe'} and origin == 'forward' and symbol not in self.top:
                continue
            signal = strategy.detector([t['digit'] for t in buf])
            if not signal:
                continue
            contract, barrier = signal
            price_key = (symbol, contract, barrier, strategy.duration)
            payout = self.payouts.get(price_key)
            ratio = payout['ratio'] if payout and 0 <= received - payout['observed'] <= 60 and origin == 'forward' else None
            if origin == 'forward' and ratio is None and price_key not in self.quote_needed:
                self.quote_needed.append(price_key)
            paper = dict(id=uuid.uuid4().hex, symbol=symbol, strategy=strategy.id,
                entry_seq=seq, created=epoch, contract=contract, barrier=barrier,
                analysis_start_seq=seq - strategy.required + 1,
                duration=strategy.duration, connection=self.connection, origin=origin,
                payout_ratio=ratio, pricing='observed proposal, unit stake' if ratio else 'unpriced')
            self.pending[key] = paper
            self.setup_batch.append((paper['id'], symbol, strategy.id, seq, epoch, json.dumps(paper)))

    def settle(self, key, paper):
        self.recent.setdefault(key, deque(maxlen=500)).append(dict(paper))
        accumulate(self.totals.setdefault(key, empty()), paper)
        if paper.get('contract'):
            variant = signature(paper['contract'], paper.get('barrier'), paper.get('duration', 1))
            accumulate(self.variant_totals.setdefault(key, {}).setdefault(variant, empty()), paper)
        self.paper_batch.append((paper['id'], paper['symbol'], paper['strategy'], paper['entry_seq'],
                                 paper['exit_seq'], paper['created'], json.dumps(paper)))

    def flush(self):
        if not (self.write_batch or self.paper_batch or self.setup_batch):
            return
        # Ticks, outcomes and cumulative state commit together, at most every two seconds.
        with self.store.connect() as db:
            db.executemany('INSERT OR IGNORE INTO ticks(symbol,epoch,quote,precision,digit,received,connection,origin,seq) VALUES(?,?,?,?,?,?,?,?,?)', self.write_batch)
            db.executemany('INSERT OR IGNORE INTO setups VALUES(?,?,?,?,?,?)', self.setup_batch)
            db.executemany('INSERT OR IGNORE INTO papers VALUES(?,?,?,?,?,?,?)', self.paper_batch)
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('totals', json.dumps(self.totals)))
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('variant_totals', json.dumps(self.variant_totals)))
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('sequences', json.dumps(self.seq)))
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('last_epochs', json.dumps(self.last_epochs)))
            # Bound raw tick storage without touching cumulative paper outcomes/statistics.
            max_ticks = max(1, int(os.environ.get('KOOLKID_INTELLIGENCE_MAX_TICKS', '500')))
            touched = {row[0] for row in self.write_batch}
            for symbol in touched:
                cutoff_seq = int(self.seq.get(symbol, 0)) - max_ticks + 1
                if cutoff_seq > 0:
                    db.execute('DELETE FROM ticks WHERE symbol=? AND seq<?', (symbol, cutoff_seq))
        self.write_batch.clear()
        self.setup_batch.clear()
        self.paper_batch.clear()

    def snapshots(self, now=None):
        now = now or time.time()
        self.flush()
        with self.store.connect() as db:
            for window in WINDOWS:
                rows = []
                for symbol, market in self.markets.items():
                    for strategy in self.registry:
                        if not all(c in market['contracts'] for c in strategy.contracts):
                            continue
                        key = symbol + ':' + strategy.id
                        head = self.seq.get(symbol, 0)
                        stats = self.totals.get(key, empty()) if window == 'ALL' else empty()
                        variants = self.variant_totals.get(key, {}) if window == 'ALL' else {}
                        if window != 'ALL':
                            boundary = max(0, head - int(window))
                            for paper in self.recent.get(key, ()):
                                # BOTH setup and settlement must lie in the selected tick dataset.
                                if paper.get('analysis_start_seq', paper['entry_seq']) > boundary and paper['exit_seq'] <= head:
                                    accumulate(stats, paper)
                                    if paper.get('contract'):
                                        variant = signature(paper['contract'], paper.get('barrier'), paper.get('duration', 1))
                                        accumulate(variants.setdefault(variant, empty()), paper)
                        rows.append(dict(symbol=symbol, market=market['label'], strategy=strategy.id,
                            bot=strategy.name, window=window,
                            variants={k: report(v, head if window == 'ALL' else min(head, int(window))) for k, v in variants.items()},
                            latest_market_tick=self.last_epochs.get(symbol),
                            market_live=symbol in self.subscribed and bool(self.buffers.get(symbol)) and now-self.buffers[symbol][-1]['epoch']<30,
                            **report(stats, head if window == 'ALL' else min(head, int(window)))))
                rows.sort(key=lambda r: (r['score'] is not None, r['score'] or 0, r['paper_trades']), reverse=True)
                db.execute('INSERT OR REPLACE INTO snapshots VALUES(?,?,?)', (window, now, json.dumps(rows)))
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('sequences', json.dumps(self.seq)))

    def health(self, state, connected=False, error=''):
        payload = dict(state=state, connected=connected, authorized=connected, error=error,
            markets_monitored=len(self.subscribed), markets_stored=len(self.markets), bots_tracked=len(self.registry), ticks_received=self.received,
            historical_records=sum(self.seq.values()), paper_trades=sum(s['trades'] for s in self.totals.values()),
            latest_tick=self.last_tick or None, updated=time.time(), uptime=time.time()-self.started,
            database='ONLINE', strategies=[dict(id=s.id, name=s.name) for s in self.registry])
        payload['test_result'] = self.store.get('test_result', '')
        self.store.set('health', payload)

    def observe_payout(self, feed):
        if not self.quote_needed or time.time() - self.last_quote_request < 2:
            return
        self.last_quote_request = time.time()
        key = self.quote_needed.popleft()
        symbol, contract, barrier, duration = key
        response = feed.request(dict(proposal=1, amount=1, basis='stake', currency=feed.currency,
            contract_type=contract, barrier=str(barrier), duration=duration, duration_unit='t', underlying_symbol=symbol))
        proposal = response.get('proposal') or {}
        ask, payout = float(proposal.get('ask_price') or 0), float(proposal.get('payout') or 0)
        if not math.isfinite(ask + payout) or ask <= 0 or payout <= 0:
            return
        observed = time.time()
        value = dict(ratio=payout/ask, observed=observed, contract=contract, barrier=barrier, duration=duration)
        self.payouts[key] = value
        with self.store.connect() as db:
            db.execute('INSERT INTO payouts(symbol,observed,value) VALUES(?,?,?)', (symbol, observed, json.dumps(value)))


def precision_of(item):
    if item.get('pip_size') is not None:
        return int(item['pip_size'])
    return max(0, -Decimal(str(item.get('pip', '.01'))).normalize().as_tuple().exponent)


def supported_tick_contracts(data, duration=1):
    contracts = set()
    for row in data.get('available', []):
        minimum = str(row.get('min_contract_duration', ''))
        maximum = str(row.get('max_contract_duration', ''))
        if not minimum.endswith('t'):
            continue
        try:
            if int(minimum[:-1]) > duration:
                continue
            if maximum.endswith('t') and int(maximum[:-1]) < duration:
                continue
        except ValueError:
            continue
        if row.get('contract_type'):
            contracts.add(row['contract_type'])
    return sorted(contracts)


def run_engine():
    store = Store()
    engine = ResearchEngine(store)
    backoff = 2
    seen_revision = None
    while True:
        if not store.get('enabled', Secrets(store).configured()):
            engine.health('STOPPED')
            time.sleep(1)
            continue
        feed = None
        try:
            engine.health('AUTHORIZING')
            feed = Feed(Secrets(store).load(), os.environ.get('KOOLKID_INTELLIGENCE_APP_ID') or store.get('app_id', ''),
                        os.environ.get('KOOLKID_INTELLIGENCE_ACCOUNT_ID', ''))
            feed.connect()
            engine.connection = uuid.uuid4().hex
            engine.pending.clear()
            engine.payouts.clear()
            seen_revision = store.get('revision', 0)
            engine.health('LOADING_HISTORY', True)
            active = feed.request({'active_symbols': 'brief'}).get('active_symbols', [])
            connected_symbols = set()
            engine.subscribed = connected_symbols
            for item in active:
                if not store.get('enabled', True):
                    break
                symbol = item.get('symbol') or item.get('underlying_symbol')
                if not symbol:
                    continue
                try:
                    metadata = store.get('contracts:' + symbol)
                    if not metadata or time.time() - metadata['updated'] > 1200:
                        data = feed.request({'contracts_for': symbol}).get('contracts_for', {})
                        contracts = supported_tick_contracts(data)
                        metadata = dict(updated=time.time(), contracts=contracts)
                        store.set('contracts:' + symbol, metadata)
                    contracts = metadata['contracts']
                    if not any(all(c in contracts for c in s.contracts) for s in engine.registry):
                        continue
                    precision = precision_of(item)
                    engine.set_market(symbol, item.get('display_name') or symbol, precision, contracts)
                    response = feed.request(dict(ticks_history=symbol, end='latest', count=500, style='ticks', subscribe=1))
                    history = response.get('history') or {}
                    # Gaps invalidate old pending setups; warm history is replayed chronologically.
                    engine.pending = {k:v for k,v in engine.pending.items() if v['symbol'] != symbol}
                    previous = list(engine.buffers[symbol])
                    times = history.get('times', [])
                    if len(previous) >= 2 and times:
                        interval = max(1, previous[-1]['epoch'] - previous[-2]['epoch'])
                        if times[0] - previous[-1]['epoch'] > interval * 3:
                            engine.buffers[symbol].clear()
                    for epoch, price in zip(history.get('times', []), history.get('prices', [])):
                        engine.ingest(symbol, price, epoch, precision, origin='historical')
                    engine.pending = {k:v for k,v in engine.pending.items() if v['symbol'] != symbol}
                    connected_symbols.add(symbol)
                    engine.health('SUBSCRIBING', True)
                except ResearchError:
                    continue
            if not connected_symbols:
                raise ResearchError('No supported digit markets subscribed.')
            # Removed markets are retained for historical reporting, but marked inactive.
            store.set('subscribed_markets', sorted(connected_symbols))
            next_snapshot = next_ping = next_health = 0
            refresh_metadata_at = time.time() + 1200
            backoff = 2
            while not feed.closed.is_set() and store.get('enabled', True):
                now = time.time()
                if store.get('revision', 0) != seen_revision or now > refresh_metadata_at:
                    break
                try:
                    tick, received = feed.events.get(timeout=.2)
                    symbol = tick.get('symbol') or tick.get('underlying_symbol')
                    if symbol in connected_symbols:
                        precision = int(tick.get('pip_size', engine.markets[symbol]['precision']))
                        engine.ingest(symbol, tick['quote'], tick['epoch'], precision, received,
                                      analyze=time.time()-received<10)
                except queue.Empty:
                    pass
                if now >= next_health:
                    stale = not engine.last_tick or now-engine.last_tick > 15
                    engine.health('DEGRADED' if stale else 'READY', True)
                    engine.flush()
                    next_health = now + 2
                    if engine.last_tick and now - engine.last_tick > 45:
                        raise ResearchError('Global market data is stale; reconnecting.')
                if now >= next_snapshot:
                    engine.snapshots()
                    engine.store.trim_ticks(int(os.environ.get('KOOLKID_INTELLIGENCE_MAX_TICKS', '500')))
                    next_snapshot = now + 10
                if now >= next_ping:
                    feed.request({'ping': 1})
                    next_ping = now + 25
                test_requested = store.get('test_requested', 0)
                if test_requested > store.get('test_completed', 0):
                    feed.request({'balance': 1})
                    store.set('test_result', 'Authenticated socket responded successfully')
                    store.set('test_completed', test_requested)
                if feed.events.qsize() < 10:
                    try:
                        engine.observe_payout(feed)
                    except ResearchError:
                        pass
        except Exception as exc:
            message = str(exc) if isinstance(exc, ResearchError) else 'Research engine error. Check configuration and database access.'
            engine.health('ERROR', False, message)
        finally:
            if feed:
                feed.close()
            engine.pending.clear()
            engine.subscribed = set()
            engine.flush()
            engine.snapshots()
        for _ in range(backoff):
            if not store.get('enabled', True) or store.get('revision', 0) != seen_revision:
                break
            time.sleep(1)
        backoff = min(60, backoff * 2)
