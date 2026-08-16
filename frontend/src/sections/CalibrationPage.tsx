// ═══════════════════════════════════════════════════════════════
// SAHOOL — CalibrationPage (حالة المعايرة الإقليميّة، يستهلك GET /api/v1/calibration)
// لوحة قراءة فقط: لكلّ إقليم يمنيّ، هل ثوابته الأغرونوميّة مُتحقَّق منها ميدانيّاً
// أم ما تزال افتراضات FAO عامّة؟ فيرى المستخدم بالضبط أين تنقص بيانات المعايرة
// الحقيقيّة. صدق: الأقاليم غير المُتحقَّق منها (validated=false) ترث الافتراضات
// العامّة وتحتاج بيانات حقليّة — بانر كهرمانيّ صريح، لا أرقام قاطعة مُلفَّقة.
// ═══════════════════════════════════════════════════════════════
import { Activity, AlertTriangle, RefreshCw, CheckCircle2, XCircle } from 'lucide-react';
import { useCalibration } from '../hooks/useApi';
import type { CalibrationProfile } from '../services/api';
import { ErrorState, LoadingState } from '../components/StateViews';

// شارة مستوى الدليل — ألوان: مُتحقَّق ميدانيّاً أخضر، ميدانيّ أوّليّ كهرمانيّ،
// رأي خبير سماويّ، لا شيء أردوازيّ/أحمر (يطابق نصّ المهمّة).
const EVIDENCE_AR: Record<string, string> = {
  field_verified:    'مُتحقَّق ميدانيّاً',
  field_preliminary: 'ميدانيّ أوّليّ',
  expert_opinion:    'رأي خبير',
  none:              'لا دليل',
};
const evidenceStyle = (level: string): { bg: string; color: string } => {
  switch (level) {
    case 'field_verified':    return { bg: '#0c2a1a', color: '#4ade80' };
    case 'field_preliminary': return { bg: '#2a1a00', color: '#fbbf24' };
    case 'expert_opinion':    return { bg: '#0a1f2e', color: '#38bdf8' };
    case 'none':              return { bg: '#2a0d0d', color: '#f87171' };
    default:                  return { bg: '#1e293b', color: '#94a3b8' };
  }
};

// صفّ ملفّ واحد في الجدول (إقليم أو الملفّ العامّ المُعلَّم isGeneric).
function ProfileRow({ p, isGeneric }: { p: CalibrationProfile; isGeneric?: boolean }) {
  const ev = evidenceStyle(p.evidence_level);
  return (
    <tr
      className="text-slate-300"
      style={{ borderBottom: '1px solid #25303f', background: isGeneric ? '#161616' : undefined }}
    >
      <td className="px-3 py-1.5 font-medium text-slate-100">
        {p.region_ar}
        {isGeneric && (
          <span className="mr-2 text-[10px] px-1.5 py-0.5 rounded text-slate-400" style={{ background: '#0f1117' }}>
            عامّ
          </span>
        )}
      </td>
      <td className="px-3 py-1.5">
        <span
          className="text-[11px] px-2 py-0.5 rounded-full font-semibold"
          style={{ background: ev.bg, color: ev.color }}
        >
          {EVIDENCE_AR[p.evidence_level] ?? p.evidence_level}
        </span>
      </td>
      <td className="px-3 py-1.5 text-center">
        {p.validated
          ? <CheckCircle2 className="w-4 h-4 text-emerald-400 inline" />
          : <XCircle className="w-4 h-4 text-slate-500 inline" />}
      </td>
      <td className="px-3 py-1.5">{p.sample_count}</td>
      <td className="px-3 py-1.5">{p.raw_fraction.toFixed(2)}</td>
      <td className="px-3 py-1.5">{p.root_depth_m.toFixed(2)} م</td>
      <td className="px-3 py-1.5">{p.kc_dyn_min.toFixed(2)}–{p.kc_dyn_max.toFixed(2)}</td>
      <td className="px-3 py-1.5 text-xs text-slate-400">{p.source_ar}</td>
    </tr>
  );
}

export default function CalibrationPage() {
  const { data, isLoading, isError, refetch, isFetching } = useCalibration();

  // الأقاليم غير المُتحقَّق منها — ترث الافتراضات العامّة وتحتاج بيانات حقليّة.
  const needFieldData = (data?.regions ?? []).filter(r => !r.validated);

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-emerald-400" />
          <h2 className="text-xl font-bold text-slate-100">حالة المعايرة الإقليميّة</h2>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm text-slate-300 disabled:opacity-60"
          style={{ background: '#1e293b', border: '1px solid #334155' }}
        >
          <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          تحديث
        </button>
      </div>
      <p className="text-sm text-slate-400">
        لكلّ إقليم يمنيّ: هل ثوابته الأغرونوميّة <span className="text-emerald-300">مُتحقَّق منها ميدانيّاً</span> أم ما تزال
        <span className="text-amber-300"> افتراضات FAO عامّة</span>؟ تُظهر هذه اللوحة بالضبط أين تنقص بيانات المعايرة الحقيقيّة.
      </p>

      {isLoading && <LoadingState message="جارٍ جلب حالة المعايرة…" />}
      {isError && <ErrorState title="تعذّر جلب حالة المعايرة" onRetry={() => refetch()} />}

      {data && (
        <div className="space-y-4">
          {/* Header strip: validated_count / total + note */}
          <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
            <div className="text-center px-3 flex-shrink-0">
              <div className="text-2xl font-bold text-slate-100">
                {data.validated_count}<span className="text-slate-500 text-base"> / {data.regions.length}</span>
              </div>
              <div className="text-[11px] text-slate-400 mt-0.5">أقاليم مُعايَرة ميدانيّاً</div>
            </div>
            <div className="flex-1 text-sm text-slate-300 self-center">{data.note_ar}</div>
          </div>

          {/* Honesty banner: regions needing field data */}
          {needFieldData.length > 0 && (
            <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
              <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div className="space-y-1">
                <div className="text-sm font-semibold text-amber-200">
                  🟡 {needFieldData.length} إقليم ترث الافتراضات العامّة (FAO) وتحتاج بيانات حقليّة
                </div>
                <div className="text-[11px] text-amber-300/80">
                  الأقاليم: {needFieldData.map(r => r.region_ar).join('، ')} — قيمها تقديريّة غير مُعايَرة حتى تُجمَع قياسات ميدانيّة.
                </div>
                {needFieldData.flatMap(r =>
                  r.notes_ar.map((n, i) => (
                    <div key={`${r.region}-${i}`} className="text-[11px] text-slate-400">• {r.region_ar}: {n}</div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* إرشاد: غرض اللوحة وكيف تتحدّث القيم عند ربط نتائج ميدانيّة */}
          <p className="text-[12px] text-slate-400 leading-relaxed">
            تعرض هذه اللوحة أين تنقص المعايرة الميدانيّة الحقيقيّة لكلّ إقليم. تتحدّث القيم
            (مستوى الدليل وعدد العيّنات والثوابت) عند ربط نتائج outcome/measure عبر
            <code dir="ltr" className="text-slate-300">POST /api/v1/calibration/&#123;region&#125;/evidence</code>.
          </p>

          {/* Regions table (+ generic row) */}
          <div className="rounded-xl border overflow-hidden" style={{ background: '#1e293b', borderColor: '#334155' }}>
            <div className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-slate-100" style={{ borderBottom: '1px solid #334155' }}>
              <Activity className="w-4 h-4 text-emerald-400" /> ثوابت الأقاليم
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[11px] text-slate-400" style={{ borderBottom: '1px solid #334155' }}>
                    <th className="px-3 py-2 text-right font-medium">الإقليم</th>
                    <th className="px-3 py-2 text-right font-medium">مستوى الدليل</th>
                    <th className="px-3 py-2 text-center font-medium">مُعايَر</th>
                    <th className="px-3 py-2 text-right font-medium">العيّنات</th>
                    <th className="px-3 py-2 text-right font-medium">p (RAW)</th>
                    <th className="px-3 py-2 text-right font-medium">عمق الجذور</th>
                    <th className="px-3 py-2 text-right font-medium">Kc (أدنى–أقصى)</th>
                    <th className="px-3 py-2 text-right font-medium">المصدر</th>
                  </tr>
                </thead>
                <tbody>
                  {data.regions.map(r => <ProfileRow key={r.region} p={r} />)}
                  {/* الملفّ العامّ (FAO) — مرجع الافتراضات التي ترثها الأقاليم غير المُعايَرة */}
                  <ProfileRow p={data.generic} isGeneric />
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
