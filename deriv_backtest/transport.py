"""Dedicated read-only transport. The outbound allowlist cannot express a buy."""
import json
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import websocket


class ResearchError(Exception):
    pass


class Feed:
    ALLOWED = {'balance', 'active_symbols', 'contracts_for', 'ticks_history', 'ticks', 'proposal', 'ping', 'forget_all'}

    def __init__(self, token, app_id, account_id='', tick_queue=None):
        self._token = token
        self.app_id = app_id
        self.account_id = account_id
        self.currency = 'USD'
        self.events = tick_queue if tick_queue is not None else queue.Queue(maxsize=20000)
        self.socket = None
        self.pending = {}
        self.lock = threading.Lock()
        self.sequence = 0
        self.closed = threading.Event()
        self.reader = None
        self.last_send = 0.

    def rest(self, path, method='GET'):
        request = urllib.request.Request('https://api.derivws.com/trading/v1/options/' + path,
            data=b'{}' if method == 'POST' else None, method=method,
            headers={'Authorization': 'Bearer ' + self._token, 'Deriv-App-ID': self.app_id,
                     'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise ResearchError('Global PAT rejected (401). Check PAT and PAT App ID.') from None
            if exc.code == 403:
                raise ResearchError('Global PAT access denied (403). Check account access and scopes.') from None
            raise ResearchError('Deriv REST request failed: HTTP ' + str(exc.code)) from None
        except Exception:
            raise ResearchError('Deriv REST timeout or unavailable response.') from None

    def connect(self):
        if not self._token or not self.app_id:
            raise ResearchError('Configure the global PAT and KOOLKID_INTELLIGENCE_APP_ID.')
        payload = self.rest('accounts').get('data', [])
        if isinstance(payload, dict):
            payload = payload.get('accounts', list(payload.values()))
        accounts = [row for row in payload if isinstance(row, dict)]
        if self.account_id:
            accounts = [row for row in accounts if str(row.get('account_id') or row.get('id') or row.get('loginid')) == self.account_id]
        if not accounts:
            raise ResearchError('Global PAT has no matching Options account.')
        account = next((row for row in accounts if
                        str(row.get('account_type') or row.get('type') or '').lower() in {'demo', 'virtual'}
                        or row.get('is_virtual') in (True, 1, '1', 'true')), None)
        if account is None:
            raise ResearchError('Global PAT has no matching demo Options account. Real accounts are disabled.')
        account_id = str(account.get('account_id') or account.get('id') or account.get('loginid') or '')
        if not account_id:
            raise ResearchError('Deriv returned an unsupported account record.')
        self.currency = account.get('currency') or 'USD'
        payload = self.rest('accounts/' + urllib.parse.quote(account_id, safe='') + '/otp', 'POST')
        url = (payload.get('data') or {}).get('url', '')
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'wss' or parsed.hostname != 'api.derivws.com' or parsed.path != '/trading/v1/options/ws/demo':
            raise ResearchError('Deriv returned an unexpected WebSocket URL.')
        try:
            self.socket = websocket.create_connection(url, timeout=15, enable_multithread=True)
            self.socket.settimeout(5)
        except Exception:
            raise ResearchError('Global WebSocket connection failed.') from None
        self.reader = threading.Thread(target=self._receive, daemon=True, name='intelligence-socket')
        self.reader.start()
        result = self.request({'balance': 1})
        self.currency = (result.get('balance') or {}).get('currency') or self.currency

    def _receive(self):
        try:
            while not self.closed.is_set():
                try:
                    raw = self.socket.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not raw:
                    break
                payload = json.loads(raw)
                with self.lock:
                    future = self.pending.get(payload.get('req_id'))
                if future:
                    future.put_nowait(payload)
                if payload.get('tick'):
                    self.events.put_nowait((payload['tick'], time.time()))
        except Exception:
            pass
        finally:
            self.closed.set()

    def request(self, payload):
        commands = set(payload) & self.ALLOWED
        permitted_fields = {'subscribe', 'count', 'end', 'start', 'style', 'adjust_start_time',
                            'amount', 'basis', 'contract_type', 'barrier', 'duration', 'duration_unit',
                            'currency', 'underlying_symbol'}
        if len(commands) != 1 or set(payload) - self.ALLOWED - permitted_fields:
            raise ResearchError('Operation is not allowed on the research connection.')
        if self.closed.is_set() or not self.socket:
            raise ResearchError('Global WebSocket is disconnected.')
        # One caller, bounded request cadence; receiver never blocks on database or analysis.
        delay = .12 - (time.monotonic() - self.last_send)
        if delay > 0:
            self.closed.wait(delay)
        response = queue.Queue(maxsize=1)
        with self.lock:
            self.sequence += 1
            request_id = self.sequence
            self.pending[request_id] = response
        try:
            self.socket.send(json.dumps({**payload, 'req_id': request_id}))
            self.last_send = time.monotonic()
            result = response.get(timeout=12)
            if result.get('error'):
                # Never return arbitrary upstream text that could echo secrets or URLs.
                raise ResearchError('Deriv rejected research request: ' + next(iter(commands)))
            return result
        except ResearchError:
            raise
        except Exception:
            raise ResearchError('Research request timed out or connection failed.') from None
        finally:
            with self.lock:
                self.pending.pop(request_id, None)

    def close(self):
        self.closed.set()
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
        if self.reader and self.reader is not threading.current_thread():
            self.reader.join(timeout=6)
