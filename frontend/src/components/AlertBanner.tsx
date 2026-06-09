import { useState } from 'react';
import { AlertTriangle, AlertOctagon, Info, X } from 'lucide-react';

interface Alert {
  id: string;
  severity?: 'critical' | 'high' | 'medium' | 'low';
  title?: string;
  message?: string;
  [key: string]: unknown;
}

interface AlertBannerProps {
  alerts: Alert[];
}

const SEV_CFG = {
  critical: { icon: AlertOctagon, color: 'text-red-400',    bg: 'bg-red-950/60',    border: 'border-red-800' },
  high:     { icon: AlertTriangle, color: 'text-orange-400', bg: 'bg-orange-950/60', border: 'border-orange-800' },
  medium:   { icon: AlertTriangle, color: 'text-amber-400',  bg: 'bg-amber-950/60',  border: 'border-amber-800' },
  low:      { icon: Info,          color: 'text-sky-400',    bg: 'bg-sky-950/60',    border: 'border-sky-800' },
};

export function AlertBanner({ alerts }: AlertBannerProps) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const visible = alerts.filter(a => !dismissed.has(a.id));
  if (!visible.length) return null;

  return (
    <div className="space-y-2" dir="rtl">
      {visible.slice(0, 3).map(alert => {
        const sev = alert.severity ?? 'low';
        const cfg = SEV_CFG[sev as keyof typeof SEV_CFG] ?? SEV_CFG.low;
        const Icon = cfg.icon;
        return (
          <div
            key={alert.id}
            className={`flex items-start gap-3 px-4 py-3 rounded-lg border ${cfg.bg} ${cfg.border}`}
          >
            <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${cfg.color}`} />
            <div className="flex-1 min-w-0">
              {alert.title && (
                <p className={`text-sm font-semibold ${cfg.color}`}>{alert.title}</p>
              )}
              {alert.message && (
                <p className="text-xs text-slate-400 mt-0.5 truncate">{alert.message}</p>
              )}
            </div>
            <button
              onClick={() => setDismissed(prev => new Set([...prev, alert.id]))}
              className="shrink-0 text-slate-500 hover:text-slate-300 transition-colors"
              aria-label="إغلاق"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        );
      })}
      {visible.length > 3 && (
        <p className="text-xs text-slate-500 text-center">
          +{visible.length - 3} تنبيهات أخرى
        </p>
      )}
    </div>
  );
}
