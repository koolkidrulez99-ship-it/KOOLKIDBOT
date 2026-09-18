import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Check, CheckCircle2, Copy, KeyRound, Landmark, Plus, Power, Trash2, Wallet } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { fmtSigned, fmtUSD, profitTone } from '../lib/format';
import { Badge, EmptyState, PageHeader, Panel, Progress, Spinner, StatusDot } from '../components/ui';
import Modal from '../components/Modal';
import ConfirmModal from '../components/ConfirmModal';
import { accountAction, addAccount, removeAccount, testAccount } from '../lib/actions';
import { isSimulation } from '../config/runtime';
import { mt5AccountService } from '../services/mt5AccountService';
import type { Mt5Account } from '../types';

const BROKER_PRESETS = [
  { name: 'Deriv', servers: ['Deriv-Demo', 'DerivSVG-Server'] },
  { name: 'HFM', servers: ['HFMarketsGlobal-Demo', 'HFMarketsGlobal-Demo3', 'HFMarketsGlobal-Demo4', 'HFMarketsGlobal-Live1', 'HFMarketsGlobal-Live3', 'HFMarketsGlobal-Live4', 'HFMarketsGlobal-Live5', 'HFMarketsGlobal-Live7', 'HFMarketsGlobal-Live8', 'HFMarketsGlobal-Live9', 'HFMarketsGlobal-Live10', 'HFMarketsGlobal-Live11', 'HFMarketsGlobal-Live12', 'HFMarketsGlobal-Live13', 'HFMarketsGlobal-Live14', 'HFMarketsGlobal-Live15', 'HFMarketsGlobal-Live16', 'HFMarketsGlobal-Live17', 'HFMarketsGlobal-Live18', 'HFMarketsGlobal-Live19', 'HFMarketsGlobal-Live20'] },
  { name: 'XM Global', servers: ['XMGlobal-MT5', 'XMGlobal-MT5 2', 'XMGlobal-MT5 4', 'XMGlobal-MT5 5', 'XMGlobal-MT5 6', 'XMGlobal-MT5 7', 'XMGlobal-MT5 8', 'XMGlobal-MT5 9', 'XMGlobal-MT5 10', 'XMGlobal-MT5 11', 'XMGlobal-MT5 12', 'XMGlobal-MT5 13', 'XMGlobal-MT5 14', 'XMGlobal-MT5 15', 'XMGlobal-MT5 16', 'XMGlobal-MT5 17', 'XMGlobal-MT5 18', 'XMGlobal-MT5 19', 'XMGlobal-MT5 20'] },
  { name: 'Qberx Capital', servers: ['QberxCapital-Server'] },
  { name: 'Exness', servers: [] },
  { name: 'IC Markets', servers: [] },
  { name: 'Pepperstone', servers: [] },
  { name: 'FXTM', servers: [] },
  { name: 'FBS', servers: [] },
  { name: 'Eightcap', servers: [] },
  { name: 'Admiral Markets', servers: [] },
  { name: 'FTMO', servers: [] },
  { name: 'Other / Custom Broker', servers: [] },
] as const;

const BROKERS = BROKER_PRESETS.map((broker) => broker.name);

export default function AccountsPage() {
  const { accounts, positions, liveProfit, pushToast, refresh, setActive, active } = useHub();
  const [addOpen, setAddOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<Mt5Account | null>(null);
  const [reconnectTarget, setReconnectTarget] = useState<Mt5Account | null>(null);
  const [budgetTarget, setBudgetTarget] = useState<Mt5Account | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const accFloating = (login: number) => positions.filter((p) => p.account_login === login).reduce((s, p) => s + liveProfit(p), 0);

  const toggleStatus = async (a: Mt5Account) => {
    if (!isSimulation && a.status !== 'connected') {
      setReconnectTarget(a);
      return;
    }
    setBusyId(a.id);
    try {
      const next = (await accountAction(a.id, a.status === 'connected' ? 'disconnect' : 'connect')) as Mt5Account;
      pushToast(next.status === 'connected' ? 'success' : 'info', `${a.nickname} ${next.status}`, `Login #${a.login} ${next.status === 'connected' ? (isSimulation ? 'enabled in simulation.' : 'connected to the MT5 bridge.') : 'disconnected.'}`);
      await refresh(true);
    } catch (e) {
      pushToast('error', 'Connection toggle failed', e instanceof Error ? e.message : undefined);
    } finally {
      setBusyId(null);
    }
  };

  const copyLogin = (login: number) => {
    navigator.clipboard?.writeText(String(login)).catch(() => {});
    pushToast('info', 'Login copied', `#${login} copied to clipboard.`);
  };

  return (
    <div>
      <PageHeader
        title="MT5 Accounts"
        sub={isSimulation ? 'Simulation account profiles · real broker authentication is not active yet' : 'Link, monitor and switch MetaTrader 5 account connections'}
        actions={
          <button className="btn-primary" onClick={() => setAddOpen(true)}>
            <Plus size={15} /> Add MT5 Account
          </button>
        }
      />

      {accounts.length === 0 ? (
        <Panel>
          <EmptyState
            icon={Wallet}
            title="No MT5 accounts linked"
            sub={isSimulation ? 'Add your first simulated MT5 account profile.' : 'Connect your first MetaTrader 5 account through the terminal bridge.'}
            action={
              <button className="btn-primary" onClick={() => setAddOpen(true)}>
                <Plus size={15} /> Connect first account
              </button>
            }
          />
        </Panel>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-4">
          {accounts.map((a) => {
            const float = accFloating(a.login);
            const equity = Number(a.balance) + float;
            const margin = Number(a.margin);
            const marginLevel = margin > 0 ? (equity / margin) * 100 : null;
            const isActive = active === a.login;
            const connected = a.status === 'connected';
            return (
              <Panel key={a.id} hover className={`p-5 ${isActive ? 'ring-1 ring-brand-500/50 shadow-glow-brand' : ''}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-500/12 border border-brand-500/25 text-brand-300">
                      <Landmark size={19} />
                    </span>
                    <div className="min-w-0">
                      <p className="text-[15px] font-bold text-white truncate">{a.nickname}</p>
                      <p className="text-[11px] text-slate-500 truncate">{a.broker}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Badge tone={a.account_type === 'live' ? 'loss' : 'warn'}>{a.account_type}</Badge>
                    {(a.read_only || a.access_mode === 'investor') && <Badge tone="slate">INVESTOR</Badge>}
                    {isActive && <Badge tone={connected ? 'brand' : 'slate'}>{connected ? 'Active' : 'Selected'}</Badge>}
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-[12px]">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Login</span>
                    <button onClick={() => copyLogin(a.login)} className="mono text-slate-300 inline-flex items-center gap-1 hover:text-brand-300 transition-colors cursor-pointer">
                      #{a.login} <Copy size={11} />
                    </button>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Server</span>
                    <span className="text-slate-300 truncate max-w-[130px]" title={a.server}>{a.server}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Leverage</span>
                    <span className="mono text-slate-300">1:{a.leverage}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Currency</span>
                    <span className="mono text-slate-300">{a.currency}</span>
                  </div>
                </div>

                <div className="mt-4 rounded-xl bg-black/25 border border-white/[0.06] p-3.5 grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-[10px] uppercase tracking-widest text-slate-600 font-semibold">Balance</p>
                    <p className="mono text-[15px] font-bold text-white mt-0.5">{fmtUSD(Number(a.balance))}{!connected && !isSimulation ? <span className="ml-1 text-[9px] text-slate-600">CACHED</span> : null}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-widest text-slate-600 font-semibold">Equity</p>
                    <p className="mono text-[15px] font-bold text-white mt-0.5">{fmtUSD(equity)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-widest text-slate-600 font-semibold">Margin</p>
                    <p className="mono text-[13px] text-slate-300 mt-0.5">{fmtUSD(margin)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-widest text-slate-600 font-semibold">Free margin</p>
                    <p className="mono text-[13px] text-slate-300 mt-0.5">{fmtUSD(equity - margin)}</p>
                  </div>
                </div>

                {a.budget_enabled && a.budget != null && (
                  <div className="mt-3 rounded-xl border border-brand-500/20 bg-brand-500/[0.06] px-3 py-2.5 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[9px] uppercase tracking-widest font-bold text-brand-300">Trading Budget Active</p>
                      <p className="text-[10px] text-slate-500">KOOLKID sizes and blocks routed entries against this allocation.</p>
                    </div>
                    <p className="mono text-sm font-extrabold text-white">{fmtUSD(Number(a.budget))}</p>
                  </div>
                )}

                <div className="mt-3.5 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[10px] uppercase tracking-widest text-slate-600 font-semibold mb-1">
                      Margin level &middot; {marginLevel ? `${marginLevel.toFixed(0)}%` : '\u221e'}
                    </p>
                    <div className="w-36">
                      <Progress value={marginLevel ? Math.min(100, marginLevel / 20) : 0} tone={!marginLevel || marginLevel > 400 ? 'gain' : marginLevel > 200 ? 'warn' : 'loss'} />
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-[10px] uppercase tracking-widest text-slate-600 font-semibold">Floating P/L</p>
                    <p className={`mono text-[14px] font-bold mt-0.5 ${profitTone(float)}`}>{fmtSigned(float)}</p>
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t border-white/[0.06] flex items-center gap-2">
                  <button
                    className={isActive ? 'btn-ghost flex-1 !cursor-default opacity-70' : 'btn-ghost flex-1'}
                    disabled={isActive}
                    onClick={() => setActive(a.login)}
                  >
                    {isActive ? <><Check size={14} className="text-gain-400" /> Selected</> : 'Set Active'}
                  </button>
                  <button className="btn-ghost !px-2 !py-1.5 !text-[10px] shrink-0" onClick={() => setBudgetTarget(a)} disabled={isSimulation} title="Set trading budget">
                    <Wallet size={12} className={a.budget_enabled ? 'text-brand-300' : 'text-slate-500'} /> Budget
                  </button>
                  <button className="btn-ghost" onClick={() => toggleStatus(a)} disabled={busyId === a.id || a.status === 'connecting'}>
                    {busyId === a.id ? <Spinner size={13} /> : <Power size={14} className={connected ? 'text-gain-400' : 'text-slate-500'} />}
                    {a.status === 'connecting' ? 'Connecting' : connected ? 'Disconnect' : 'Connect'}
                  </button>
                  <button className="btn-icon hover:!text-loss-400" title="Remove account" onClick={() => setRemoveTarget(a)}>
                    <Trash2 size={15} />
                  </button>
                </div>

                <div className="mt-3 flex items-center gap-2 text-[11px] text-slate-500">
                  <StatusDot status={a.status} />
                  {connected ? (isSimulation ? `Simulation active · ${a.server}` : `Account session live · ${a.server}`) : a.status === 'connecting' ? 'Connecting to account worker…' : (isSimulation ? 'Simulation profile disabled' : 'Offline · cached account details')}
                </div>
              </Panel>
            );
          })}
        </div>
      )}

      <AddAccountModal open={addOpen} onClose={() => setAddOpen(false)} />
      <ReconnectAccountModal account={reconnectTarget} onClose={() => setReconnectTarget(null)} />
      <BudgetModal account={budgetTarget} onClose={() => setBudgetTarget(null)} />

      <ConfirmModal
        open={removeTarget !== null}
        onClose={() => setRemoveTarget(null)}
        title={`Remove ${removeTarget?.nickname || 'account'}?`}
        tone="danger"
        confirmLabel="Remove Account"
        message={
          <>Login <span className="mono font-bold text-white">#{removeTarget?.login}</span> will be removed from the Hub. Saved credentials in the MetaTrader terminal are not changed. Any assigned bots are stopped.</>
        }
        onConfirm={async () => {
          if (!removeTarget) return;
          try {
            await removeAccount(removeTarget.id);
            pushToast('info', 'Account removed', `#${removeTarget.login} unlinked from the hub.`);
            await refresh(true);
          } catch (e) {
            pushToast('error', 'Remove failed', e instanceof Error ? e.message : undefined);
          }
        }}
      />
    </div>
  );
}

function BudgetModal({ account, onClose }: { account: Mt5Account | null; onClose: () => void }) {
  const { pushToast, refresh } = useHub();
  const [amount, setAmount] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!account) return;
    setAmount(account.budget_enabled && account.budget != null ? String(account.budget) : '');
    setError('');
  }, [account?.id, account?.budget, account?.budget_enabled]);

  const save = async () => {
    if (!account) return;
    const value = Number(amount);
    if (!Number.isFinite(value) || value <= 0) { setError('Enter a budget greater than zero.'); return; }
    if (Number(account.balance) > 0 && value > Number(account.balance)) {
      setError(`Budget cannot exceed the current MT5 balance of ${fmtUSD(Number(account.balance))}.`);
      return;
    }
    setBusy(true);
    setError('');
    try {
      await mt5AccountService.setBudget(account.id, value);
      pushToast('success', 'Trading budget set', `${account.nickname} will use ${fmtUSD(value)} as its KOOLKID allocation cap.`);
      await refresh(true);
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not set the trading budget.');
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (!account) return;
    setBusy(true);
    setError('');
    try {
      await mt5AccountService.resetBudget(account.id);
      pushToast('info', 'Budget reset', `${account.nickname} is back to its actual MT5 balance for KOOLKID-routed trading.`);
      await refresh(true);
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not reset the trading budget.');
    } finally {
      setBusy(false);
    }
  };

  return <Modal open={Boolean(account)} onClose={() => !busy && onClose()} title="Account Trading Budget" sub={account ? `${account.nickname} · #${account.login}` : ''}>
    <div className="space-y-4">
      <div className="rounded-xl border border-brand-500/20 bg-brand-500/[0.06] px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-slate-500">Actual MT5 balance</span>
          <span className="mono font-bold text-white">{fmtUSD(Number(account?.balance || 0))}</span>
        </div>
        <p className="mt-2 text-[10px] leading-relaxed text-slate-500">A budget is a hard KOOLKID allocation cap. Native AI, manual orders and copy-trader orders size/check against it instead of using the full account. It does not move or withdraw money.</p>
      </div>
      <div>
        <label className="label">Budget amount</label>
        <div className="relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-slate-500">$</span>
          <input autoFocus className="input mono !pl-7" type="number" min="0.01" step="0.01" max={account?.balance || undefined}
            value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="100.00" />
        </div>
        <p className="mt-1 text-[10px] text-slate-600">Example: a $100 budget on a $1,000 account makes KOOLKID treat $100 as the maximum allocated capital.</p>
      </div>
      {error && <p className="rounded-lg border border-loss-500/30 bg-loss-500/10 px-3 py-2 text-xs text-loss-300">{error}</p>}
      <div className="flex flex-wrap justify-end gap-2">
        {account?.budget_enabled && <button className="btn-ghost" onClick={reset} disabled={busy}>Reset to Account Balance</button>}
        <button className="btn-ghost" onClick={onClose} disabled={busy}>Cancel</button>
        <button className="btn-primary" onClick={save} disabled={busy}>{busy ? <Spinner size={14} /> : <Wallet size={14} />} Set Budget</button>
      </div>
    </div>
  </Modal>;
}

function ReconnectAccountModal({ account, onClose }: { account: Mt5Account | null; onClose: () => void }) {
  const { pushToast, refresh } = useHub();
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const connect = async () => {
    if (!account || !password) { setError('Enter the MT5 password for this account.'); return; }
    setBusy(true); setError('');
    try {
      const next = await accountAction(account.id, 'connect', { password }) as Mt5Account;
      setPassword('');
      pushToast('success', `${account.nickname} connected`, `Login #${next.login} connected to ${next.server}.`);
      onClose();
      void refresh(true);
    } catch (reason) {
      setError(reason instanceof DOMException && reason.name === 'AbortError'
        ? 'MT5 connection timed out. The account terminal did not become ready.'
        : reason instanceof Error ? reason.message : 'MT5 connection failed.');
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (account && busy) {
      try { await accountAction(account.id, 'cancel_connect'); } catch { /* the backend timeout still performs cleanup */ }
    }
    setBusy(false);
    onClose();
  };

  return <Modal open={Boolean(account)} onClose={cancel} title={`Connect ${account?.nickname || 'MT5 account'}`} sub={`Authenticate login #${account?.login || ''} on ${account?.server || 'the saved server'}.`}>
    <div className="space-y-4">
      <div><label className="label">{account?.access_mode === 'investor' ? 'MT5 Investor Password' : 'MT5 Trading Password'}</label><div className="relative"><KeyRound size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-600" /><input autoFocus type="password" className="input !pl-9" placeholder={account?.access_mode === 'investor' ? 'Enter investor/read-only password' : 'Enter trading password'} autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') connect(); }} /></div></div>
      <p className="text-[11px] text-slate-500">{account?.access_mode === 'investor' ? 'This account reconnects in read-only investor mode. KOOLKID will not submit or modify orders on it.' : 'The password is used for this connection only and is not stored by KOOLKID.'}</p>
      {error && <p className="rounded-lg border border-loss-500/30 bg-loss-500/10 px-3 py-2 text-xs text-loss-300">{error}</p>}
      <div className="flex justify-end gap-2"><button className="btn-ghost" onClick={cancel}>Cancel</button><button className="btn-primary" onClick={connect} disabled={busy}>{busy ? <Spinner size={14} /> : <Power size={14} />} {busy ? 'Connecting…' : 'Connect'}</button></div>
    </div>
  </Modal>;
}

function AddAccountModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { pushToast, refresh } = useHub();
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [tested, setTested] = useState(false);
  const [testing, setTesting] = useState(false);
  const [customServer, setCustomServer] = useState(false);
  const [form, setForm] = useState({
    login: '',
    password: '',
    nickname: '',
    broker: 'Deriv',
    server: 'Deriv-Demo',
    access_mode: 'trading' as 'trading' | 'investor',
    leverage: '500',
    account_type: 'demo' as 'demo' | 'live',
    balance: '10000',
  });

  const set = (k: string, v: string) => { setTested(false); setForm((f) => ({ ...f, [k]: v })); };
  const serverPresets: readonly string[] = BROKER_PRESETS.find((broker) => broker.name === form.broker)?.servers || [];
  const setBroker = (broker: string) => {
    const nextServers: readonly string[] = BROKER_PRESETS.find((item) => item.name === broker)?.servers || [];
    setTested(false);
    setCustomServer(nextServers.length === 0);
    setForm((current) => ({ ...current, broker, server: nextServers[0] || '' }));
  };
  const setServerChoice = (value: string) => {
    setTested(false);
    if (value === '__custom__') {
      setCustomServer(true);
      setForm((current) => ({ ...current, server: '' }));
      return;
    }
    setCustomServer(false);
    setForm((current) => ({ ...current, server: value }));
  };

  const cancel = async () => {
    if (!isSimulation && (busy || testing) && /^[0-9]{4,12}$/.test(form.login)) {
      try { await mt5AccountService.cancelConnect(Number(form.login)); } catch { /* the server-side deadline still cleans the worker */ }
    }
    setBusy(false);
    setTesting(false);
    onClose();
  };

  const validate = () => {
    const errs: string[] = [];
    if (!/^[0-9]{4,12}$/.test(form.login)) errs.push('MT5 login must be 4–12 digits.');
    if (!form.nickname.trim()) errs.push('Nickname is required.');
    if (!form.server.trim()) errs.push('Broker server is required.');
    if (!isSimulation && !form.password) errs.push('MT5 password is required when bridge mode is enabled.');
    if (isSimulation && Number(form.balance) < 100) errs.push('Starting balance must be at least $100.');
    setErrors(errs);
    return errs.length === 0;
  };

  const test = async () => {
    if (!validate()) return;
    setTesting(true);
    setTested(false);
    try {
      const result = await testAccount({ login: form.login, broker: form.broker, server: form.server, access_mode: form.access_mode, ...(isSimulation ? {} : { password: form.password }) });
      setTested(Boolean(result.ok));
      pushToast('success', isSimulation ? 'Simulation check passed' : 'Connection test passed', result.message);
    } catch (err) {
      setErrors([err instanceof Error ? err.message : 'Connection test failed.']);
    } finally {
      setTesting(false);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setBusy(true);
    try {
      await addAccount({
        login: form.login,
        nickname: form.nickname,
        broker: form.broker,
        server: form.server,
        access_mode: form.access_mode,
        leverage: Number(form.leverage),
        account_type: form.account_type,
        balance: Number(form.balance),
        ...(isSimulation ? {} : { password: form.password }),
      });
      pushToast('success', isSimulation ? 'Simulation account added' : 'MT5 account connected', `${form.nickname} (#${form.login}) is ready.`);
      await refresh(true);
      setForm({ login: '', password: '', nickname: '', broker: 'Deriv', server: 'Deriv-Demo', access_mode: 'trading', leverage: '500', account_type: 'demo', balance: '10000' });
      setCustomServer(false);
      setTested(false);
      onClose();
    } catch (err) {
      setErrors([err instanceof Error ? err.message : 'Connection failed.']);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={cancel} title="Add MT5 Account" sub={isSimulation ? 'Create a simulation account profile. No broker authentication occurs.' : 'Connect through the configured authenticated MT5 bridge.'} wide>
      <form onSubmit={submit} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="label">MT5 Login</label>
          <input className="input mono" placeholder="51284763" value={form.login} onChange={(e) => set('login', e.target.value.replace(/[^0-9]/g, ''))} inputMode="numeric" />
        </div>
        <div>
          <label className="label">{form.access_mode === 'investor' ? 'MT5 Investor Password' : 'MT5 Trading Password'}</label>
          <div className="relative">
            <KeyRound size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-600" />
            <input type="password" className="input !pl-9" placeholder={form.access_mode === 'investor' ? 'Enter investor/read-only password' : 'Enter trading password'} autoComplete="current-password" value={form.password} onChange={(e) => set('password', e.target.value)} />
          </div>
          <p className="mt-1 text-[10px] text-slate-600">{isSimulation ? 'Simulation mode: this password stays only in this form and is never stored or transmitted.' : form.access_mode === 'investor' ? 'Investor sessions are read-only in KOOLKID: balances, charts, positions and history work, but order actions are blocked.' : 'The password is sent only to the configured backend bridge over your deployment transport; this frontend never persists it.'}</p>
        </div>
        {!isSimulation && (
          <div className="sm:col-span-2">
            <label className="label">Login access</label>
            <div className="grid grid-cols-2 gap-2">
              <button type="button" className={form.access_mode === 'trading' ? 'btn-primary justify-center' : 'btn-ghost justify-center'} onClick={() => set('access_mode', 'trading')}>Trading Password</button>
              <button type="button" className={form.access_mode === 'investor' ? 'btn-primary justify-center' : 'btn-ghost justify-center'} onClick={() => set('access_mode', 'investor')}>Investor / Read-only</button>
            </div>
            <p className="mt-1 text-[10px] text-slate-600">Investor accounts can be monitored and used as a Copy Trader master, but cannot be a slave or receive KOOLKID orders.</p>
          </div>
        )}
        <div>
          <label className="label">Nickname</label>
          <input className="input" placeholder="My Deriv MT5" value={form.nickname} onChange={(e) => set('nickname', e.target.value)} />
        </div>
        <div>
          <label className="label">Broker</label>
          <select className="input" value={form.broker} onChange={(e) => setBroker(e.target.value)}>
            {BROKERS.map((b) => (
              <option key={b}>{b}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Server</label>
          {serverPresets.length > 0 ? (
            <>
              <select className="input" value={customServer ? '__custom__' : form.server} onChange={(e) => setServerChoice(e.target.value)}>
                {serverPresets.map((server) => <option key={server} value={server}>{server}</option>)}
                <option value="__custom__">Other / Exact server…</option>
              </select>
              {customServer && (
                <input
                  className="input mt-2"
                  placeholder="Enter the exact MT5 server or host:port"
                  value={form.server}
                  onChange={(e) => set('server', e.target.value)}
                  autoComplete="off"
                />
              )}
              <p className="mt-1 text-[10px] text-slate-600">Choose the exact {form.broker} MT5 server assigned to this account.</p>
            </>
          ) : (
            <>
              <input
                className="input"
                placeholder="Enter the exact MT5 server from your broker"
                value={form.server}
                onChange={(e) => set('server', e.target.value)}
                autoComplete="off"
              />
              <p className="mt-1 text-[10px] text-slate-600">Paste or type the exact MT5 server shown by your broker.</p>
            </>
          )}
        </div>
        {isSimulation ? (<>
          <div>
            <label className="label">Leverage</label>
            <select className="input mono" value={form.leverage} onChange={(e) => set('leverage', e.target.value)}>
              {['100', '200', '500', '1000', '2000', '3000'].map((l) => (
                <option key={l} value={l}>1:{l}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Account type</label>
            <div className="flex gap-1.5">
              {(['demo', 'live'] as const).map((t) => (
                <button type="button" key={t} onClick={() => set('account_type', t)} className={`flex-1 rounded-lg px-3 py-2 text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer ${form.account_type === t ? t === 'live' ? 'bg-loss-500/20 text-loss-300 border border-loss-500/40' : 'bg-warn-400/15 text-warn-400 border border-warn-400/35' : 'bg-white/[0.04] text-slate-500 border border-white/10 hover:text-slate-300'}`}>
                  {t}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="label">Starting balance (USD)</label>
            <input className="input mono" value={form.balance} onChange={(e) => set('balance', e.target.value)} inputMode="decimal" />
          </div>
        </>) : (
          <div className="sm:col-span-2 rounded-xl border border-brand-500/20 bg-brand-500/[0.06] px-4 py-3 text-xs text-slate-400">
            Balance, equity, leverage and DEMO/LIVE account type are read directly from MetaTrader 5 after authentication; they are not entered manually. LIVE order execution remains safety-locked by default in the local bridge.
          </div>
        )}

        {errors.length > 0 && (
          <div className="sm:col-span-2 rounded-xl border border-loss-500/30 bg-loss-500/10 px-4 py-3 space-y-1">
            {errors.map((er) => (
              <p key={er} className="text-xs text-loss-300">{er}</p>
            ))}
          </div>
        )}

        <div className="sm:col-span-2 flex flex-wrap justify-end gap-2.5 mt-1">
          <button type="button" className="btn-ghost" onClick={cancel}>Cancel</button>
          <button type="button" className="btn-ghost" onClick={test} disabled={busy || testing}>
            {testing ? <Spinner size={14} /> : tested ? <CheckCircle2 size={15} className="text-gain-400" /> : <Power size={15} />}
            {testing ? 'Testing…' : tested ? 'Test Passed' : 'Test Connection'}
          </button>
          <button type="submit" className="btn-primary" disabled={busy || testing}>
            {busy ? <Spinner size={14} /> : <Plus size={15} />}
            {busy ? (isSimulation ? 'Adding…' : 'Connecting…') : (isSimulation ? 'Add Simulation Account' : 'Connect Account')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
