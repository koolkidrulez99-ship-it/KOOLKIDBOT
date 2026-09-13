import { useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import Sidebar from '../components/Sidebar';
import TopBar from '../components/TopBar';
import Toasts from '../components/Toasts';
import { useHub } from '../context/HubContext';
import { Skel } from '../components/ui';
import { RefreshCw } from 'lucide-react';
import { appVersion, isSimulation } from '../config/runtime';
import WorkspaceRestorer from '../components/WorkspaceRestorer';
import CopyTradeApproval from '../components/CopyTradeApproval';

function BootSkeleton() {
  return <div className="px-4 md:px-6 py-6 space-y-5 max-w-[1600px]"><Skel className="h-8 w-64" /><div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">{Array.from({ length: 4 }).map((_, i) => <Skel key={i} className="h-28" />)}</div><Skel className="h-[360px]" /><div className="grid grid-cols-1 lg:grid-cols-2 gap-4"><Skel className="h-56" /><Skel className="h-56" /></div></div>;
}

export default function Shell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const { loading, bridgeStarting, error, refresh, bridge } = useHub();

  return (
    <div className="min-h-screen">
      <WorkspaceRestorer />
      <div className="pointer-events-none fixed inset-x-0 top-0 h-[420px] bg-grid z-0" />
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="relative z-10 lg:pl-[248px] flex flex-col min-h-screen">
        <TopBar onMenu={() => setMenuOpen(true)} />
        <main className="flex-1">
          {loading ? (bridgeStarting ? <div className="flex flex-col items-center justify-center py-32 px-6 text-center"><RefreshCw className="animate-spin text-brand-300" size={26} /><h3 className="mt-5 text-lg font-bold text-white">Connecting to MT5 bridge...</h3><p className="text-sm text-slate-500 mt-2">Waiting for the separate local bridge to become ready.</p></div> : <BootSkeleton />) : error ? (
            <div className="flex flex-col items-center justify-center py-32 px-6 text-center"><div className="rounded-2xl bg-loss-500/10 border border-loss-500/25 p-4 text-loss-400 mb-5">!</div><h3 className="text-lg font-bold text-white">MT5 Hub could not load</h3><p className="text-sm text-slate-500 mt-2 max-w-sm">{error}</p><button className="btn-primary mt-6" onClick={() => refresh()}><RefreshCw size={15} /> Retry</button></div>
          ) : (
            <motion.div key={location.pathname} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.28, ease: 'easeOut' }} className="px-4 md:px-6 py-6 max-w-[1600px]"><Outlet /></motion.div>
          )}
        </main>
        <footer className="px-6 py-4 text-[11px] text-slate-600 border-t border-white/[0.05] flex flex-wrap gap-x-6 gap-y-1"><span>MT5 Hub module v{appVersion}</span><span>{isSimulation ? 'Runtime: self-contained simulation' : `Bridge: ${bridge?.status || 'unknown'}`}</span><span className="mono">{isSimulation ? 'Real MT5 execution disabled' : (bridge?.endpoint || 'Bridge endpoint not configured')}</span></footer>
      </div>
      <Toasts />
      <CopyTradeApproval />
    </div>
  );
}
