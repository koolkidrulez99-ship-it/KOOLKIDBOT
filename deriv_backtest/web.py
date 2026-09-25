import os
import secrets
import subprocess
import sys
import time
from urllib.parse import urlsplit
from pathlib import Path
from flask import jsonify, make_response, render_template, request, session

from .statistics import WINDOWS
from .store import Secrets, Store
from .confirmation import DEFAULT_POLICY, policy, assess


def health(store):
    value = dict(store.get('health', {'state': 'STOPPED'}))
    value['stale'] = time.time() - value.get('updated', 0) > 30
    if value['stale'] and value['state'] != 'STOPPED':
        value.update(state='DEGRADED', connected=False, authorized=False)
    value['pat_configured'] = Secrets(store).configured()
    value['app_id_configured'] = bool(os.environ.get('KOOLKID_INTELLIGENCE_APP_ID') or store.get('app_id'))
    return value


def validate_setup(store, strategy, symbol, window='100'):
    """Read-only future integration interface. Does not route or execute trades."""
    snapshot = store.snapshot(window)
    if health(store).get('state') != 'READY' or time.time() - (snapshot['updated'] or 0) > 30:
        return {'decision': 'WAIT', 'reason': 'Intelligence unavailable or stale'}
    row = next((r for r in snapshot['rows'] if r['symbol'] == symbol and r['strategy'] == strategy), None)
    if not row or row['status'] != 'VALIDATED' or not row.get('market_live'):
        return {'decision': 'WAIT', 'reason': 'Insufficient validated research'}
    return {'decision': 'APPROVE' if row['ev'] > 0 else 'REJECT', 'statistics': row,
            'reason': 'Research comparison only; current setup and user risk checks remain required'}


def register(app, login_required, is_admin, store=None):
    store = store or Store()

    @app.get('/backtest-tools')
    def backtest_tools_page():
        if not login_required():
            return 'Login required', 401
        root = Path(__file__).resolve().parent.parent
        watched = [root / 'static/css/backtest_tools.css', root / 'static/js/backtest_tools.js', root / 'templates/backtest_tools.html']
        try:
            asset_version = str(max(int(path.stat().st_mtime_ns) for path in watched if path.exists()))
        except Exception:
            asset_version = str(int(time.time()))
        response = make_response(render_template('backtest_tools.html', asset_version=asset_version))
        # Never let an old research page/template survive a redesign or API contract change.
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        return response

    @app.get('/backtest-tools/api/rankings')
    def backtest_tools_rankings():
        if not login_required():
            return jsonify(error='Login required'), 401
        window = request.args.get('window', '500').upper()
        if window not in WINDOWS:
            return jsonify(error='Invalid tick window'), 400
        value = store.snapshot(window)
        rows = value['rows']
        markets = sorted({(r['symbol'], r['market']) for r in rows})
        bots = sorted({(r['strategy'], r['bot']) for r in rows})
        for key in ('symbol', 'strategy', 'status'):
            selected = request.args.get(key)
            if selected:
                rows = [r for r in rows if r.get(key) == selected]
        sort = request.args.get('sort', 'score')
        if sort not in {'score', 'win_rate', 'ev', 'paper_trades', 'max_drawdown'}:
            return jsonify(error='Invalid sort'), 400
        rows = sorted(rows, key=lambda r: (r.get(sort) is None, (r.get(sort) or 0) * (1 if sort == 'max_drawdown' else -1)))
        return jsonify(health=health(store), updated=value['updated'],
            stale=time.time()-(value['updated'] or 0)>30, window=window, rows=rows,
            markets=markets, bots=bots, confirmation_policy=policy(store),
            confirmation_coverage=['under9', 'over0'])

    @app.get('/backtest-tools/api/decisions')
    def backtest_tools_decisions():
        if not login_required():
            return jsonify(error='Login required'), 401
        # Users see only their own order decisions, never another account's activity.
        return jsonify(decisions=store.decisions(str(session.get('user') or '')),
                       policy=policy(store))

    @app.get('/backtest-tools/api/details')
    def backtest_tools_details():
        if not login_required():
            return jsonify(error='Login required'), 401
        symbol, strategy = request.args.get('symbol', ''), request.args.get('strategy', '')
        windows = {}
        for window in WINDOWS:
            snap = store.snapshot(window)
            windows[window] = next((r for r in snap['rows'] if r['symbol'] == symbol and r['strategy'] == strategy), None)
        variants = (store.snapshot(policy(store)['window']))['rows']
        current = next((r for r in variants if r['symbol'] == symbol and r['strategy'] == strategy), {})
        confirmations = [assess(store, strategy if strategy in {'under9', 'over0'} else None, symbol, key)
                         for key in current.get('variants', {})]
        return jsonify(windows=windows, history=store.history(symbol, strategy), health=health(store),
                       confirmations=confirmations)

    @app.get('/admin/intelligence/status')
    def global_intelligence_status():
        if not login_required() or not is_admin():
            return jsonify(error='Admin access required'), 403
        session.setdefault('intelligence_csrf', secrets.token_urlsafe(32))
        return jsonify(health=health(store), csrf=session['intelligence_csrf'], policy=policy(store))

    @app.post('/admin/intelligence/<action>')
    def global_intelligence_control(action):
        if not login_required() or not is_admin():
            return jsonify(error='Admin access required'), 403
        csrf = session.get('intelligence_csrf', '')
        if not csrf or not secrets.compare_digest(request.headers.get('X-Intelligence-CSRF', ''), csrf):
            return jsonify(error='Refresh the admin page before making changes.'), 403
        data = request.get_json(silent=True) or {}
        try:
            if action == 'confirmation':
                enabled = data.get('enabled')
                window = str(data.get('window', '500')).upper()
                if not isinstance(enabled, bool) or window not in WINDOWS:
                    return jsonify(error='Choose an enabled state and valid research window.'), 400
                store.set('confirmation_policy', {**DEFAULT_POLICY, 'enabled': enabled, 'window': window})
            elif action == 'save':
                forwarded_proto = str(request.headers.get('X-Forwarded-Proto') or '').split(',', 1)[0].strip().lower()
                forwarded_ssl = str(request.headers.get('X-Forwarded-Ssl') or '').strip().lower()
                secure_request = request.is_secure or forwarded_proto == 'https' or forwarded_ssl == 'on'
                if not secure_request and urlsplit(request.host_url).hostname not in {'localhost', '127.0.0.1', '::1'}:
                    return jsonify(error='HTTPS is required to save the global PAT.'), 400
                Secrets(store).save(data.get('pat'))
                app_id = str(data.get('app_id') or '').strip()
                if app_id:
                    store.set('app_id', app_id)
                store.set('revision', secrets.token_hex(12))
            elif action in {'start', 'reconnect'}:
                if not Secrets(store).configured():
                    return jsonify(error='Save a global PAT first.'), 400
                if not (os.environ.get('KOOLKID_INTELLIGENCE_APP_ID') or store.get('app_id')):
                    return jsonify(error='Configure the global PAT App ID first.'), 400
                store.set('enabled', True)
                store.set('revision', secrets.token_hex(12))
                launch_daemon()
            elif action == 'stop':
                store.set('enabled', False)
            elif action == 'test':
                # Process a test on the SAME daemon/connection, never create a second socket in Flask.
                if not store.get('enabled', False):
                    return jsonify(error='Start Engine first; Test Connection checks its dedicated socket.'), 409
                store.set('test_requested', time.time())
                store.set('test_result', 'Pending authenticated connection check')
            else:
                return jsonify(error='Unknown command'), 404
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except Exception:
            return jsonify(error='Unable to save global secret. Check encryption-key configuration.'), 400
        return jsonify(ok=True, health=health(store))

    return store


def launch_daemon():
    if 'pytest' in sys.modules or os.environ.get('KOOLKID_INTELLIGENCE_AUTOSTART', '1') != '1':
        return
    # Child takes an OS lock before creating any sockets; Flask reloads/workers cannot duplicate feeds.
    kwargs = {'cwd': str(Path(__file__).resolve().parent.parent), 'stdin': subprocess.DEVNULL,
              'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    else:
        kwargs['start_new_session'] = True
    subprocess.Popen([sys.executable, '-m', 'deriv_backtest'], **kwargs)
