// ═══════════════════════════════════════════════════════════════
// SAHOOL — fieldsetup/StepShell.tsx
// قشرة بطاقة موحّدة على طراز Climate FieldView لكلّ خطوة في المعالج:
//   عنوان + مؤشّر تقدّم (نقاط) + محتوى + أزرار (رجوع / تخطّي / التالي).
// التصميم يطابق نظام التصميم القائم (slate-900/emerald، RTL عربيّ).
// ═══════════════════════════════════════════════════════════════
import { ChevronLeft, ChevronRight, SkipForward, Loader2, AlertCircle } from 'lucide-react';

interface Props {
  title: string;
  subtitle?: string;
  icon: React.ReactNode;
  stepIndex: number;
  stepTotal: number;
  optional?: boolean;
  canGoBack: boolean;
  onBack: () => void;
  onSkip?: () => void;       // يظهر فقط للخطوات الاختياريّة
  onNext: () => void;
  nextLabel?: string;
  saving?: boolean;
  error?: string;
  children: React.ReactNode;
}

export default function StepShell({
  title, subtitle, icon, stepIndex, stepTotal, optional,
  canGoBack, onBack, onSkip, onNext, nextLabel, saving, error, children,
}: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.7)' }}>
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl shadow-2xl"
        style={{ background: '#1e293b', border: '1px solid #334155' }}>

        {/* Header + مؤشّر التقدّم */}
        <div className="sticky top-0 z-10 px-5 py-3.5 border-b"
          style={{ background: '#1e293b', borderColor: '#334155' }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-emerald-400">{icon}</span>
              <div>
                <h2 className="font-bold text-slate-100 text-sm">{title}</h2>
                {subtitle && <p className="text-[11px] text-slate-400">{subtitle}</p>}
              </div>
            </div>
            <span className="text-[11px] text-slate-400">
              الخطوة {stepIndex + 1} من {stepTotal}
              {optional && <span className="text-amber-400 mr-1">· اختياريّة</span>}
            </span>
          </div>
          {/* نقاط التقدّم */}
          <div className="flex items-center gap-1.5 mt-2.5" dir="rtl">
            {Array.from({ length: stepTotal }).map((_, i) => (
              <span key={i} className="h-1.5 rounded-full transition-all"
                style={{
                  flex: 1,
                  background: i < stepIndex ? '#16a34a' : i === stepIndex ? '#34d399' : '#334155',
                }} />
            ))}
          </div>
        </div>

        {/* المحتوى */}
        <div className="p-5 space-y-4" dir="rtl">
          {children}

          {error && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm"
              style={{ background: '#1a000022', border: '1px solid #dc262633', color: '#f87171' }}>
              <AlertCircle className="w-4 h-4" /> {error}
            </div>
          )}

          {/* أزرار التنقّل */}
          <div className="flex items-center justify-between gap-2 pt-3 border-t" style={{ borderColor: '#334155' }}>
            <button onClick={onBack} disabled={!canGoBack || saving}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border text-slate-400 hover:text-slate-200 disabled:opacity-30"
              style={{ borderColor: '#334155' }}>
              <ChevronRight className="w-4 h-4" /> رجوع
            </button>
            <div className="flex items-center gap-2">
              {optional && onSkip && (
                <button onClick={onSkip} disabled={saving}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border text-slate-400 hover:text-slate-200 disabled:opacity-50"
                  style={{ borderColor: '#334155' }}>
                  <SkipForward className="w-4 h-4" /> تخطّي
                </button>
              )}
              <button onClick={onNext} disabled={saving}
                className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white"
                style={{ background: saving ? '#15803d' : '#16a34a' }}>
                {saving
                  ? <><Loader2 className="w-4 h-4 animate-spin" /> جارٍ الحفظ…</>
                  : <>{nextLabel || 'التالي'} <ChevronLeft className="w-4 h-4" /></>}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
