import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, Brain, Globe, RefreshCw, ShieldAlert, Sparkles, TrendingUp, X, Zap } from 'lucide-react';
import { useHub } from '../context/HubContext';
import { timeAgo } from '../lib/format';
import { Badge, PageHeader, Panel, Progress, Skel, Spinner, Toggle } from '../components/ui';
import type { AiInsight, AiSettings } from '../types';
import { aiControlService } from '../services/aiControlService';
import { isSimulation } from '../config/runtime';

const CATEGORY_META: Record<string, { icon: typeof Brain; cls: string }> = {
  risk: { icon: ShieldAlert, cls: 'text-loss-400 bg-loss-500/12 border-loss-500/25' },
  opportunity: { icon: Zap, cls: 'text-gain-400 bg-gain-500/12 border-gain-500/25' },
  performance: { icon: TrendingUp, cls: 'text-brand-300 bg-brand-500/12 border-brand-500/25' },
  market: { icon: Globe, cls: 'text-warn-400 bg-warn-400/10 border-warn-400/25' },
};

const SENTIMENT_TONE: Record<string, 'gain' | 'loss' | 'warn' | 'slate'> = {
  positive: 'gain',
  critical: 'loss',
  warning: 'warn',
  neutral: 'slate',
};

const TOGGLE_DEFS: { key: keyof AiSettings; label: string; desc: string }[] = [
  { key: 'auto_trading', label: 'AI Auto-Trading', desc: 'Allow the AI control layer to request simulated ticket actions. Live execution still requires confirmation and a real bridge.' },
  { key: 'risk_guard', label: 'AI Risk Guard', desc: 'Surface risk warnings when account, position or drawdown limits are approached.' },
  { key: 'sentiment_filter', label: 'Sentiment Filter', desc: 'Use market context as an optional filter once a real market-data provider is connected.' },
  { key: 'news_pause', label: 'Red-Folder News Pause', desc: 'Prepare a pause rule for high-impact events when a real news feed is connected.' },
];

export default function AIPage() {
  const { pushToast } = useHub();
  const [insights, setInsights] = useState<AiInsight[] | null>(null);
  const [settings, setSettings] = useState<AiSettings | null>(null);
  const [generating, setGenerating] = useState(false);
  const [scanPulse, setScanPulse] = useState(0);

  const load = () => {
    aiControlService.get()
      .then((d) => { setInsights(d.insights); setSettings(d.settings); })
      .catch(() => pushToast('error', 'AI feed unavailable', 'Could not load the intelligence feed.'));
  };

  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const id = window.setInterval(() => setScanPulse((p) => p + 1), 2400);
    return () => window.clearInterval(id);
  }, []);

  const generate = async () => {
    setGenerating(true);
    try {
      const result = await aiControlService.generate();
      setInsights(result.insights);
      setSettings(result.settings);
      pushToast('success', 'Fresh analysis published', result.insights[0]?.title || 'Analysis updated.');
    } catch (e) {
      pushToast('error', 'Analysis failed', e instanceof Error ? e.message : undefined);
    } finally {
      setGenerating(false);
    }
  };

  const dismiss = async (id: number) => {
    setInsights((prev) => (prev || []).filter((i) => i.id !== id));
    try { await aiControlService.remove(id); } catch { /* visual removal already applied */ }
  };

  const updateSetting = async (key: keyof AiSettings, value: boolean) => {
    if (!settings) return;
    const previous = settings;
    const next = { ...settings, [key]: value };
    setSettings(next);
    try {
      await aiControlService.saveSettings(next);
      pushToast('info', `${TOGGLE_DEFS.find((t) => t.key === key)?.label} ${value ? 'enabled' : 'disabled'}`);
    } catch {
      setSettings(previous);
      pushToast('error', 'Persist failed', 'Reverting the toggle.');
    }
  };

  return (
    <div>
      <PageHeader
        title="AI Intelligence"
        sub="Rule-based MT5 Hub insights now; designed for a real AI/control service later"
        actions={
          <button className="btn-primary" onClick={generate} disabled={generating}>
            {generating ? <Spinner size={15} /> : <Sparkles size={15} />}
            {generating ? 'Scanning book\u2026' : 'Generate Fresh Analysis'}
          </button>
        }
      />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {/* engine card */}
        <Panel className="p-6 xl:row-span-2 h-fit xl:sticky xl:top-24">
          <div className="flex items-center gap-3">
            <span className="relative grid h-12 w-12 place-items-center rounded-2xl bg-brand-600/20 border border-brand-500/40 text-brand-300">
              <Brain size={22} />
              <motion.span
                key={scanPulse}
                className="absolute inset-0 rounded-2xl border border-brand-400/50"
                initial={{ opacity: 0.7, scale: 1 }}
                animate={{ opacity: 0, scale: 1.45 }}
                transition={{ duration: 1.6, ease: 'easeOut' }}
              />
            </span>
            <div>
              <p className="text-[15px] font-extrabold text-white tracking-tight">MT5 AI CONTROL</p>
              <p className="mono text-[10px] text-slate-500">simulation insight engine &middot; no model execution claims</p>
            </div>
            <Badge tone={isSimulation ? 'warn' : 'gain'}>{isSimulation ? 'Simulation' : 'Online'}</Badge>
          </div>

          <div className="mt-5 grid grid-cols-3 gap-2.5 text-center">
            <div className="rounded-xl bg-black/25 border border-white/[0.06] p-2.5">
              <p className="mono text-lg font-extrabold text-white">{(insights?.length ?? 0) * 1}</p>
              <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold mt-0.5">Insights</p>
            </div>
            <div className="rounded-xl bg-black/25 border border-white/[0.06] p-2.5">
              <p className="mono text-lg font-extrabold text-white">
                {insights && insights.length ? Math.round(insights.reduce((s, i) => s + i.confidence, 0) / insights.length) : 0}%
              </p>
              <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold mt-0.5">Avg conf</p>
            </div>
            <div className="rounded-xl bg-black/25 border border-white/[0.06] p-2.5">
              <p className="mono text-lg font-extrabold text-gain-400">{scanPulse}</p>
              <p className="text-[9px] uppercase tracking-widest text-slate-600 font-semibold mt-0.5">Scan pulse</p>
            </div>
          </div>

          <p className="mt-4 flex items-center gap-2 text-[11px] text-slate-500">
            <Activity size={12} className="text-gain-400" />
            {isSimulation ? 'Analyzing the standalone simulated account, bot and position state.' : 'Analyzing connected MT5 account, bot and position state.'}
          </p>

          <div className="mt-5 pt-5 border-t border-white/[0.07] space-y-4">
            {TOGGLE_DEFS.map((t) => (
              <div key={t.key} className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[13px] font-semibold text-slate-200">{t.label}</p>
                  <p className="text-[11px] text-slate-500 leading-snug mt-0.5">{t.desc}</p>
                </div>
                <Toggle on={settings ? settings[t.key] : false} onChange={(v) => updateSetting(t.key, v)} disabled={!settings} />
              </div>
            ))}
          </div>
        </Panel>

        {/* insights feed */}
        <div className="xl:col-span-2 space-y-3">
          {insights === null ? (
            <>
              {Array.from({ length: 4 }).map((_, i) => (
                <Skel key={i} className="h-32" />
              ))}
            </>
          ) : insights.length === 0 ? (
            <Panel>
              <div className="py-14 text-center">
                <Sparkles size={26} className="mx-auto text-brand-300 mb-3" />
                <p className="text-sm text-slate-400">No insights yet - generate the first simulation scan.</p>
              </div>
            </Panel>
          ) : (
            insights.map((i) => {
              const meta = CATEGORY_META[i.category] || CATEGORY_META.market;
              const Icon = meta.icon;
              return (
                <motion.div key={i.id} layout initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
                  <Panel hover className="p-5">
                    <div className="flex items-start gap-3.5">
                      <span className={`shrink-0 grid h-10 w-10 place-items-center rounded-xl border ${meta.cls}`}>
                        <Icon size={17} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-[14px] font-bold text-white">{i.title}</p>
                          <Badge tone={SENTIMENT_TONE[i.sentiment] || 'slate'}>{i.sentiment}</Badge>
                        </div>
                        <p className="mt-1.5 text-[13px] leading-relaxed text-slate-400">{i.body}</p>
                        <div className="mt-3 flex items-center gap-3">
                          <span className="text-[10px] uppercase tracking-widest text-slate-600 font-semibold">Confidence</span>
                          <div className="w-32">
                            <Progress value={i.confidence} tone={i.confidence >= 80 ? 'gain' : i.confidence >= 65 ? 'brand' : 'warn'} />
                          </div>
                          <span className="mono text-[11px] font-bold text-slate-300">{i.confidence}%</span>
                          <span className="text-[10px] text-slate-600 ml-auto">{timeAgo(i.created_at)}</span>
                        </div>
                      </div>
                      <button className="btn-icon !p-1.5" title="Dismiss" onClick={() => dismiss(i.id)}>
                        <X size={14} />
                      </button>
                    </div>
                  </Panel>
                </motion.div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
