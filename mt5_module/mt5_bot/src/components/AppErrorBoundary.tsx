import { Component, type ErrorInfo, type ReactNode } from 'react';

type Props = { children: ReactNode };
type State = { error: Error | null; eventId: string | null };

export default class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null, eventId: null };

  static getDerivedStateFromError(error: Error): State {
    return { error, eventId: `ui-${Date.now().toString(36)}` };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    const payload = {
      at: new Date().toISOString(),
      message: error.message,
      stack: error.stack || '',
      componentStack: info.componentStack || '',
      href: window.location.href,
    };
    try {
      localStorage.setItem('koolkid_mt5_last_ui_error', JSON.stringify(payload));
    } catch {
      // Recovery UI must never fail because browser storage is unavailable.
    }
    console.error('KOOLKID MT5 UI recovered from a render crash', payload);
  }

  private retry = () => {
    this.setState({ error: null, eventId: null });
  };

  render() {
    const { error, eventId } = this.state;
    if (!error) return this.props.children;

    return (
      <main className="min-h-screen bg-[#04060b] p-4 text-slate-200 sm:p-8">
        <section className="mx-auto mt-[12vh] max-w-xl rounded-2xl border border-loss-500/20 bg-[#070b13] p-5 shadow-2xl shadow-black/30">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-loss-300">MT5 Hub recovered safely</p>
          <h1 className="mt-2 text-xl font-extrabold text-white">This page hit a UI error instead of going blank.</h1>
          <p className="mt-2 text-sm leading-relaxed text-slate-400">
            Your trading services keep running separately. You can retry the screen or reload the Hub.
          </p>
          <div className="mt-4 rounded-xl border border-white/[0.06] bg-white/[0.025] p-3">
            <p className="text-xs font-semibold text-slate-300">{error.message || 'Unknown UI error'}</p>
            {eventId && <p className="mono mt-1 text-[9px] text-slate-600">Error ID {eventId}</p>}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" className="btn-primary" onClick={this.retry}>Try Again</button>
            <button type="button" className="btn-ghost" onClick={() => window.location.reload()}>Reload Hub</button>
          </div>
        </section>
      </main>
    );
  }
}
