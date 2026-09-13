import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { isSimulation } from '../config/runtime';
import { groupMt5Symbols, simulationSymbolRows } from '../lib/symbols';

export default function MarketSelect({ value, onChange, compact = false, tradeOnly = false }: { value: string; onChange: (symbol: string) => void; compact?: boolean; tradeOnly?: boolean }) {
  const { mt5Symbols } = useHub();
  const [query, setQuery] = useState('');
  const source = useMemo(() => {
    const allRows = isSimulation ? simulationSymbolRows() : mt5Symbols;
    const rows = tradeOnly ? allRows.filter((r) => r.trade_allowed) : allRows;
    const q = query.trim().toLowerCase();
    return q ? rows.filter((r) => `${r.symbol} ${r.description} ${r.category || ''} ${r.path || ''}`.toLowerCase().includes(q)) : rows;
  }, [mt5Symbols, query, tradeOnly]);
  const groups = useMemo(() => groupMt5Symbols(source), [source]);

  if (compact) {
    return (
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {groups.map(([group, rows]) => (
          <optgroup key={group} label={group}>
            {rows.map((r) => <option key={r.symbol} value={r.symbol}>{r.symbol}{r.description && r.description !== r.symbol ? ` — ${r.description}` : ''}</option>)}
          </optgroup>
        ))}
      </select>
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
          <optgroup key={group} label={`${group} (${rows.length})`}>
            {rows.map((r) => <option key={r.symbol} value={r.symbol}>{r.symbol}{r.description && r.description !== r.symbol ? ` — ${r.description}` : ''}</option>)}
          </optgroup>
        ))}
      </select>
      <p className="mt-1.5 text-[10px] text-slate-600">{isSimulation ? `${source.length} simulated markets available` : `${source.length} broker symbols loaded from MT5`}</p>
    </div>
  );
}
