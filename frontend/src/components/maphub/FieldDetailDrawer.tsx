// ═══════════════════════════════════════════════════════════════
// SAHOOL — Map Hub · درج تفاصيل الحقل المنزلق (Field Detail Drawer)
// ───────────────────────────────────────────────────────────────
// درج جانبيّ ينزلق (framer-motion) داخل مركز الخرائط: يعرض الحقل المختار،
// يتيح تحرير بيانات التربة/المناخ/الملكيّة (PATCH جزئيّ — الحقول المُعدَّلة فقط،
// نفس منطق FieldDetailPanel)، ويلخّص الموسم الأحدث (للقراءة). حالات صادقة
// (تحميل/خطأ مع إعادة/حفظ) عبر StateViews + useFieldDetail/useUpdateField/useSeasons.
//
// يختلف عن FieldDetailPanel (مودال مركزيّ يُفتَح من إدارة الحقول): هنا درج
// منزلق سياقيّ بجانب الخريطة، أخفّ، ويعيد استخدام نفس منطق الـpatch بأمانة
// (لا تلفيق قيم؛ النصّ الفارغ → null صريح، الرقم غير الصالح يُتجاهَل).
// ═══════════════════════════════════════════════════════════════
import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X, Check, FlaskConical, Mountain, Scroll, Sprout, Droplets } from 'lucide-react';
import { useFieldDetail, useUpdateField, useSeasons } from '../../hooks/useApi';
import { apiErrorMessage, type FieldDetail, type FieldUpdatePatch, type SeasonSummary } from '../../services/api';
import { LoadingState, ErrorState } from '../StateViews';
import { toastStore } from '../../services/websocket';

type NumKey =
  | 'soil_ph' | 'soil_ec' | 'soil_om' | 'soil_n' | 'soil_p' | 'soil_k'
  | 'elevation_m' | 'slope_pct' | 'annual_rainfall_mm' | 'lease_years';
type StrKey = 'aspect' | 'climate_zone' | 'owner_name' | 'registry_no';

interface FieldSpec { key: NumKey | StrKey; label: string; type: 'number' | 'text'; hint?: string }

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
  { key: 'aspect', label: 'الجهة', type: 'text' },
  { key: 'climate_zone', label: 'المنطقة المناخيّة', type: 'text' },
  { key: 'annual_rainfall_mm', label: 'الأمطار السنويّة (مم)', type: 'number' },
];
const OWNER_FIELDS: FieldSpec[] = [
  { key: 'owner_name', label: 'اسم المالك', type: 'text' },
  { key: 'lease_years', label: 'مدّة الإيجار (سنوات)', type: 'number' },
  { key: 'registry_no', label: 'رقم السجلّ', type: 'text' },
];
const ALL_FIELDS = [...SOIL_FIELDS, ...CLIMATE_FIELDS, ...OWNER_FIELDS];

function valToStr(v: unknown): string { return v == null ? '' : String(v); }

// يبني patch من الحقول المُعدَّلة فقط (نفس منطق FieldDetailPanel.buildPatch).
function buildPatch(draft: Record<string, string>, original: FieldDetail): FieldUpdatePatch {
  const patch: Record<string, number | string | null> = {};
  for (const spec of ALL_FIELDS) {
    const raw = draft[spec.key] ?? '';
    const origStr = valToStr((original as unknown as Record<string, unknown>)[spec.key]);
    if (raw === origStr) continue;
    if (raw === '') { patch[spec.key] = null; }
    else if (spec.type === 'number') {
      const n = Number(raw);
      if (Number.isFinite(n)) patch[spec.key] = n;
    } else { patch[spec.key] = raw; }
  }
  return patch as FieldUpdatePatch;
}

function fmtRead(value: string | number | null | undefined, unit?: string): string {
  if (value == null || value === '') return '—';
  return unit ? `${value} ${unit}` : String(value);
}

function Section({
  icon, title, fields, draft, onChange,
}: {
  icon: React.ReactNode; title: string; fields: FieldSpec[];
  draft: Record<string, string>; onChange: (key: string, value: string) => void;
}) {
  return (
    <div className="rounded-xl border p-3" style={{ borderColor: '#334155', background: '#0f1117' }}>
      <div className="flex items-center gap-2 mb-2.5 text-slate-200 text-sm font-semibold">{icon}{title}</div>
      <div className="grid grid-cols-2 gap-2.5">
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

// صفوف ملخّص الموسم الأحدث (للقراءة) — يطابق seasonRows في FieldDetailPanel.
function seasonRows(s: SeasonSummary): { label: string; value: string | number | null; unit?: string }[] {
  return [
    { label: 'الحالة', value: s.status },
    { label: 'المحاصيل', value: s.crops?.join('، ') || null },
    { label: 'الغلّة المستهدفة', value: s.target_yield_kg_ha, unit: 'كجم/هـ' },
    { label: 'الغلّة الفعليّة', value: s.actual_yield_kg_ha, unit: 'كجم/هـ' },
    { label: 'تاريخ البذر', value: s.sowing_date },
    { label: 'نوع الريّ', value: s.irrigation_type },
  ];
}

export default function FieldDetailDrawer({
  fieldId, fieldName, open, onClose,
}: {
  fieldId: string | null;
  fieldName: string;
  open: boolean;
  onClose: () => void;
}) {
  const { data, isLoading, isError, error, refetch } = useFieldDetail(fieldId ?? undefined);
  const seasonsQuery = useSeasons(fieldId ?? undefined);
  const update = useUpdateField(fieldId ?? '');
  const [draft, setDraft] = useState<Record<string, string>>({});

  const latestSeason = seasonsQuery.data?.[0];

  useEffect(() => {
    if (!data) return;
    const seed: Record<string, string> = {};
    for (const f of ALL_FIELDS) seed[f.key] = valToStr((data as unknown as Record<string, unknown>)[f.key]);
    setDraft(seed);
  }, [data]);

  const onChange = (key: string, value: string) => setDraft((d) => ({ ...d, [key]: value }));

  const irrigationRows = useMemo(() => {
    if (!data) return [];
    return [
      { label: 'نوع الريّ', value: data.irrigation_type },
      { label: 'كفاءة الريّ', value: data.irrigation_efficiency_pct, unit: '%' },
      { label: 'ملوحة الماء', value: data.water_ec, unit: 'dS/m' },
      { label: 'المنطقة', value: data.zone_key },
    ];
  }, [data]);

  const handleSave = async () => {
    if (!data || !fieldId) return;
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
      toastStore.add('error', '⚠️ فشل حفظ التفاصيل', apiErrorMessage(e, 'تعذّر الحفظ — تحقّق من القاعدة/الصلاحيّة.'));
    }
  };

  return (
    <AnimatePresence>
      {open && fieldId && (
        <>
          {/* خلفيّة معتمة (نقرة للإغلاق) */}
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={onClose}
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', zIndex: 1100 }}
          />
          {/* الدرج المنزلق — من اليسار (RTL: الجانب الأبعد عن المحتوى) */}
          <motion.aside
            dir="rtl"
            initial={{ x: '-100%' }} animate={{ x: 0 }} exit={{ x: '-100%' }}
            transition={{ type: 'tween', duration: 0.25 }}
            style={{
              position: 'fixed', top: 0, bottom: 0, insetInlineStart: 0, width: 'min(440px, 92vw)',
              background: '#1e293b', borderInlineEnd: '1px solid #334155', zIndex: 1101,
              overflowY: 'auto', boxShadow: '4px 0 24px rgba(0,0,0,.4)',
            }}
            role="dialog" aria-modal="true" aria-label={`تفاصيل ${fieldName}`}
          >
            <div className="flex items-center justify-between p-4 sticky top-0" style={{ background: '#1e293b', borderBottom: '1px solid #334155' }}>
              <div>
                <h3 className="font-bold text-slate-100 text-base">تفاصيل الحقل</h3>
                <p className="text-xs text-slate-400 mt-0.5">{fieldName}</p>
              </div>
              <button onClick={onClose} className="p-1 rounded hover:bg-slate-700 text-slate-400" aria-label="إغلاق">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 space-y-3">
              {isLoading && <LoadingState message="جارٍ تحميل تفاصيل الحقل…" />}
              {isError && !isLoading && (
                <ErrorState
                  title="تعذّر تحميل التفاصيل"
                  detail={apiErrorMessage(error, 'القاعدة غير متاحة أو الحقل غير موجود.')}
                  onRetry={() => refetch()}
                />
              )}
              {data && !isLoading && (
                <>
                  <p className="text-xs text-slate-500">
                    املأ ما تعرفه تدريجيّاً — تُحفَظ الحقول المُعدَّلة فقط.
                  </p>
                  <Section icon={<FlaskConical className="w-4 h-4 text-emerald-400" />} title="كيمياء التربة"
                    fields={SOIL_FIELDS} draft={draft} onChange={onChange} />
                  <Section icon={<Mountain className="w-4 h-4 text-sky-400" />} title="المناخ والتضاريس"
                    fields={CLIMATE_FIELDS} draft={draft} onChange={onChange} />
                  <Section icon={<Scroll className="w-4 h-4 text-amber-400" />} title="الملكيّة"
                    fields={OWNER_FIELDS} draft={draft} onChange={onChange} />

                  {/* ملفّ الريّ (للقراءة) */}
                  <div className="rounded-xl border p-3" style={{ borderColor: '#334155', background: '#0f1117' }}>
                    <div className="flex items-center gap-2 mb-2.5 text-slate-200 text-sm font-semibold">
                      <Droplets className="w-4 h-4 text-cyan-400" /> ملفّ الريّ
                    </div>
                    <div className="grid grid-cols-2 gap-2.5">
                      {irrigationRows.map((r) => (
                        <div key={r.label}>
                          <span className="block text-xs text-slate-400 mb-1">{r.label}</span>
                          <span className="block text-sm text-slate-100">{fmtRead(r.value, r.unit)}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* ملخّص الموسم الأحدث (للقراءة) */}
                  <div className="rounded-xl border p-3" style={{ borderColor: '#334155', background: '#0f1117' }}>
                    <div className="flex items-center gap-2 mb-2.5 text-slate-200 text-sm font-semibold">
                      <Sprout className="w-4 h-4 text-lime-400" /> الموسم الأحدث والنشاط
                    </div>
                    {seasonsQuery.isLoading ? (
                      <div className="text-xs text-slate-400">جارٍ تحميل المواسم…</div>
                    ) : latestSeason ? (
                      <div className="grid grid-cols-2 gap-2.5">
                        {seasonRows(latestSeason).map((r) => (
                          <div key={r.label}>
                            <span className="block text-xs text-slate-400 mb-1">{r.label}</span>
                            <span className="block text-sm text-slate-100">{fmtRead(r.value, r.unit)}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-xs text-slate-400">لا مواسم مُسجّلة لهذا الحقل بعد.</div>
                    )}
                  </div>

                  <div className="flex gap-2 pt-1 pb-2">
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
                </>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
