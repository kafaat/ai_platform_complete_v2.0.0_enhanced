// ═══════════════════════════════════════════════════════════════
// SAHOOL — FieldDetailPanel.tsx (تفاصيل الحقل، sahool-platform v37)
// لوحة «ملء تدريجيّ» تُفتَح من إدارة الحقول: تعرض الحقل وتتيح ملء كيمياء
// التربة + المناخ الدقيق + الملكيّة، وتحفظ عبر PATCH (تحديث جزئيّ — الحقول
// المُعدَّلة فقط). حالات صادقة: تحميل/خطأ (مع إعادة)/حفظ — لا تلفيق قيم.
// ═══════════════════════════════════════════════════════════════
import { useState, useEffect } from 'react';
import { X, Check, FlaskConical, Mountain, Scroll } from 'lucide-react';
import { useFieldDetail, useUpdateField } from '../hooks/useApi';
import { apiErrorMessage, type FieldDetail, type FieldUpdatePatch } from '../services/api';
import { LoadingState, ErrorState } from './StateViews';
import { toastStore } from '../services/websocket';

// مفاتيح الحقول الرقميّة والنصّيّة المتقدّمة (تُبنى منها المدخلات والـpatch).
type NumKey =
  | 'soil_ph' | 'soil_ec' | 'soil_om' | 'soil_n' | 'soil_p' | 'soil_k'
  | 'elevation_m' | 'slope_pct' | 'annual_rainfall_mm' | 'lease_years';
type StrKey = 'aspect' | 'climate_zone' | 'owner_name' | 'registry_no';

interface FieldSpec {
  key:   NumKey | StrKey;
  label: string;
  type:  'number' | 'text';
  hint?: string;
}

const SOIL_FIELDS: FieldSpec[] = [
  { key: 'soil_ph', label: 'الحموضة pH', type: 'number', hint: '0–14' },
  { key: 'soil_ec', label: 'الملوحة EC (dS/m)', type: 'number' },
  { key: 'soil_om', label: 'المادّة العضويّة %', type: 'number' },
  { key: 'soil_n', label: 'النيتروجين N (mg/kg)', type: 'number' },
  { key: 'soil_p', label: 'الفوسفور P (mg/kg)', type: 'number' },
  { key: 'soil_k', label: 'البوتاسيوم K (mg/kg)', type: 'number' },
];
const CLIMATE_FIELDS: FieldSpec[] = [
  { key: 'elevation_m', label: 'الارتفاع (م)', type: 'number' },
  { key: 'slope_pct', label: 'الميل %', type: 'number' },
  { key: 'aspect', label: 'الجهة (شمال/جنوب…)', type: 'text' },
  { key: 'climate_zone', label: 'المنطقة المناخيّة', type: 'text' },
  { key: 'annual_rainfall_mm', label: 'الأمطار السنويّة (مم)', type: 'number' },
];
const OWNER_FIELDS: FieldSpec[] = [
  { key: 'owner_name', label: 'اسم المالك', type: 'text' },
  { key: 'lease_years', label: 'مدّة الإيجار (سنوات)', type: 'number' },
  { key: 'registry_no', label: 'رقم السجلّ', type: 'text' },
];

const ALL_FIELDS = [...SOIL_FIELDS, ...CLIMATE_FIELDS, ...OWNER_FIELDS];

// قيمة الحقل من التفاصيل → نصّ للمدخل (null/undefined → '').
function valToStr(v: unknown): string {
  return v == null ? '' : String(v);
}

// يبني patch من الحقول المُعدَّلة فقط (مقارنةً بالأصل): نصّ فارغ → null (مسح).
function buildPatch(
  draft: Record<string, string>,
  original: FieldDetail,
): FieldUpdatePatch {
  const patch: Record<string, number | string | null> = {};
  for (const spec of ALL_FIELDS) {
    const raw = draft[spec.key] ?? '';
    const origStr = valToStr((original as unknown as Record<string, unknown>)[spec.key]);
    if (raw === origStr) continue; // لم يتغيّر ⇒ لا يُرسَل
    if (raw === '') {
      patch[spec.key] = null; // مُسح ⇒ null صريح
    } else if (spec.type === 'number') {
      // قيمة رقميّة غير مكتملة/غير صالحة (مثل "-") ⇒ NaN؛ لا تُدرَج في الـpatch
      // كي لا تتحوّل إلى null عبر JSON وتمسح القيمة على الخادم دون قصد.
      const n = Number(raw);
      if (Number.isFinite(n)) patch[spec.key] = n;
    } else {
      patch[spec.key] = raw;
    }
  }
  return patch as FieldUpdatePatch;
}

function Section({
  icon, title, fields, draft, onChange,
}: {
  icon: React.ReactNode;
  title: string;
  fields: FieldSpec[];
  draft: Record<string, string>;
  onChange: (key: string, value: string) => void;
}) {
  return (
    <div className="rounded-xl border p-4" style={{ borderColor: '#334155', background: '#0f1117' }}>
      <div className="flex items-center gap-2 mb-3 text-slate-200 text-sm font-semibold">
        {icon}{title}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {fields.map((f) => (
          <div key={f.key}>
            <label className="block text-xs text-slate-400 mb-1">{f.label}</label>
            <input
              type={f.type}
              value={draft[f.key] ?? ''}
              onChange={(e) => onChange(f.key, e.target.value)}
              placeholder={f.hint ?? '—'}
              className="w-full px-2.5 py-1.5 rounded-lg text-sm"
              style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function FieldDetailPanel({
  fieldId,
  fieldName,
  onClose,
}: {
  fieldId: string;
  fieldName: string;
  onClose: () => void;
}) {
  const { data, isLoading, isError, error, refetch } = useFieldDetail(fieldId);
  const update = useUpdateField(fieldId);
  const [draft, setDraft] = useState<Record<string, string>>({});

  // بذر المسوّدة من التفاصيل الحيّة عند وصولها (تحرير محلّيّ بعدها).
  useEffect(() => {
    if (!data) return;
    const seed: Record<string, string> = {};
    for (const f of ALL_FIELDS) {
      seed[f.key] = valToStr((data as unknown as Record<string, unknown>)[f.key]);
    }
    setDraft(seed);
  }, [data]);

  const onChange = (key: string, value: string) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const handleSave = async () => {
    if (!data) return;
    const patch = buildPatch(draft, data);
    if (Object.keys(patch).length === 0) {
      toastStore.add('info', 'لا تغييرات', 'لم تُعدَّل أيّ بيانات');
      return;
    }
    try {
      await update.mutateAsync(patch);
      toastStore.add('success', '✅ تم حفظ التفاصيل', fieldName);
      onClose();
    } catch (e) {
      toastStore.add(
        'error',
        '⚠️ فشل حفظ التفاصيل',
        apiErrorMessage(e, 'تعذّر الحفظ — تحقّق من القاعدة/الصلاحيّة.'),
      );
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.7)' }}>
      <div
        className="rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        style={{ background: '#1e293b', border: '1px solid #334155' }}
        dir="rtl"
      >
        <div className="flex items-center justify-between p-5 pb-3 sticky top-0" style={{ background: '#1e293b' }}>
          <div>
            <h3 className="font-bold text-slate-100">تفاصيل الحقل</h3>
            <p className="text-xs text-slate-400 mt-0.5">{fieldName}</p>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-700 text-slate-400" aria-label="إغلاق">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 pb-5">
          {isLoading && <LoadingState message="جارٍ تحميل تفاصيل الحقل…" />}
          {isError && !isLoading && (
            <ErrorState
              title="تعذّر تحميل التفاصيل"
              detail={apiErrorMessage(error, 'القاعدة غير متاحة أو الحقل غير موجود.')}
              onRetry={() => refetch()}
            />
          )}
          {data && !isLoading && (
            <div className="space-y-4">
              <p className="text-xs text-slate-500">
                املأ ما تعرفه تدريجيّاً — تُحفَظ الحقول المُعدَّلة فقط. الحقول الفارغة تبقى دون قيمة.
              </p>
              <Section icon={<FlaskConical className="w-4 h-4 text-emerald-400" />} title="كيمياء التربة"
                fields={SOIL_FIELDS} draft={draft} onChange={onChange} />
              <Section icon={<Mountain className="w-4 h-4 text-sky-400" />} title="المناخ الدقيق والتضاريس"
                fields={CLIMATE_FIELDS} draft={draft} onChange={onChange} />
              <Section icon={<Scroll className="w-4 h-4 text-amber-400" />} title="الملكيّة"
                fields={OWNER_FIELDS} draft={draft} onChange={onChange} />

              <div className="flex gap-3 pt-1">
                <button
                  onClick={handleSave}
                  disabled={update.isPending}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
                  style={{ background: '#16a34a' }}
                >
                  <Check className="w-4 h-4" /> {update.isPending ? 'جارٍ الحفظ…' : 'حفظ التفاصيل'}
                </button>
                <button onClick={onClose} className="px-4 py-2.5 rounded-lg text-sm text-slate-400 border" style={{ borderColor: '#334155' }}>
                  إغلاق
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
