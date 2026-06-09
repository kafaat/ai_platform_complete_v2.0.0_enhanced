// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — components/ToastContainer.tsx
// عرض إشعارات Toast من wsService
// ═══════════════════════════════════════════════════════════════
import { useState, useEffect } from 'react';
import { toastStore, type ToastItem } from '../services/websocket';
import { X, CheckCircle, AlertTriangle, Info, AlertOctagon } from 'lucide-react';

const ICONS = {
  success: <CheckCircle  className="w-4 h-4 text-emerald-400" />,
  warning: <AlertTriangle className="w-4 h-4 text-amber-400" />,
  error:   <AlertOctagon className="w-4 h-4 text-red-400" />,
  info:    <Info          className="w-4 h-4 text-blue-400" />,
};
const COLORS = {
  success: { bg:'#1e3a1e', border:'#16a34a44' },
  warning: { bg:'#2a1a00', border:'#f59e0b44' },
  error:   { bg:'#1a0000', border:'#dc262644' },
  info:    { bg:'#001a2a', border:'#38bdf844' },
};

export default function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  useEffect(() => toastStore.subscribe(setToasts), []);
  if (!toasts.length) return null;
  return (
    <div className="fixed top-4 left-4 z-[9999] space-y-2 max-w-sm" dir="rtl">
      {toasts.map(t => (
        <div key={t.id} className="rounded-xl px-4 py-3 shadow-xl flex items-start gap-3 animate-slide-in"
          style={{ background: COLORS[t.type].bg, border:`1px solid ${COLORS[t.type].border}` }}>
          <div className="mt-0.5 flex-shrink-0">{ICONS[t.type]}</div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-slate-100">{t.title}</p>
            {t.message && <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{t.message}</p>}
          </div>
          <button onClick={() => toastStore.remove(t.id)} className="text-slate-500 hover:text-slate-300 flex-shrink-0">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
