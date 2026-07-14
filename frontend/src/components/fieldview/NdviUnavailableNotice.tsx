// ═══════════════════════════════════════════════════════════════
// SAHOOL — إشعار «NDVI غير متاح» التشخيصيّ (عقد 424)
// ───────────────────────────────────────────────────────────────
// خدمة الغطاء real-only تفشل مُغلَقةً بـ424 حين لا مشاهدة NDVI موثّقة، وتُرفِق سبباً
// مُصنَّفاً: {code, message, action, retryable}. هذا المكوّن يُصيّر حالة فارغة **هادئة**
// (لا console.error، لا اختلاق قيمة) برسالة مفهومة لكلّ code، ويُظهر إجراءً صريحاً
// «معالجة الصور» للحالات الحتميّة (لا صور مُعالَجة) — بلا بدء backfill تلقائيّ.
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react';

export interface NdviUnavailable {
  code: string;
  message?: string;
  action?: string;
  retryable?: boolean;
}

// نسخة عربيّة لكلّ سبب (مصدر الحقيقة الخادم؛ هذا تصيير بشريّ). cta فقط للحالات القابلة
// للمعالجة يدويّاً (لا صور مُعالَجة / لا أصل موثّق) — لا للأعطال العابرة/التفويض.
const COPY: Record<string, { ar: string; cta?: string }> = {
  NO_PROCESSED_IMAGERY: {
    ar: 'لا توجد صور أقمار صناعيّة مُعالَجة لهذا الحقل بعد.',
    cta: 'معالجة الصور',
  },
  NO_VALIDATED_NDVI_ASSET: {
    ar: 'لا توجد مشاهدة NDVI موثّقة حديثة لهذا الحقل.',
    cta: 'طلب جلب الصور السابقة',
  },
  RASTER_DEPENDENCY_UNAVAILABLE: { ar: 'خدمة معالجة الصور غير متاحة مؤقّتاً؛ حاوِل لاحقاً.' },
  RASTER_AUTH_FAILURE: { ar: 'تعذّر تفويض صور هذا الحقل لمستأجِرك.' },
  RASTER_RESPONSE_INVALID: { ar: 'ردّ غير متوقّع من خدمة الصور.' },
};

/** يستخرج تفصيل 424 التشخيصيّ من خطأ axios، أو null إن لم يكن 424 معروفاً. */
export function ndviUnavailableFromError(error: unknown): NdviUnavailable | null {
  const resp = (
    error as { response?: { status?: number; data?: { detail?: NdviUnavailable | string } } }
  )?.response;
  if (!resp || resp.status !== 424) return null;
  const detail = resp.data?.detail;
  if (detail && typeof detail === 'object' && typeof detail.code === 'string') {
    return detail;
  }
  // 424 قديم بتفصيل نصّيّ (قبل العقد التشخيصيّ): عامِله كـ«لا صور مُعالَجة».
  return { code: 'NO_PROCESSED_IMAGERY', retryable: false };
}

interface Props {
  info: NdviUnavailable;
  /** يُطلق مسار المعالجة (refreshFieldImagery/analyze) — يظهر الزرّ فقط حين يُمرَّر. */
  onProcess?: () => void;
  processing?: boolean;
  className?: string;
}

export default function NdviUnavailableNotice({ info, onProcess, processing, className }: Props) {
  const copy = COPY[info.code] ?? { ar: info.message || 'مؤشّر NDVI غير متاح لهذا الحقل.' };
  // الزرّ للحالات الحتميّة القابلة للمعالجة فقط (retryable:false + cta + معالِج).
  const showCta = !!copy.cta && !!onProcess && info.retryable === false;
  return (
    <div
      role="status"
      aria-live="polite"
      className={
        className ??
        'flex flex-col items-center gap-2 rounded-lg border border-sahool-border bg-sahool-surface/40 p-4 text-center'
      }
    >
      <AlertTriangle className="w-5 h-5 text-sahool-muted" aria-hidden="true" />
      <p className="text-sm text-sahool-muted">{copy.ar}</p>
      {showCta && (
        <button
          type="button"
          onClick={onProcess}
          disabled={processing}
          className="mt-1 inline-flex items-center gap-1.5 rounded-md border border-sahool-green px-3 py-1.5 text-xs text-sahool-green hover:bg-sahool-green/10 disabled:opacity-60"
        >
          {processing ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
          )}
          {copy.cta}
        </button>
      )}
    </div>
  );
}
