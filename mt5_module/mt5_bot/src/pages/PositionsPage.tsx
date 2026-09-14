import { useEffect, useMemo, useState } from 'react';
import { Layers, ShieldAlert, X } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { fmtPrice, fmtSigned, profitTone, timeAgo } from '../lib/format';
import { Badge, EmptyState, PageHeader, Panel, Spinner } from '../components/ui';
import ConfirmModal from '../components/ConfirmModal';
import { closeAllPositions, closePosition } from '../lib/actions';
import { MARKET } from '../lib/market';
import { isSimulation } from '../config/runtime';
import { mt5MultiAccountService, type MultiPosition } from '../services/mt5MultiAccountService';
import type { Mt5Position } from '../types';

type DisplayPosition = Mt5Position & { multiAccountId?: string; multiAccountName?: string };

function openedAt(position: DisplayPosition): number {
  const parsed = Date.parse(position.open_time);
  return Number.isFinite(parsed) ? parsed : 0;
}

function mapMultiPosition(row: MultiPosition, index: number): DisplayPosition {
  const side = String(row.side || row.type || '').toUpperCase();
  const type = side === 'SELL' || side === '1' ? 'sell' : 'buy';
  const openTime = row.open_time || (row.time ? new Date(Number(row.time) * 1000).toISOString() : new Date().toISOString());
  return {
    id: Number(row.ticket) || index + 1,
    ticket: Number(row.ticket) || index + 1,
    account_login: Number(row.account_login || 0),
    symbol: row.symbol,
    type,
    volume: Number(row.volume || 0),
    open_price: Number(row.open_price ?? row.price_open ?? 0),
    current_price: Number(row.current_price ?? row.price_current ?? row.open_price ?? row.price_open ?? 0),
    sl: row.sl ? Number(row.sl) : null,
    tp: row.tp ? Number(row.tp) : null,
    profit: Number(row.profit || 0),
    swap: Number(row.swap || 0),
    commission: Number(row.commission || 0),
    open_time: openTime,
    source: String(row.source || 'MT5'),
    magic: row.magic == null ? null : Number(row.magic),
    multiAccountId: row.account_id,
    multiAccountName: row.account_nickname,
  };
}

export default function PositionsPage() {
  const { positions, scopePositions, livePrice, liveProfit, accountName, pushToast, refresh, prefs, derived } = useHub();
  const [closingId, setClosingId] = useState<number | null>(null);
  const [confirmCloseAll, setConfirmCloseAll] = useState(false);
  const [multiPositions, setMultiPositions] = useState<DisplayPosition[]>([]);
  const [multiOnline, setMultiOnline] = useState(false);

  const loadMultiPositions = async () => {
    try {
      const rows = await mt5MultiAccountService.positions();
      setMultiPositions((rows.positions || []).map(mapMultiPosition));
      setMultiOnline(true);
    } catch {
      setMultiPositions([]);
      setMultiOnline(false);
    }
  };

  useEffect(() => {
    loadMultiPositions();
    const timer = window.setInterval(loadMultiPositions, 2500);
    return () => window.clearInterval(timer);
  }, []);

  const shownPositions: DisplayPosition[] = useMemo(() => {
    if (!multiOnline) {
      return [...(scopePositions as DisplayPosition[])].sort((a, b) => openedAt(b) - openedAt(a) || b.ticket - a.ticket);
    }
    const workerKeys = new Set(multiPositions.map((p) => `${p.account_login}:${p.ticket}`));
    const bridgeOnly = positions.filter((p) => !workerKeys.has(`${p.account_login}:${p.ticket}`));
    return [...multiPositions, ...(bridgeOnly as DisplayPosition[])]
      .sort((a, b) => openedAt(b) - openedAt(a) || b.ticket - a.ticket);
  }, [multiOnline, multiPositions, positions, scopePositions]);
  const shownProfit = (p: DisplayPosition) => p.multiAccountId ? Number(p.profit || 0) : liveProfit(p);

  const net = useMemo(() => shownPositions.reduce((s, p) => s + shownProfit(p), 0), [shownPositions]);
  const longs = shownPositions.filter((p) => p.type === 'buy');
  const shorts = shownPositions.filter((p) => p.type === 'sell');
  const longPl = longs.reduce((s, p) => s + shownProfit(p), 0);
  const shortPl = shorts.reduce((s, p) => s + shownProfit(p), 0);

  const close = async (position: DisplayPosition) => {
    const id = position.id;
    setClosingId(id);
    try {
      if (position.multiAccountId) {
        await mt5MultiAccountService.closePosition(position.multiAccountId, position.ticket);
        pushToast('success', `Position #${position.ticket} close requested`, `${position.multiAccountId} · ${position.symbol}`);
        await loadMultiPositions();
      } else {
        const r = await closePosition(id);
        pushToast(r.profit >= 0 ? 'success' : 'warning', `Position #${position.ticket} closed`, `Realized ${fmtSigned(r.profit)} \u2014 moved to history.`);
      }
      await refresh(true);
    } catch (e) {
      pushToast('error', 'Close failed', e instanceof Error ? e.message : undefined);
    } finally {
      setClosingId(null);
    }
  };

  const doCloseAll = async () => {
    try {
      if (multiOnline) {
        await Promise.all(shownPositions.map((p) => p.multiAccountId
          ? mt5MultiAccountService.closePosition(p.multiAccountId, p.ticket)
          : closePosition(p.id)));
        pushToast('success', `Close requested for ${shownPositions.length} position${shownPositions.length === 1 ? '' : 's'}`);
        await loadMultiPositions();
      } else {
        const r = await closeAllPositions();
        pushToast(r.realized >= 0 ? 'success' : 'warning', `Closed ${r.closed} position${r.closed === 1 ? '' : 's'}`, `Realized P/L ${fmtSigned(r.realized)} moved to history.`);
      }
      await refresh(true);
    } catch (e) {
      pushToast('error', 'Close-all failed', e instanceof Error ? e.message : undefined);
    }
  };

  return (
    <div>
      <PageHeader
        title="Open Positions"
        sub={multiOnline ? 'Open positions across all connected MT5 account workers' : isSimulation ? 'Open simulation positions · local prices update every 2s' : 'Open MT5 positions reported by the configured terminal bridge'}
        actions={
          shownPositions.length > 0 ? (
            <button className="btn-danger" onClick={() => (prefs.confirmDanger ? setConfirmCloseAll(true) : doCloseAll())}>
              <ShieldAlert size={15} /> Close All Positions
            </button>
          ) : undefined
        }
      />

      <div className="flex flex-wrap gap-2.5 mb-5">
        <span className="chip"><span className="text-slate-500">Open</span><span className="mono font-bold text-white">{shownPositions.length}</span></span>
        <span className="chip"><span className="text-slate-500">Net floating</span><span className={`mono font-bold ${profitTone(net)}`}>{fmtSigned(net)}</span></span>
        <span className="chip"><span className="text-slate-500">Long {longs.length}</span><span className={`mono font-bold ${profitTone(longPl)}`}>{fmtSigned(longPl)}</span></span>
        <span className="chip"><span className="text-slate-500">Short {shorts.length}</span><span className={`mono font-bold ${profitTone(shortPl)}`}>{fmtSigned(shortPl)}</span></span>
      </div>

      {shownPositions.length === 0 ? (
        <Panel>
          <EmptyState icon={Layers} title="No open positions" sub={isSimulation ? 'Simulated manual or bot-sourced tickets will appear here.' : 'MT5 positions reported by the bridge will appear here.'} />
        </Panel>
      ) : (
        <Panel className="overflow-hidden">
          <div className="hidden md:block overflow-x-auto">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Ticket</th>
                  <th>Opened</th>
                  <th>Account</th>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th className="!text-right">Volume</th>
                  <th className="!text-right">Open</th>
                  <th className="!text-right">Current</th>
                  <th className="!text-right">S/L</th>
                  <th className="!text-right">T/P</th>
                  <th className="!text-right">Floating P/L</th>
                  <th>Source</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {shownPositions.map((p) => {
                  const pl = shownProfit(p);
                  const cur = livePrice(p.symbol) || Number(p.current_price);
                  const dist = Math.abs(cur - Number(p.open_price));
                  const pipsMove = MARKET[p.symbol] ? dist / MARKET[p.symbol].pip : 0;
                  return (
                    <tr key={`${p.multiAccountId || p.account_login}:${p.ticket}`}>
                      <td className="mono text-xs text-slate-500">#{p.ticket}</td>
                      <td className="text-xs text-slate-500">{timeAgo(p.open_time)}</td>
                      <td className="text-xs text-slate-300">{p.multiAccountName || accountName(p.account_login)}</td>
                      <td className="font-semibold text-white text-[13px]">{p.symbol}</td>
                      <td><Badge tone={p.type === 'buy' ? 'brand' : 'loss'}>{p.type}</Badge></td>
                      <td className="mono !text-right text-[13px] text-slate-200">{Number(p.volume).toFixed(2)}</td>
                      <td className="mono !text-right text-[13px] text-slate-400">{fmtPrice(Number(p.open_price), p.symbol)}</td>
                      <td className="mono !text-right text-[13px] text-white font-semibold">{fmtPrice(cur, p.symbol)}</td>
                      <td className="mono !text-right text-xs text-slate-500">{p.sl ? fmtPrice(Number(p.sl), p.symbol) : '\u2014'}</td>
                      <td className="mono !text-right text-xs text-slate-500">{p.tp ? fmtPrice(Number(p.tp), p.symbol) : '\u2014'}</td>
                      <td className={`mono !text-right text-[13px] font-bold ${profitTone(pl)}`}>
                        {fmtSigned(pl)}
                        <span className="block text-[9px] font-medium opacity-60">{pipsMove.toFixed(1)} pips</span>
                      </td>
                      <td className="text-xs">
                        {p.source === 'Manual' ? (
                          <span className="text-slate-400">Manual</span>
                        ) : (
                          <span className="text-brand-300">{p.source}</span>
                        )}
                      </td>
                      <td>
                        <button
                          className="btn-icon !p-1.5 hover:!text-loss-400 hover:!bg-loss-500/15"
                          title="Close at market"
                          disabled={closingId === p.id}
                          onClick={() => close(p)}
                        >
                          {closingId === p.id ? <Spinner size={13} /> : <X size={14} />}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="md:hidden divide-y divide-white/[0.06]">
            {shownPositions.map((p) => {
              const pl = shownProfit(p);
              const cur = livePrice(p.symbol) || Number(p.current_price);
              return <div key={`${p.multiAccountId || p.account_login}:${p.ticket}`} className="p-4">
                <div className="flex items-start justify-between gap-3"><div><p className="font-bold text-white">{p.symbol} <Badge tone={p.type === 'buy' ? 'brand' : 'loss'}>{p.type}</Badge></p><p className="mono text-[10px] text-slate-600 mt-1">#{p.ticket} · {timeAgo(p.open_time)}</p></div><p className={`mono text-sm font-bold ${profitTone(pl)}`}>{fmtSigned(pl)}</p></div>
                <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-[11px]"><p className="text-slate-500">Account <span className="block text-slate-300">{p.multiAccountName || accountName(p.account_login)}</span></p><p className="text-slate-500">Source <span className="block text-slate-300">{p.source}</span></p><p className="text-slate-500">Volume <span className="mono block text-slate-300">{Number(p.volume).toFixed(2)}</span></p><p className="text-slate-500">Current <span className="mono block text-slate-300">{fmtPrice(cur, p.symbol)}</span></p></div>
                <button className="btn-danger mt-3 w-full justify-center" disabled={closingId === p.id} onClick={() => close(p)}>{closingId === p.id ? <Spinner size={13} /> : <X size={14} />} Close Position</button>
              </div>;
            })}
          </div>
        </Panel>
      )}

      <ConfirmModal
        open={confirmCloseAll}
        onClose={() => setConfirmCloseAll(false)}
        title="Close all positions?"
        tone="danger"
        confirmLabel="Close All Positions"
        message={
          <>All <span className="mono font-bold text-white">{shownPositions.length}</span> open tickets {multiOnline ? 'across connected account workers' : 'in this scope'} will be market-closed, realizing <span className={`mono font-bold ${profitTone(derived.floating)}`}>{fmtSigned(net)}</span> of floating P/L.</>
        }
        onConfirm={doCloseAll}
      />
    </div>
  );
}
