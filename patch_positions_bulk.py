from pathlib import Path
p=Path(r'C:\Users\jjmje\Desktop\deriv-bot-site\mt5_module\mt5_bot\src\pages\PositionsPage.tsx')
s=p.read_text(encoding='utf-8-sig')
s=s.replace("import { Layers, ShieldAlert, X } from 'lucide-react';", "import { Layers, ShieldAlert, TrendingDown, TrendingUp, X } from 'lucide-react';")
s=s.replace("  const [confirmCloseAll, setConfirmCloseAll] = useState(false);", "  const [confirmCloseAll, setConfirmCloseAll] = useState(false);\n  const [confirmBulk, setConfirmBulk] = useState<'profit' | 'loss' | null>(null);")
needle="  const shortPl = shorts.reduce((s, p) => s + shownProfit(p), 0);\n"
insert="""  const shortPl = shorts.reduce((s, p) => s + shownProfit(p), 0);
  const profitablePositions = shownPositions.filter((p) => shownProfit(p) > 0);
  const losingPositions = shownPositions.filter((p) => shownProfit(p) < 0);
  const profitablePl = profitablePositions.reduce((s, p) => s + shownProfit(p), 0);
  const losingPl = losingPositions.reduce((s, p) => s + shownProfit(p), 0);
"""
if needle not in s: raise SystemExit('stats needle not found')
s=s.replace(needle,insert,1)
p.write_text(s,encoding='utf-8')
print('STEP1_OK')
s=p.read_text(encoding='utf-8')
needle="""  const doCloseAll = async () => {
"""
helper="""  const closeSelected = async (targets: DisplayPosition[], label: string) => {
    if (!targets.length) return;
    try {
      const multiTargets = targets.filter((p) => p.multiAccountId).map((p) => ({ account_id: p.multiAccountId!, ticket: p.ticket }));
      const bridgeTargets = targets.filter((p) => !p.multiAccountId);
      if (multiTargets.length) await mt5MultiAccountService.closeMany(multiTargets);
      if (bridgeTargets.length) await Promise.all(bridgeTargets.map((p) => closePosition(p.id)));
      pushToast('success', `${label}: ${targets.length} close request${targets.length === 1 ? '' : 's'} sent`);
      if (multiOnline) await loadMultiPositions();
      await refresh(true);
    } catch (e) {
      pushToast('error', `${label} failed`, e instanceof Error ? e.message : undefined);
    }
  };

  const doCloseAll = async () => {
"""
if needle not in s: raise SystemExit('doCloseAll needle missing')
s=s.replace(needle,helper,1)
p.write_text(s,encoding='utf-8')
print('STEP2_OK')
s=p.read_text(encoding='utf-8')
old="""        actions={
          shownPositions.length > 0 ? (
            <button className=\"btn-danger\" onClick={() => (prefs.confirmDanger ? setConfirmCloseAll(true) : doCloseAll())}>
              <ShieldAlert size={15} /> Close All Positions
            </button>
          ) : undefined
        }
"""
new="""        actions={
          shownPositions.length > 0 ? (
            <div className=\"flex flex-wrap gap-2\">
              <button className=\"btn-secondary\" disabled={!profitablePositions.length} onClick={() => setConfirmBulk('profit')}>
                <TrendingUp size={15} /> Close All Profitable
              </button>
              <button className=\"btn-secondary\" disabled={!losingPositions.length} onClick={() => setConfirmBulk('loss')}>
                <TrendingDown size={15} /> Close All Losing
              </button>
              <button className=\"btn-danger\" onClick={() => (prefs.confirmDanger ? setConfirmCloseAll(true) : doCloseAll())}>
                <ShieldAlert size={15} /> Close All Positions
              </button>
            </div>
          ) : undefined
        }
"""
if old not in s: raise SystemExit('header block missing')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
print('STEP3_OK')
s=p.read_text(encoding='utf-8')
needle="""      <ConfirmModal
        open={confirmCloseAll}
"""
bulk="""      <ConfirmModal
        open={confirmBulk !== null}
        onClose={() => setConfirmBulk(null)}
        title={confirmBulk === 'profit' ? 'Close all profitable positions?' : 'Close all losing positions?'}
        tone={confirmBulk === 'profit' ? 'warning' : 'danger'}
        confirmLabel={confirmBulk === 'profit' ? 'Close Profitable' : 'Close Losing'}
        message={confirmBulk === 'profit'
          ? <>All <span className=\"mono font-bold text-white\">{profitablePositions.length}</span> positions currently above $0 floating P/L will be closed, realizing approximately <span className=\"mono font-bold text-gain-400\">{fmtSigned(profitablePl)}</span>. Break-even and losing positions stay open.</>
          : <>All <span className=\"mono font-bold text-white\">{losingPositions.length}</span> positions currently below $0 floating P/L will be closed, realizing approximately <span className=\"mono font-bold text-loss-400\">{fmtSigned(losingPl)}</span>. Break-even and profitable positions stay open.</>}
        onConfirm={() => confirmBulk === 'profit'
          ? closeSelected(profitablePositions, 'Close profitable')
          : closeSelected(losingPositions, 'Close losing')}
      />

      <ConfirmModal
        open={confirmCloseAll}
"""
if needle not in s: raise SystemExit('modal needle missing')
s=s.replace(needle,bulk,1)
p.write_text(s,encoding='utf-8')
print('STEP4_OK')
