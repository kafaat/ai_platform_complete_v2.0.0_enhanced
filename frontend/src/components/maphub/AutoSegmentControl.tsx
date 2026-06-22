// ═══════════════════════════════════════════════════════════════
// SAHOOL — AutoSegmentControl.tsx
// أزرار التقطيع المُساعَد (تلقائيّ / هجين) بجوار الرسم اليدويّ.
//   ✅ «تلقائيّ» / «هجين» → يطلبان تقطيع حدّ الحقل من خدمة التقطيع المُوكَّلة
//   ✅ نتيجة → مضلّع مُقترَح يُحمَّل في طبقة الرسم القابلة للتحرير (يؤكّده المستخدم)
//   ✅ صدق صارم: 503 model_not_configured ⇒ رسالة صريحة «استخدم الرسم اليدويّ»
//      (لا مضلّع مُفبرَك). 404 (غير منشورة) ⇒ «غير متاح» بلطف.
//
// مكوّن عرض صرف: يستقبل onSegment(mode) ويعرض حالة التحميل/الرسالة الممرَّرة.
// منطق الطلب وتحميل الناتج في طبقة الرسم يبقيان في AddFieldWithMap (يملك الخريطة).
// ═══════════════════════════════════════════════════════════════
import { Sparkles, Wand2, Loader2, AlertCircle, Info } from 'lucide-react';
import type { SegmentationMode } from '../../services/api';

// نبرة الرسالة المعروضة تحت الأزرار — تحكم لونها ورمزها (صدق بصريّ):
//   info    → اقتراح مُحمَّل بنجاح أو إرشاد محايد.
//   warning → نموذج غير مُهيَّأ / الخدمة غير متاحة (لا تلفيق — أبقِ الرسم اليدويّ).
//   error   → خطأ فعليّ (شبكة/تحقّق) يُعرَض نصّه.
export type SegmentNoticeTone = 'info' | 'warning' | 'error';

export interface SegmentNotice {
  tone: SegmentNoticeTone;
  text: string;
}

interface Props {
  onSegment: (mode: SegmentationMode) => void;
  loading:   boolean;
  // الوضع قيد التحميل حاليّاً (لإظهار المؤشّر على الزرّ الصحيح فقط).
  pendingMode?: SegmentationMode | null;
  notice?:   SegmentNotice | null;
  disabled?: boolean;
}

const TONE_STYLE: Record<SegmentNoticeTone, { bg: string; border: string; color: string }> = {
  info:    { bg: '#0b2538', border: '#0ea5e944', color: '#7dd3fc' },
  warning: { bg: '#2a1f05', border: '#f59e0b44', color: '#fbbf24' },
  error:   { bg: '#1a0000', border: '#dc262633', color: '#f87171' },
};

export default function AutoSegmentControl({
  onSegment, loading, pendingMode = null, notice = null, disabled = false,
}: Props) {
  const busy = loading || disabled;
  const tone = notice ? TONE_STYLE[notice.tone] : null;
  const NoticeIcon = notice?.tone === 'info' ? Info : AlertCircle;

  return (
    <div className="space-y-2" dir="rtl">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs" style={{ color: '#94a3b8' }}>
          تقطيع مُساعَد للحدّ:
        </span>
        <button
          type="button"
          onClick={() => onSegment('auto')}
          disabled={busy}
          title="اقتراح حدّ الحقل آليّاً من المشهد (يُحمَّل للتعديل قبل الحفظ)"
          className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold text-white disabled:opacity-60"
          style={{ background: '#0ea5e9' }}>
          {loading && pendingMode === 'auto'
            ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
            : <Sparkles className="w-3.5 h-3.5" />}
          تلقائيّ
        </button>
        <button
          type="button"
          onClick={() => onSegment('hybrid')}
          disabled={busy}
          title="اقتراح هجين (نموذج + مركز الخريطة كتلميح) — يُحمَّل للتعديل قبل الحفظ"
          className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold text-white disabled:opacity-60"
          style={{ background: '#7c3aed' }}>
          {loading && pendingMode === 'hybrid'
            ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
            : <Wand2 className="w-3.5 h-3.5" />}
          هجين
        </button>
        <span className="text-[11px]" style={{ color: '#64748b' }}>
          (اقتراح يُراجَع ويُعدَّل يدويّاً — لا يُعتمَد بلا تأكيد)
        </span>
      </div>

      {notice && tone && (
        <div
          className="flex items-start gap-2 px-3 py-2 rounded-lg text-xs"
          style={{ background: tone.bg, border: `1px solid ${tone.border}`, color: tone.color }}>
          <NoticeIcon className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{notice.text}</span>
        </div>
      )}
    </div>
  );
}
