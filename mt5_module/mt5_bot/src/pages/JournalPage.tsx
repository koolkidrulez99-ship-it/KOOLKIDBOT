import { useEffect, useMemo, useState } from 'react';
import { BookOpenText, CalendarDays, ChevronLeft, ChevronRight, Quote, RefreshCw, TrendingDown, TrendingUp } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { journalService } from '../services/journalService';
import type { JournalDay, JournalMonth, JournalYear } from '../services/journalService';
import { Badge, EmptyState, PageHeader, Panel, Spinner } from '../components/ui';

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function money(value: number, currency = 'USD') {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 2, signDisplay: 'exceptZero' }).format(value);
  } catch {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`;
  }
}

function pnlClass(value: number) {
  if (value > 0) return 'text-gain-400';
  if (value < 0) return 'text-loss-400';
  return 'text-slate-500';
}

function dayCardClass(day: JournalDay, selected: boolean) {
  const base = selected ? 'ring-1 ring-brand-400/70 border-brand-400/40' : '';
  if (day.pnl > 0) return `${base} border-gain-500/20 bg-gain-500/[0.045]`;
  if (day.pnl < 0) return `${base} border-loss-500/20 bg-loss-500/[0.045]`;
  return `${base} border-white/[0.06] bg-white/[0.018]`;
}

export default function JournalPage() {
  const { accounts, activeAccount, pushToast } = useHub();
  const now = new Date();
  const [accountLogin, setAccountLogin] = useState<number | ''>(activeAccount?.login || accounts[0]?.login || '');
  const [view, setView] = useState<'month' | 'year'>('month');
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [monthData, setMonthData] = useState<JournalMonth | null>(null);
  const [yearData, setYearData] = useState<JournalYear | null>(null);
  const [selectedDay, setSelectedDay] = useState<JournalDay | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (accountLogin === '' && accounts.length) setAccountLogin(accounts[0].login);
  }, [accounts, accountLogin]);

  const load = async () => {
    if (accountLogin === '') return;
    setLoading(true);
    try {
      if (view === 'year') {
        const data = await journalService.year(Number(accountLogin), year);
        setYearData(data);
        setMonthData(null);
        setSelectedDay(null);
      } else {
        const data = await journalService.month(Number(accountLogin), year, month);
        setMonthData(data);
        setYearData(null);
        setSelectedDay((current) => current ? data.days.find((day) => day.date === current.date) || null : null);
      }
    } catch (error) {
      pushToast('error', 'Journal unavailable', error instanceof Error ? error.message : undefined);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [accountLogin, view, year, month]);

  const currency = monthData?.account.currency || yearData?.account.currency || accounts.find((a) => a.login === accountLogin)?.currency || 'USD';
  const startOffset = useMemo(() => {
    if (!monthData) return 0;
    const jsDay = new Date(monthData.year, monthData.month - 1, 1).getDay();
    return (jsDay + 6) % 7;
  }, [monthData]);

  const years = useMemo(() => {
    const current = now.getFullYear();
    return Array.from({ length: current - 2010 + 1 }, (_, index) => current - index);
  }, []);

  const goMonth = (delta: number) => {
    const next = new Date(year, month - 1 + delta, 1);
    const currentStart = new Date(now.getFullYear(), now.getMonth(), 1);
    if (next > currentStart) return;
    setYear(next.getFullYear());
    setMonth(next.getMonth() + 1);
    setSelectedDay(null);
  };

  const openYearMonth = (targetMonth: number) => {
    setMonth(targetMonth);
    setView('month');
    setSelectedDay(null);
  };

  if (!accounts.length) {
    return (
      <div>
        <PageHeader title="📔 Journal" sub="Account-by-account MT5 trading journal" />
        <Panel><EmptyState icon={BookOpenText} title="No MT5 accounts yet" sub="Connect an MT5 account first, then your journal can build from its trade history." /></Panel>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="📔 Journal"
        sub="Daily, monthly and yearly performance for one MT5 account at a time"
        actions={
          <div className="flex flex-wrap items-center gap-2 max-md:w-full">
            <select className="input !w-auto !py-2 text-xs max-md:flex-1 max-md:min-w-0" value={accountLogin} onChange={(event) => setAccountLogin(Number(event.target.value))}>
              {accounts.map((account) => (
                <option key={account.id} value={account.login}>#{account.login} · {account.nickname || account.broker}</option>
              ))}
            </select>
            <button className="btn-ghost" disabled={loading} onClick={() => void load()}>
              {loading ? <Spinner size={14} /> : <RefreshCw size={14} />} Refresh
            </button>
          </div>
        }
      />

      <Panel className="mb-4 overflow-hidden !border-brand-500/20">
        <div className="relative p-5 md:p-6">
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-brand-500/[0.08] via-transparent to-transparent" />
          <div className="relative flex items-start gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl border border-brand-500/20 bg-brand-500/10 text-brand-300"><Quote size={18} /></span>
            <div>
              <p className="text-[10px] font-extrabold uppercase tracking-[0.20em] text-brand-300">Today's KOOLKID Mindset</p>
              <p className="mt-2 max-w-4xl text-sm font-semibold leading-relaxed text-slate-200">
                {monthData?.today_motivation || 'Stay disciplined. Your next clean setup is worth waiting for.'}
              </p>
            </div>
          </div>
        </div>
      </Panel>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 max-md:items-stretch">
        <div className="flex items-center gap-2 max-md:w-full max-md:[&>button]:flex-1 max-md:[&>button]:justify-center">
          <button className={view === 'month' ? 'btn-primary' : 'btn-ghost'} onClick={() => setView('month')}>Month</button>
          <button className={view === 'year' ? 'btn-primary' : 'btn-ghost'} onClick={() => setView('year')}>Year</button>
        </div>

        <div className="flex flex-wrap items-center gap-2 max-md:w-full max-md:grid max-md:grid-cols-[auto_1fr_1fr_auto]">
          {view === 'month' && <button className="btn-icon" onClick={() => goMonth(-1)}><ChevronLeft size={16} /></button>}
          {view === 'month' && (
            <select className="input !w-auto !py-2 text-xs" value={month} onChange={(event) => { setMonth(Number(event.target.value)); setSelectedDay(null); }}>
              {MONTHS.map((label, index) => (
                <option key={label} value={index + 1} disabled={year === now.getFullYear() && index + 1 > now.getMonth() + 1}>{label}</option>
              ))}
            </select>
          )}
          <select className="input !w-auto !py-2 text-xs" value={year} onChange={(event) => { setYear(Number(event.target.value)); setSelectedDay(null); }}>
            {years.map((value) => <option key={value}>{value}</option>)}
          </select>
          {view === 'month' && <button className="btn-icon" disabled={year === now.getFullYear() && month === now.getMonth() + 1} onClick={() => goMonth(1)}><ChevronRight size={16} /></button>}
        </div>
      </div>

      {view === 'month' && monthData && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
            {[
              ['Net P/L', money(monthData.summary.net_pnl, currency), monthData.summary.net_pnl],
              ['Trades', monthData.summary.trades, null],
              ['Win rate', `${monthData.summary.win_rate.toFixed(1)}%`, null],
              ['Winning days', monthData.summary.winning_days, null],
              ['Losing days', monthData.summary.losing_days, null],
              ['Avg day', money(monthData.summary.average_day_pnl, currency), monthData.summary.average_day_pnl],
              ['Best day', monthData.summary.best_day ? money(monthData.summary.best_day.pnl, currency) : '—', monthData.summary.best_day?.pnl ?? null],
              ['Worst day', monthData.summary.worst_day ? money(monthData.summary.worst_day.pnl, currency) : '—', monthData.summary.worst_day?.pnl ?? null],
            ].map(([label, value, pnl]) => (
              <Panel key={String(label)} className="p-3">
                <p className="text-[9px] font-bold uppercase tracking-wider text-slate-600">{label}</p>
                <p className={`mono mt-1 text-sm font-extrabold ${typeof pnl === 'number' ? pnlClass(pnl) : 'text-white'}`}>{String(value)}</p>
              </Panel>
            ))}
          </div>

          <Panel className="md:hidden p-2.5">
            <div className="grid grid-cols-7 gap-1 mb-1">
              {WEEKDAYS.map((day) => <div key={day} className="py-1 text-center text-[8px] font-bold uppercase tracking-wider text-slate-600">{day.slice(0, 1)}</div>)}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {Array.from({ length: startOffset }).map((_, index) => <div key={`mobile-empty-${index}`} />)}
              {monthData.days.map((day) => (
                <button
                  key={`mobile-${day.date}`}
                  className={`min-h-[72px] rounded-lg border p-1.5 text-left transition ${dayCardClass(day, selectedDay?.date === day.date)}`}
                  onClick={() => setSelectedDay(day)}
                >
                  <div className="flex items-center justify-between gap-1">
                    <span className="mono text-[10px] font-bold text-slate-300">{day.day}</span>
                    {day.trades > 0 && <span className="h-1.5 w-1.5 rounded-full bg-brand-400" />}
                  </div>
                  <p className={`mono mt-2 truncate text-[9px] font-extrabold ${pnlClass(day.pnl)}`}>{money(day.pnl, currency)}</p>
                  <p className="mt-1 truncate text-[8px] text-slate-600">{day.trades ? `${day.trades} trade${day.trades === 1 ? '' : 's'}` : '—'}</p>
                </button>
              ))}
            </div>
          </Panel>

          <Panel className="hidden md:block overflow-x-auto p-3 md:p-4">
            <div className="min-w-[900px]">
              <div className="mb-2 grid grid-cols-7 gap-2">
                {WEEKDAYS.map((day) => <div key={day} className="px-2 py-1 text-center text-[9px] font-bold uppercase tracking-[0.18em] text-slate-600">{day}</div>)}
              </div>
              <div className="grid grid-cols-7 gap-2">
                {Array.from({ length: startOffset }).map((_, index) => <div key={`empty-${index}`} />)}
                {monthData.days.map((day) => (
                  <button
                    key={day.date}
                    className={`min-h-[142px] rounded-xl border p-3 text-left transition hover:-translate-y-0.5 hover:border-brand-400/30 ${dayCardClass(day, selectedDay?.date === day.date)}`}
                    onClick={() => setSelectedDay(day)}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="mono text-xs font-bold text-slate-300">{day.day}</span>
                      {day.trades > 0 && <Badge tone={day.pnl > 0 ? 'gain' : day.pnl < 0 ? 'loss' : 'slate'}>{day.trades} trade{day.trades === 1 ? '' : 's'}</Badge>}
                    </div>
                    <p className={`mono mt-3 text-base font-extrabold ${pnlClass(day.pnl)}`}>{money(day.pnl, currency)}</p>
                    <p className="mt-1 text-[10px] text-slate-600">{day.trades ? `${day.wins}W · ${day.losses}L · ${day.win_rate.toFixed(0)}%` : 'No trades'}</p>
                    {day.motivation && <p className="mt-3 line-clamp-2 text-[10px] leading-relaxed text-slate-500">“{day.motivation}”</p>}
                  </button>
                ))}
              </div>
            </div>
          </Panel>
        </>
      )}

      {view === 'year' && yearData && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
            <Panel className="p-4"><p className="text-[9px] font-bold uppercase text-slate-600">Year P/L</p><p className={`mono mt-1 text-lg font-extrabold ${pnlClass(yearData.summary.net_pnl)}`}>{money(yearData.summary.net_pnl, currency)}</p></Panel>
            <Panel className="p-4"><p className="text-[9px] font-bold uppercase text-slate-600">Trades</p><p className="mono mt-1 text-lg font-extrabold text-white">{yearData.summary.trades}</p></Panel>
            <Panel className="p-4"><p className="text-[9px] font-bold uppercase text-slate-600">Win rate</p><p className="mono mt-1 text-lg font-extrabold text-white">{yearData.summary.win_rate.toFixed(1)}%</p></Panel>
            <Panel className="p-4"><p className="text-[9px] font-bold uppercase text-slate-600">Profitable months</p><p className="mono mt-1 text-lg font-extrabold text-gain-400">{yearData.summary.profitable_months}</p></Panel>
            <Panel className="p-4"><p className="text-[9px] font-bold uppercase text-slate-600">Losing months</p><p className="mono mt-1 text-lg font-extrabold text-loss-400">{yearData.summary.losing_months}</p></Panel>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {yearData.months.map((item) => (
              <button key={item.month} type="button" className="text-left" onClick={() => openYearMonth(item.month)}>
                <Panel hover className="p-4 cursor-pointer h-full">
                  <div className="flex items-center justify-between">
                    <div><p className="text-sm font-extrabold text-white">{MONTHS[item.month - 1]}</p><p className="mt-1 text-[10px] text-slate-600">{item.trades} trades · {item.win_rate.toFixed(1)}% WR</p></div>
                    {item.pnl > 0 ? <TrendingUp size={17} className="text-gain-400" /> : item.pnl < 0 ? <TrendingDown size={17} className="text-loss-400" /> : <CalendarDays size={17} className="text-slate-600" />}
                  </div>
                  <p className={`mono mt-4 text-xl font-extrabold ${pnlClass(item.pnl)}`}>{money(item.pnl, currency)}</p>
                </Panel>
              </button>
            ))}
          </div>
        </>
      )}

      {selectedDay && view === 'month' && (
        <Panel className="mt-4 p-5 max-md:p-4">
          <div className="flex flex-wrap items-start justify-between gap-3 max-md:flex-col">

            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-brand-300">Daily Review</p>
              <h3 className="mt-1 text-lg font-extrabold text-white">{new Date(selectedDay.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}</h3>
              {selectedDay.motivation && <p className="mt-2 max-w-3xl text-xs italic text-slate-400">“{selectedDay.motivation}”</p>}
            </div>
            <div className="text-right max-md:text-left">
              <p className={`mono text-xl font-extrabold ${pnlClass(selectedDay.pnl)}`}>{money(selectedDay.pnl, currency)}</p>
              <p className="text-[10px] text-slate-600">{selectedDay.trades} trades · {selectedDay.wins} wins · {selectedDay.losses} losses</p>
            </div>
          </div>

          {selectedDay.trade_rows.length ? (
            <>
            <div className="mt-4 hidden md:block overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-xs">
                <thead className="border-b border-white/[0.07] text-[9px] uppercase tracking-wider text-slate-600">
                  <tr><th className="py-2">Time</th><th>Symbol</th><th>Side</th><th>Volume</th><th>Source</th><th className="text-right">P/L</th></tr>
                </thead>
                <tbody>
                  {selectedDay.trade_rows.map((trade, index) => (
                    <tr key={`${trade.ticket || trade.id || index}-${trade.close_time}`} className="border-b border-white/[0.04]">
                      <td className="py-3 text-slate-500">{new Date(trade.close_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td>
                      <td className="font-semibold text-slate-200">{trade.symbol}</td>
                      <td className="uppercase text-slate-400">{trade.type}</td>
                      <td className="mono text-slate-400">{Number(trade.volume || 0).toFixed(2)}</td>
                      <td className="text-slate-500">{trade.source || 'MT5'}</td>
                      <td className={`mono text-right font-bold ${pnlClass(Number(trade.net_pl || 0))}`}>{money(Number(trade.net_pl || 0), currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 md:hidden divide-y divide-white/[0.06] rounded-xl border border-white/[0.06] overflow-hidden">
              {selectedDay.trade_rows.map((trade, index) => (
                <div key={`mobile-${trade.ticket || trade.id || index}-${trade.close_time}`} className="p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-bold text-white">{trade.symbol} <span className="text-[10px] uppercase text-slate-500">{trade.type}</span></p>
                      <p className="mt-1 text-[10px] text-slate-600">{new Date(trade.close_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · {trade.source || 'MT5'}</p>
                    </div>
                    <p className={`mono text-sm font-bold ${pnlClass(Number(trade.net_pl || 0))}`}>{money(Number(trade.net_pl || 0), currency)}</p>
                  </div>
                  <p className="mt-2 text-[10px] text-slate-500">Volume <span className="mono text-slate-300">{Number(trade.volume || 0).toFixed(2)}</span></p>
                </div>
              ))}
            </div>
            </>
          ) : <p className="mt-4 text-xs text-slate-500">No closed trades were recorded for this day.</p>}
        </Panel>
      )}

      {(monthData?.refresh_error || yearData?.refresh_error) && (
        <p className="mt-3 text-[10px] text-slate-600">
          Showing saved journal history. Live MT5 refresh is unavailable right now: {monthData?.refresh_error || yearData?.refresh_error}
        </p>
      )}
    </div>
  );
}
