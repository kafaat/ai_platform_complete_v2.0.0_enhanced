// ═══════════════════════════════════════════════════════════════
// StateViews — حالات الواجهة الموحّدة (تحميل / هيكل عظمي / فراغ / خطأ)
// تستبدل الـspinner والـpulse الـad-hoc المكرّرة في الصفحات. عرض فقط (بلا منطق
// بيانات). RTL + a11y: role/aria-live/aria-busy + نصّ بديل للقارئ الشاشي.
// الألوان من نظام التصميم الموحّد (tokens sahool/status) لا inline.
// ═══════════════════════════════════════════════════════════════
import type { ReactNode } from 'react';
import { Loader2, Inbox, AlertTriangle, RefreshCw } from 'lucide-react';

export function LoadingState({ message = 'جارٍ التحميل…' }: { message?: string }) {
  return (
    <div
      className="flex items-center justify-center h-64"
      dir="rtl"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="text-center">
        <Loader2 className="w-8 h-8 text-sahool-green animate-spin mx-auto mb-3" aria-hidden="true" />
        <p className="text-sahool-muted text-sm">{message}</p>
      </div>
    </div>
  );
}

export function SkeletonGrid({
  count = 6,
  className = 'grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3',
  itemClassName = 'rounded-xl h-28',
}: {
  count?: number;
  className?: string;
  itemClassName?: string;
}) {
  return (
    <div className={className} role="status" aria-live="polite" aria-busy="true">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={`${itemClassName} animate-pulse border border-sahool-border bg-sahool-surface/40`}
          aria-hidden="true"
        />
      ))}
      <span className="sr-only">جارٍ تحميل المحتوى…</span>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  hint,
}: {
  icon?: ReactNode;
  title: string;
  hint?: string;
}) {
  return (
    <div className="text-center py-10 text-sahool-muted" dir="rtl" role="status">
      <div className="flex justify-center mb-2" aria-hidden="true">
        {icon ?? <Inbox className="w-8 h-8" />}
      </div>
      <p className="text-sm font-medium text-sahool-text">{title}</p>
      {hint && <p className="text-xs mt-1">{hint}</p>}
    </div>
  );
}

export function ErrorState({
  title = 'تعذّر تحميل البيانات',
  detail,
  onRetry,
}: {
  title?: string;
  detail?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="text-center py-10" dir="rtl" role="alert" aria-live="assertive">
      <AlertTriangle className="w-8 h-8 text-status-critical mx-auto mb-2" aria-hidden="true" />
      <p className="text-sm font-medium text-sahool-text">{title}</p>
      {detail && <p className="text-xs text-sahool-muted mt-1">{detail}</p>}
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-sahool-border text-sm text-sahool-text hover:border-sahool-green focus:outline-none focus:ring-2 focus:ring-sahool-border-focus"
        >
          <RefreshCw className="w-4 h-4" aria-hidden="true" />
          إعادة المحاولة
        </button>
      )}
    </div>
  );
}
