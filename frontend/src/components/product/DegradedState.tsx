import { AlertTriangle, RefreshCw } from 'lucide-react';

export function DegradedState({
  title = 'الخدمة غير متاحة بالكامل الآن',
  detail = 'يمكنك متابعة العمل بالبيانات المتاحة أو آخر نسخة محفوظة.',
  availableActions = [],
  onRetry,
}: {
  title?: string;
  detail?: string;
  availableActions?: string[];
  onRetry?: () => void;
}) {
  return (
    <div
      className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 text-right"
      dir="rtl"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
        <div className="space-y-2">
          <p className="text-sm font-semibold text-sahool-text">{title}</p>
          <p className="text-xs text-sahool-muted">{detail}</p>
          {availableActions.length > 0 && (
            <ul className="text-xs text-sahool-muted list-disc pr-4 space-y-1">
              {availableActions.map((action) => (
                <li key={action}>{action}</li>
              ))}
            </ul>
          )}
          {onRetry && (
            <button
              onClick={onRetry}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-sahool-border text-xs text-sahool-text hover:border-sahool-green focus:outline-none focus:ring-2 focus:ring-sahool-border-focus"
            >
              <RefreshCw className="w-4 h-4" aria-hidden="true" />
              إعادة المحاولة
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
