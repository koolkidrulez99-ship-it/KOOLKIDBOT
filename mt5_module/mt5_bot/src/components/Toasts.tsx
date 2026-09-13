import { AnimatePresence, motion } from 'framer-motion';
import { Check, Info, TriangleAlert, X } from 'lucide-react';
import { useHub } from '../context/HubContext';

const ICONS = {
  success: { Icon: Check, cls: 'text-gain-400 bg-gain-500/12 border-gain-500/30' },
  error: { Icon: TriangleAlert, cls: 'text-loss-400 bg-loss-500/12 border-loss-500/30' },
  warning: { Icon: TriangleAlert, cls: 'text-warn-400 bg-warn-400/10 border-warn-400/30' },
  info: { Icon: Info, cls: 'text-brand-300 bg-brand-500/12 border-brand-500/30' },
};

export default function Toasts() {
  const { toasts, dismissToast } = useHub();
  return (
    <div className="fixed bottom-5 right-5 z-[90] flex flex-col gap-2.5 w-[min(92vw,380px)]">
      <AnimatePresence>
        {toasts.map((t) => {
          const { Icon, cls } = ICONS[t.tone];
          return (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, x: 42, scale: 0.96 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 42, scale: 0.96 }}
              transition={{ type: 'spring', stiffness: 420, damping: 30 }}
              className="glass-strong rounded-xl px-4 py-3 flex items-start gap-3 shadow-2xl"
            >
              <span className={`shrink-0 rounded-lg border p-1.5 ${cls}`}>
                <Icon size={14} strokeWidth={2.5} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-semibold text-white leading-snug">{t.title}</p>
                {t.message && <p className="text-xs text-slate-500 mt-0.5 leading-snug">{t.message}</p>}
              </div>
              <button onClick={() => dismissToast(t.id)} className="shrink-0 text-slate-600 hover:text-slate-300 transition-colors cursor-pointer">
                <X size={14} />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
