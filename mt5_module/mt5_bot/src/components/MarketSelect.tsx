import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Search } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { isSimulation } from '../config/runtime';
import { groupMt5Symbols, simulationSymbolRows } from '../lib/symbols';

export default function MarketSelect({ value, onChange, compact = false, tradeOnly = false }: { value: string; onChange: (symbol: string) => void; compact?: boolean; tradeOnly?: boolean }) {
  const { mt5Symbols } = useHub();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const allRows = useMemo(() => {
    const rows = isSimulation ? simulationSymbolRows() : mt5Symbols;
    return tradeOnly ? rows.filter((row) => row.trade_allowed) : rows;
  }, [mt5Symbols, tradeOnly]);
  const source = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? allRows.filter((row) => `${row.symbol} ${row.description} ${row.category || ''} ${row.path || ''}`.toLowerCase().includes(q)) : allRows;
  }, [allRows, query]);
  const groups = useMemo(() => groupMt5Symbols(source), [source]);
  const selected = allRows.find((row) => row.symbol === value);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) {
        setOpen(false);
        setQuery('');
      }
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  if (compact) {
    return (
      <div className="relative" ref={wrapRef}>
        <button type="button" className="input flex w-full items-center justify-between gap-3 text-left" onClick={() => setOpen((current) => !current)} aria-expanded={open}>
          <span className="min-w-0">
            <span className="mono block truncate text-slate-100">{value || 'Choose symbol'}</span>
            {selected?.description && selected.description !== value && <span className="block truncate text-[10px] text-slate-600">{selected.description}</span>}
          </span>
          <ChevronDown size={15} className={`shrink-0 text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
        {open && (
          <div className="absolute left-0 right-0 z-[80] mt-2 min-w-[300px] overflow-hidden rounded-xl border border-white/10 bg-[#0b1019] p-2 shadow-2xl">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-600" />
              <input autoFocus className="input !pl-9 !py-2 text-xs" value={query} onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Escape') { setOpen(false); setQuery(''); } }}
                placeholder="Search symbol, market or category…" />
            </div>
            <div className="mt-2 max-h-72 overflow-y-auto pr-1">
              {!groups.length && <p className="px-3 py-6 text-center text-xs text-slate-600">No matching markets.</p>}
              {groups.map(([group, rows]) => (
                <div key={group} className="mb-2 last:mb-0">
                  <p className="sticky top-0 bg-[#0b1019] px-2 py-1 text-[9px] font-bold uppercase tracking-widest text-slate-600">{group} · {rows.length}</p>
                  {rows.map((row) => (
                    <button key={row.symbol} type="button"
                      onClick={() => { onChange(row.symbol); setOpen(false); setQuery(''); }}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-white/[0.06]">
                      <span className="min-w-0 flex-1">
                        <span className="mono block truncate text-xs font-bold text-slate-200">{row.symbol}</span>
                        {row.description && row.description !== row.symbol && <span className="block truncate text-[10px] text-slate-600">{row.description}</span>}
                      </span>
                      {row.symbol === value && <Check size={14} className="shrink-0 text-brand-300" />}
                    </button>
                  ))}
                </div>
              ))}
            </div>
            <p className="border-t border-white/[0.06] px-2 pt-2 text-[9px] text-slate-600">
              {isSimulation ? source.length + ' simulated markets' : source.length + ' broker symbols'} · type to filter instantly
            </p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-white/[0.07] bg-black/20 p-2.5 min-w-[260px]">
      <div className="relative mb-2">
        <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-600" />
        <input className="input !pl-8 !py-2 text-xs" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search broker markets…" />
      </div>
      <select className="input !py-2 text-xs" value={value} onChange={(e) => onChange(e.target.value)}>
        {groups.map(([group, rows]) => (
          <optgroup key={group} label={group + ' (' + rows.length + ')'}>
            {rows.map((row) => <option key={row.symbol} value={row.symbol}>{row.symbol}{row.description && row.description !== row.symbol ? ' — ' + row.description : ''}</option>)}
          </optgroup>
        ))}
      </select>
      <p className="mt-1.5 text-[10px] text-slate-600">{isSimulation ? source.length + ' simulated markets available' : source.length + ' broker symbols loaded from MT5'}</p>
    </div>
  );
}
