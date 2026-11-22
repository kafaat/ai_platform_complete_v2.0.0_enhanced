// ═══════════════════════════════════════════════════════════════
// SAHOOL — NlGisPage (استعلام GIS باللغة الطبيعيّة)
// يستهلك POST /api/v1/nl-gis/query: يصنّف استعلاماً عربيّاً حرّاً إلى نيّة مغلقة
// (تنبيه/انخفاض NDVI/فجوة ريّ) ويُعيد معاينة قراءة-فقط للحقول المطابقة من بيانات
// المستأجِر — لا تنفيذ ولا تعديل (read_only). شريط التفسير يُظهر النيّة المكتشَفة
// والثقة والشقوق (slots) لشفافيّة الفهم. صدق: الفراغ/الحاجة-للبيانات/عدم-الدعم
// حالات مميَّزة لا جدول فارغ مُضلِّل. العلم مُطفأً (FEATURE_NATURAL_LANGUAGE_GIS)
// ⇒ 404 ⇒ رسالة «الميزة غير مُفعَّلة» لا انهيار؛ 503 ⇒ حالة خطأ صادقة.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Search, AlertTriangle, ShieldAlert, Info, Tag } from 'lucide-react';
import { queryNlGis, asApiError } from '../services/api';
import type { NlGisQueryInput, NlGisResult } from '../services/api';
import { ErrorState } from '../components/StateViews';

const inputStyle = { background: 'rgb(var(--sahool-surface-2))', border: '1px solid rgb(var(--sahool-border))', color: 'rgb(var(--sahool-text))' } as const;

// استعلامات مثال (مطابقة للنيّات المدعومة) — نقرات تملأ الإدخال.
const EXAMPLES: string[] = [
  'اعرض الحقول التي انخفض NDVI فيها أكثر من 15%',
  'اعرض حقول القمح في الجوف التي لديها تنبيه حرارة',
  'اعرض الحقول التي لم تُروَ منذ 5 أيّام',
];

// تسمية عربيّة للنيّة المكتشَفة.
const INTENT_LABEL: Record<string, string> = {
  alert_filter:   'تصفية التنبيهات',
  ndvi_drop:      'انخفاض NDVI',
  irrigation_gap: 'فجوة الريّ',
  unsupported:    'غير مدعوم',
};

// تسمية عربيّة لمفاتيح الشقوق (slots) المعروفة — تُعرَض كشرائح.
const SLOT_LABEL: Record<string, string> = {
  crop:       'المحصول',
  region:     'المنطقة',
  alert_type: 'نوع التنبيه',
  threshold:  'العتبة',
  days:       'الأيّام',
  gov:        'المحافظة',
  severity:   'الشدّة',
};

// تسمية عربيّة لأعمدة الجدول المعروفة — غير المعروف يسقط على المفتاح الخام.
const COL_LABEL: Record<string, string> = {
  field_id:    'معرّف الحقل',
  name:        'الاسم',
  crop:        'المحصول',
  gov:         'المحافظة',
  alert_type:  'نوع التنبيه',
  severity:    'الشدّة',
  title_ar:    'العنوان',
  ndvi_latest: 'NDVI الحاليّ',
  ndvi_prev:   'NDVI السابق',
  drop_pct:    'نسبة الانخفاض',
  latest_date: 'آخر تاريخ',
  last_run_at: 'آخر ريّ',
};

const colLabel = (k: string): string => COL_LABEL[k] ?? k;
const slotLabel = (k: string): string => SLOT_LABEL[k] ?? k;

// تنسيق قيمة خليّة (بدائيّ JSON) — null ⇒ «—»، الباقي نصّاً كما هو.
const cellText = (v: string | number | boolean | null): string => {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'boolean') return v ? 'نعم' : 'لا';
  return String(v);
};

export default function NlGisPage() {
  const [query, setQuery] = useState('');
  const [res, setRes] = useState<NlGisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(false);
  const [featureOff, setFeatureOff] = useState(false);

  const runQuery = (q: string) => {
    const text = q.trim();
    if (!text) return;
    setLoading(true); setErr(false); setFeatureOff(false);
    const payload: NlGisQueryInput = { query: text };
    queryNlGis(payload)
      .then(r => setRes(r))
      .catch(e => {
        setRes(null);
        // 404 ⇒ العلم مُطفأ (الميزة غير مُفعَّلة) — رسالة ودودة لا حالة خطأ.
        if (asApiError(e).response?.status === 404) setFeatureOff(true);
        else setErr(true);
      })
      .finally(() => setLoading(false));
  };

  const onSearch = () => runQuery(query);
  const onExample = (q: string) => { setQuery(q); runQuery(q); };

  // أعمدة الجدول الديناميكيّة من مفاتيح العناصر (اتّحاد المفاتيح عبر كلّ العناصر
  // حفاظاً على التغاير لو اختلفت). الترتيب: حسب أوّل ظهور.
  const columns: string[] = (() => {
    if (!res || res.items.length === 0) return [];
    const seen: string[] = [];
    for (const it of res.items) {
      for (const k of Object.keys(it)) if (!seen.includes(k)) seen.push(k);
    }
    return seen;
  })();

  const slots = res?.slots ?? {};
  const slotKeys = Object.keys(slots).filter(k => slots[k] !== null && slots[k] !== undefined && slots[k] !== '');

  // الحالة الفعليّة المعروضة بعد نتيجة ناجحة.
  const isUnsupported = res?.status === 'unsupported' || res?.supported === false;
  const isNeedsData = res?.status === 'needs_data';
  // مسح ناقص (raster تعذّر لبعض الحقول أو بُتر المسح): لا يُعرَض أبداً كفراغ صادق.
  const isPartial = res?.status === 'partial' || res?.coverage?.complete === false;
  const isOkEmpty = res?.status === 'ok' && res.count === 0 && !isPartial;
  const showTable = !!res && !isUnsupported && !isNeedsData && res.count > 0;

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <Search className="w-5 h-5 text-ops-info" />
        <h2 className="text-xl font-bold text-sahool-text">استعلام GIS باللغة الطبيعيّة</h2>
      </div>
      <p className="text-sm text-sahool-muted">
        اكتب طلبك بالعربيّة الحرّة فيُصنَّف إلى <span className="text-sahool-text">نيّة مدعومة</span>
        (تنبيه/انخفاض NDVI/فجوة ريّ) ويُعرَض معاينةً للحقول المطابقة من بياناتك.
        <span className="text-ops-warning"> قراءة فقط — لا تنفيذ ولا تعديل.</span>
      </p>

      {/* بانر قراءة فقط (بارز) */}
      <div className="rounded-xl border p-3 flex items-center gap-2" style={{ background: '#1a1400', borderColor: '#f59e0b55' }}>
        <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
        <span className="text-sm font-semibold text-amber-200">قراءة فقط — مبنيّ على بياناتك، لا تنفيذ ولا تعديل.</span>
      </div>

      {/* الإدخال + زرّ البحث */}
      <div className="rounded-xl border p-4 space-y-3" style={{ background: 'rgb(var(--sahool-surface))', borderColor: 'rgb(var(--sahool-border))' }}>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-sahool-muted">استعلامك بالعربيّة</span>
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') onSearch(); }}
            placeholder="مثال: اعرض حقول القمح في الجوف التي لديها تنبيه حرارة"
            aria-label="استعلام GIS باللغة الطبيعيّة"
            className="px-3 py-2 rounded-lg text-sm" style={inputStyle}
          />
        </label>

        {/* شرائح أمثلة قابلة للنقر */}
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex, i) => (
            <button key={i} onClick={() => onExample(ex)} type="button"
              className="text-[11px] px-2.5 py-1 rounded-full text-sahool-text hover:text-sky-300"
              style={inputStyle}>
              {ex}
            </button>
          ))}
        </div>

        <div className="flex justify-end">
          <button onClick={onSearch} disabled={loading || query.trim() === ''}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: '#0ea5e9' }}>
            <Search className="w-4 h-4" />
            {loading ? 'جارٍ البحث…' : 'ابحث'}
          </button>
        </div>
      </div>

      {/* الميزة غير مُفعَّلة (404 — العلم مُطفأ) */}
      {featureOff && (
        <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: 'rgb(var(--sahool-surface))', borderColor: 'rgb(var(--sahool-border))' }}>
          <ShieldAlert className="w-5 h-5 text-sahool-muted shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="text-sm font-semibold text-sahool-text">الميزة غير مُفعَّلة (FEATURE_NATURAL_LANGUAGE_GIS)</div>
            <div className="text-[12px] text-sahool-muted">
              استعلام GIS باللغة الطبيعيّة خلف علم تشغيل لم يُفعَّل بعد على الخادم. تواصل مع المسؤول لتفعيله.
            </div>
          </div>
        </div>
      )}

      {err && <ErrorState title="تعذّر تنفيذ الاستعلام" onRetry={onSearch} />}

      {res && !featureOff && (
        <div className="space-y-4">
          {/* شريط التفسير: النيّة + الثقة + الشقوق (slots) */}
          <div className="rounded-xl border p-4 space-y-3" style={{ background: 'rgb(var(--sahool-surface))', borderColor: 'rgb(var(--sahool-border))' }}>
            <div className="flex items-center gap-2 text-sm font-semibold text-sahool-text">
              <Info className="w-4 h-4 text-ops-info" /> تفسير الاستعلام
            </div>
            <div className="flex flex-wrap items-center gap-3 text-[12px]">
              <span className="text-sahool-muted">
                النيّة المكتشَفة:
                <span className="text-sahool-text font-semibold mr-1">
                  {INTENT_LABEL[res.intent] ?? res.intent}
                </span>
              </span>
              {typeof res.confidence === 'number' && (
                <span className="text-sahool-muted">
                  الثقة:
                  <span className="text-sahool-text font-semibold mr-1">{(res.confidence * 100).toFixed(0)}٪</span>
                </span>
              )}
            </div>
            {slotKeys.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {slotKeys.map(k => (
                  <span key={k}
                    className="inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-full text-sky-200"
                    style={{ background: '#0c2233', border: '1px solid #0ea5e955' }}>
                    <Tag className="w-3 h-3" />
                    {slotLabel(k)}: {cellText(slots[k])}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* عدم الدعم (intent=unsupported) — تنبيه كهرمانيّ + شرائح الأمثلة للإرشاد */}
          {isUnsupported && (
            <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                <div className="text-sm text-amber-200">
                  {res.reason_ar || 'لم أتعرّف على طلب مدعوم. جرّب أحد الأمثلة أدناه.'}
                </div>
              </div>
              <div className="flex flex-wrap gap-2 pr-8">
                {EXAMPLES.map((ex, i) => (
                  <button key={i} onClick={() => onExample(ex)} type="button"
                    className="text-[11px] px-2.5 py-1 rounded-full text-ops-warning hover:text-amber-100"
                    style={{ background: 'rgb(var(--sahool-surface-2))', border: '1px solid #f59e0b44' }}>
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* الحاجة للبيانات (needs_data) — لا جدول فارغ مُضلِّل */}
          {isNeedsData && (
            <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: 'rgb(var(--sahool-surface))', borderColor: 'rgb(var(--sahool-border))' }}>
              <Info className="w-5 h-5 text-sahool-muted shrink-0 mt-0.5" />
              <div className="text-sm text-sahool-text">
                {res.note_ar || 'المصدر غير متاح حاليّاً — لا يمكن عرض نتيجة موثوقة الآن.'}
              </div>
            </div>
          )}

          {/* نتيجة ناقصة (partial) — تحذير كهرمانيّ، لا «لا حقول تطابق» */}
          {isPartial && (
            <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
              <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
              <div className="text-sm text-amber-200">
                {res.note_ar || 'نتيجة ناقصة: لم تُقَس كلّ الحقول — الحقول غير المقيسة مجهولة.'}
              </div>
            </div>
          )}

          {/* فراغ صادق (ok مع count=0) */}
          {isOkEmpty && (
            <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: 'rgb(var(--sahool-surface))', borderColor: 'rgb(var(--sahool-border))' }}>
              <Info className="w-5 h-5 text-sahool-muted shrink-0 mt-0.5" />
              <div className="text-sm text-sahool-text">
                {res.note_ar || 'لا حقول تطابق هذا الاستعلام.'}
              </div>
            </div>
          )}

          {/* جدول النتائج (أعمدة ديناميكيّة) + العدد */}
          {showTable && (
            <div className="rounded-xl border overflow-hidden" style={{ background: 'rgb(var(--sahool-surface))', borderColor: 'rgb(var(--sahool-border))' }}>
              <div className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-sahool-text" style={{ borderBottom: '1px solid rgb(var(--sahool-border))' }}>
                <Search className="w-4 h-4 text-ops-info" /> النتائج
                <span className="text-[11px] text-sahool-muted font-normal">({res.count} حقل)</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-[11px] text-sahool-muted" style={{ borderBottom: '1px solid rgb(var(--sahool-border))' }}>
                      {columns.map(c => (
                        <th key={c} className="px-3 py-2 text-right font-medium">{colLabel(c)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {res.items.map((it, i) => (
                      <tr key={i} className="text-sahool-text" style={{ borderBottom: '1px solid rgb(var(--sahool-border))' }}>
                        {columns.map(c => (
                          <td key={c} className="px-3 py-1.5">{cellText(it[c] ?? null)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
