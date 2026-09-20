import { FormEvent, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { ArrowDown, ArrowLeft, ArrowRight, Bot, BrainCircuit, ChartNoAxesCombined, Copy, Eye, EyeOff, Landmark, ShieldCheck } from 'lucide-react';
import { hubAuthService } from '../services/hubAuthService';
import type { HubAuthResponse, HubTrialInfo } from '../services/hubAuthService';
import { hostHomeUrl } from '../config/runtime';
import ContactSupport from './ContactSupport';
import TrialNotice from './TrialNotice';
import AdminConsole from '../pages/AdminConsole';

type EntryView = 'cover' | 'login' | 'signup';
const logo = '/mt5-bot/favicon.svg';
const tools = [
  [Landmark, 'Connected accounts', 'Bring up to ten MT5 accounts into your own secure Hub workspace.'],
  [ChartNoAxesCombined, 'Trade and monitor', 'Work from positions, history, charts, account metrics, and manual execution controls.'],
  [Copy, 'Copy Trader', 'Link a master account to selected slaves and keep the relationship running server-side.'],
  [Bot, 'EA Bot Library', 'Assign verified EX5 bots to MT5 terminals and follow their status from one place.'],
  [BrainCircuit, 'AI Intelligence', 'Review account insight, Human Apostle scanning, and LIVE-risk confirmation safeguards.'],
  [ShieldCheck, 'Risk control', 'Set account guardrails, review exposure, and keep operational controls close.'],
] as const;

function Brand() { return <a className="mt5-brand" href="/mt5-bot"><img src={logo} alt="" /><span>KOOLKID <b>MT5</b></span></a>; }

function Cover({ open }: { open: (view: EntryView) => void }) {
  return <main className="mt5-public">
    <header className="mt5-public-head"><Brand /><nav><a href="#tools">Capabilities</a><a href="#desk">Workspace</a><button onClick={() => window.location.assign(hostHomeUrl || '/')}>KOOLKID AI BOT</button><button onClick={() => open('login')}>Log in</button><button className="mt5-nav-cta" onClick={() => open('signup')}>Create account</button></nav></header>
    <section className="mt5-hero" aria-labelledby="mt5-title"><div className="mt5-grid" aria-hidden="true" /><div className="mt5-hero-copy"><p className="mt5-kicker">KOOLKID MT5 HUB</p><h1 id="mt5-title">YOUR MT5<br /><em>TRADING DESK.</em></h1><p className="mt5-hero-line">Your accounts. Your terminals. Your control.</p><p className="mt5-muted">A server-backed MetaTrader 5 workspace for account management, manual trading, copy trading, bots, and live operational oversight.</p><div className="mt5-actions"><button className="mt5-primary" onClick={() => open('login')}>Enter MT5 Hub <ArrowRight size={17} /></button><button className="mt5-secondary" onClick={() => open('signup')}>Create account</button></div><p className="mt5-tags">MULTI-ACCOUNT <i /> MANUAL &amp; AUTOMATED <i /> SERVER-BACKED</p></div><div className="mt5-preview" aria-label="MT5 Hub workspace preview"><div className="mt5-preview-bar"><span /><span /><span /><b>MT5 HUB</b></div><div className="mt5-preview-body"><aside><img src={logo} alt="" /><i /><i /><i /><i /></aside><article><small>ACCOUNT EQUITY</small><strong>$24,680.00</strong><em>+1.84%</em><div className="mt5-chart">{Array.from({ length: 8 }).map((_, index) => <span key={index} />)}</div><footer><b>Copy Trader</b><span>Active</span><b>AI Intelligence</b><span>Monitoring</span></footer></article></div></div><a className="mt5-explore" href="#tools"><ArrowDown size={15} /> Explore the hub</a></section>
    <section className="mt5-tools" id="tools"><div className="mt5-section-head"><p>01 / THE HUB</p><div><h2>A desk that stays with you.</h2><span>Operate your MT5 setup without tying it to a browser tab.</span></div></div><div className="mt5-tool-grid">{tools.map(([Icon, title, copy], index) => <article key={title}><small>0{index + 1}</small><Icon size={20} /><h3>{title}</h3><p>{copy}</p></article>)}</div></section>
    <section className="mt5-desk" id="desk"><div><p className="mt5-kicker">YOUR WORKSPACE</p><h2>One place for every move.</h2></div><ol><li><b>01</b><div><h3>Connect</h3><p>Add your MT5 accounts to your own secure Hub workspace.</p></div></li><li><b>02</b><div><h3>Configure</h3><p>Choose account roles, copy relationships, risk settings, and EA assignments.</p></div></li><li><b>03</b><div><h3>Monitor</h3><p>Keep working relationships and intelligence scans running server-side.</p></div></li></ol></section>
    <section className="mt5-final"><p className="mt5-kicker">KOOLKID MT5 HUB</p><h2>Open your trading desk.</h2><p>Build your MT5 workspace around the way you trade.</p><div className="mt5-actions"><button className="mt5-primary" onClick={() => open('login')}>Log in <ArrowRight size={17} /></button><button className="mt5-secondary" onClick={() => open('signup')}>Create account</button></div></section>
    <footer className="mt5-footer"><Brand /><p>Trading involves risk. Use settings and automation responsibly.</p><a href="/">KOOLKID PRO</a></footer>
  </main>;
}

function Auth({ mode, open, complete }: { mode: Exclude<EntryView, 'cover'>; open: (view: EntryView) => void; complete: (result: HubAuthResponse) => void }) {
  const [username, setUsername] = useState(''); const [password, setPassword] = useState(''); const [show, setShow] = useState(false); const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const login = mode === 'login';
  const submit = async (event: FormEvent) => { event.preventDefault(); setBusy(true); setError(''); try { const result = login ? await hubAuthService.login(username, password) : await hubAuthService.signup(username, password); complete(result); } catch (err) { setError(err instanceof Error ? err.message : 'MT5 Hub sign-in failed.'); } finally { setBusy(false); } };
  return <main className="mt5-public mt5-auth"><header className="mt5-public-head"><Brand /><nav><button onClick={() => open('cover')}><ArrowLeft size={15} /> Back to home</button><button onClick={() => window.location.assign(hostHomeUrl || '/')}>KOOLKID AI BOT</button><button className="mt5-nav-cta" onClick={() => open(login ? 'signup' : 'login')}>{login ? 'Create account' : 'Log in'}</button></nav></header><section><div className="mt5-grid" aria-hidden="true" /><div className="mt5-auth-mark"><img src={logo} alt="" /> MT5</div><form onSubmit={submit}><p className="mt5-kicker">YOUR MT5 WORKSPACE</p><h1>{login ? 'Welcome back.' : 'Make it yours.'}</h1><p className="mt5-muted">{login ? 'Your next move starts here.' : 'Create your MT5 Hub account. No license key required.'}</p><label>Username<input required minLength={3} maxLength={80} value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Your MT5 Hub username" autoComplete="username" autoCapitalize="none" /></label><label>Password<div className="mt5-password"><input required minLength={8} type={show ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} placeholder={login ? 'Your password' : 'Choose a password'} autoComplete={login ? 'current-password' : 'new-password'} /><button type="button" onClick={() => setShow(!show)} title={show ? 'Hide password' : 'Show password'}>{show ? <EyeOff size={17} /> : <Eye size={17} />}</button></div>{!login && <small>Use at least 8 characters.</small>}</label>{error && <p className="mt5-auth-error">{error}</p>}<button className="mt5-primary mt5-auth-submit" disabled={busy}>{busy ? 'Please wait...' : login ? 'Log in' : 'Create account'} <ArrowRight size={17} /></button><p className="mt5-switch">{login ? 'New to KOOLKID MT5?' : 'Already have an account?'} <button type="button" onClick={() => open(login ? 'signup' : 'login')}>{login ? 'Create an account' : 'Log in'}</button></p></form></section><footer className="mt5-footer"><Brand /><p>Your account. Your approach. Your MT5 workspace.</p><button onClick={() => open('cover')}>Home</button></footer></main>;
}

export default function HubAuthGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [view, setView] = useState<EntryView>('cover');
  const [trial, setTrial] = useState<HubTrialInfo | null>(null);
  const [identity, setIdentity] = useState<HubAuthResponse | null>(null);
  const [trialNoticeOpen, setTrialNoticeOpen] = useState(false);

  useEffect(() => {
    if (!sessionStorage.getItem('koolkid_mt5_hub_token')) {
      setReady(true);
      return;
    }
    hubAuthService.me()
      .then((result) => {
        setTrial(result.trial || null);
        setIdentity(result);
        setSignedIn(true);
      })
      .catch(() => hubAuthService.logout())
      .finally(() => setReady(true));
  }, []);

  const complete = (result: HubAuthResponse) => {
    setTrial(result.trial || null);
    setIdentity(result);
    setSignedIn(true);
    setTrialNoticeOpen(result.access_tier !== 'lifetime');
  };

  useEffect(() => {
    if (!signedIn) return;
    const ping = () => { void hubAuthService.presence().catch(() => {}); };
    ping();
    const timer = window.setInterval(ping, 45000);
    return () => window.clearInterval(timer);
  }, [signedIn]);

  if (!ready) return <><div className="min-h-screen bg-[#04060b]" /><ContactSupport trial={trial} /></>;
  if (signedIn && identity?.role === 'admin') return <AdminConsole username={identity.username} />;
  if (signedIn) {
    const lifetime = identity?.access_tier === 'lifetime';
    return <>{children}{!lifetime && <ContactSupport trial={trial} />}{!lifetime && <TrialNotice open={trialNoticeOpen} onClose={() => setTrialNoticeOpen(false)} trial={trial} />}</>;
  }
  return <>{view === 'cover' ? <Cover open={setView} /> : <Auth mode={view} open={setView} complete={complete} />}<ContactSupport trial={trial} /></>;
}
