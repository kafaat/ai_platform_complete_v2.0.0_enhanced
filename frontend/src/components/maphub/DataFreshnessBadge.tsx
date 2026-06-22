// ═══════════════════════════════════════════════════════════════
// DataFreshnessBadge — تحذير عدم تطابق توقيت بيانات الطبقة/المشهد (FieldView)
// ───────────────────────────────────────────────────────────────
// يقارن «تاريخ مشهد الطبقة المعروضة» (response.date من raster-service) بـ«التاريخ
// المختار للعرض» (الشريط الزمنيّ)، ويعرض:
//   • mismatch ⇒ شريط تحذير RTL واضح («عدم تطابق توقيت البيانات…»).
//   • match    ⇒ شارة حداثة محايدة («بيانات الطبقة محدّثة لهذا المشهد»).
//   • unknown  ⇒ لا شيء (لا تاريخ طبقة، أو العرض على «الأحدث») — لا تلفيق.
//
// صدق المصدر: المقارنة الكاملة (scene_id/field_revision) تنتظر تسطيح الواجهة
// الخلفيّة لـ`geometry_metadata(...)` على استجابات الراستر — انظر sceneFreshness.ts
// (SceneProvenance + compareSceneProvenance). حتى ذلك الحين نقارن بالتاريخ الصادق.
import { AlertTriangle, Clock } from 'lucide-react';
import { compareSceneFreshness } from '../../lib/sceneFreshness';
import { fmtDateAr } from '../../lib/dates';

export interface DataFreshnessBadgeProps {
  // تاريخ المشهد الذي اشتُقّت منه الطبقة المعروضة (response.date من الراستر).
  layerDate?: string | null;
  // التاريخ الذي اختاره المستخدم للعرض (الشريط الزمنيّ)؛ 'latest'/'' ⇒ لا مقارنة.
  displayDate?: string | null;
  // اسم المؤشّر للعرض (NDVI/NDMI…) — سياق للمستخدم.
  indexLabel?: string;
}

export default function DataFreshnessBadge({
  layerDate,
  displayDate,
  indexLabel,
}: DataFreshnessBadgeProps) {
  const result = compareSceneFreshness(layerDate, displayDate);

  // unknown ⇒ لا نعرض شيئاً (لا تاريخ طبقة معروف، أو العرض «الأحدث») — لا تلفيق.
  if (result.level === 'unknown') return null;

  const idx = indexLabel ? `${indexLabel} · ` : '';

  if (result.level === 'mismatch') {
    return (
      <div
        dir="rtl"
        role="alert"
        aria-live="assertive"
        className="flex items-start gap-2 text-[11px] px-3 py-2 rounded-lg border"
        style={{ background: '#3a2414', borderColor: '#8a5a1a', color: '#f5c66b' }}
      >
        <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" aria-hidden="true" />
        <span>
          <strong className="font-semibold">عدم تطابق توقيت البيانات</strong>
          {' — '}
          {idx}الطبقة مُشتقّة من مشهد/مراجعة أقدم
          {result.layerDate && (
            <>
              {' '}
              (مشهد الطبقة: {fmtDateAr(result.layerDate)} · العرض المطلوب:{' '}
              {fmtDateAr(result.displayDate)})
            </>
          )}
          . تحقّق قبل الاعتماد عليها.
        </span>
      </div>
    );
  }

  // match ⇒ شارة حداثة محايدة (تطمئن أنّ الطبقة تطابق المشهد المختار).
  return (
    <div
      dir="rtl"
      role="status"
      aria-live="polite"
      className="flex items-center gap-2 text-[11px] px-3 py-2 rounded-lg border"
      style={{ background: '#13301f', borderColor: '#2d6a3e', color: '#9fe6b4' }}
    >
      <Clock className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
      <span>
        {idx}بيانات الطبقة محدّثة لهذا المشهد
        {result.layerDate && <> · {fmtDateAr(result.layerDate)}</>}
      </span>
    </div>
  );
}
