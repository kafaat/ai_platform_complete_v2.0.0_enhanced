// ═══════════════════════════════════════════════════════════════
// SAHOOL — GisToolsPage (أدوات الهندسة المكانيّة · GIS Studio v1)
// ───────────────────────────────────────────────────────────────
// قسم مستوحى من GeoLibre لتطبيق عمليّات هندسيّة مكانيّة على حدود حقل في
// المتصفّح (Turf) ⇒ معاينة فقط. يختار المستخدم حقلاً (useFieldOptions)، ثمّ
// عمليّة: «حِزام (Buffer)» بمسافة بالأمتار أو «تبسيط (Simplify)» بعتبة، ويُعرَض
// قبل/بعد: المساحة (areaSqMeters عبر @turf/area) وعدد الرؤوس — لا أكثر.
//
// أمانة صارمة (لا ادّعاء قاعدة بيانات مكانيّة):
//   • العمليّات كلّها في المتصفّح عبر @turf — لا استدعاء خادم، لا تحوّل خادميّ.
//   • معاينة فقط — لا حفظ في v1 (يُذكَر صراحةً في الواجهة: «معاينة فقط — لا يُحفَظ»).
//   • نتيجة غير حقيقيّة (مُدخَل ناقص / حِزام سالب يُفني الهندسة) ⇒ حالة صادقة لا رقم مُلفَّق.
// الحالات (تحميل/فراغ/خطأ) عبر StateViews الموحّدة. RTL + الثيم الداكن (slate)
// مطابقةً لأشقّاء القسم (NlGisPage/SQLWorkspacePage).
// ═══════════════════════════════════════════════════════════════
import { useMemo, useState } from 'react';
import { Wrench, Circle, Spline, AlertTriangle, Info, ArrowLeft } from 'lucide-react';
import { useFieldOptions } from '../hooks/useFieldOptions';
import { resolveActiveFieldId } from '../lib/fields';
import { areaSqMeters } from '../lib/geo';
import {
  bufferFieldGeometry,
  simplifyFieldGeometry,
  countVertices,
  isMultiPolygon,
  toTurfFeature,
  featureToGeometry,
  type ArealGeometry,
} from '../lib/fieldGeometryOps';
import { LoadingState, ErrorState, EmptyState } from '../components/StateViews';

// ثيم داكن مطابق لأشقّاء القسم (NlGisPage) — أنماط مضمّنة موحّدة.
const surfaceStyle = { background: '#1e293b', borderColor: '#334155' } as const;
const inputStyle = { background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' } as const;

type OpId = 'buffer' | 'simplify';

const OPS: { id: OpId; label: string; icon: typeof Circle; hint: string }[] = [
  { id: 'buffer', label: 'حِزام (Buffer)', icon: Circle, hint: 'توسيع/تقليص الحدّ بمسافة بالأمتار (سالبة ⇒ تقليص).' },
  { id: 'simplify', label: 'تبسيط (Simplify)', icon: Spline, hint: 'إزالة رؤوس زائدة (Douglas–Peucker) بعتبة — يقلّ التفصيل دون تشويه البنية.' },
];

// تنسيق المساحة: م² ⇒ هكتار (÷10000) برقمين عشريّين، وم² كمرجع.
function fmtArea(m2: number): string {
  if (!Number.isFinite(m2) || m2 <= 0) return '—';
  const ha = m2 / 10_000;
  return `${ha.toLocaleString('ar', { maximumFractionDigits: 2 })} هـ`;
}
function fmtSqm(m2: number): string {
  if (!Number.isFinite(m2) || m2 <= 0) return '—';
  return `${Math.round(m2).toLocaleString('ar')} م²`;
}

export default function GisToolsPage() {
  const { options, isLoading, isError, refetch } = useFieldOptions();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [op, setOp] = useState<OpId>('buffer');
  const [meters, setMeters] = useState<number>(25);
  const [tolerance, setTolerance] = useState<number>(0.001);

  const activeId = resolveActiveFieldId(options, selectedId);
  const field = options.find((o) => o.id === activeId);

  // الهندسة الأصليّة مُطبَّعة عبر toTurfFeature/featureToGeometry (نفس مسار قراءة
  // الملفّ الهندسيّ) — null إذا لم يحمل الحقل هندسة مساحيّة صالحة (فجوة بيانات صادقة).
  const originalGeom: ArealGeometry | null = useMemo(
    () => featureToGeometry(toTurfFeature(field?.geometry)),
    [field?.geometry],
  );

  // الهندسة الناتجة (معاينة) — تُحسَب عند تغيّر الحقل/العمليّة/الوسيط. null ⇒ نتيجة
  // غير حقيقيّة (مُدخَل ناقص أو حِزام سالب أفنى الهندسة) ⇒ نعرض رسالة صادقة لا رقماً.
  const resultGeom: ArealGeometry | null = useMemo(() => {
    if (!originalGeom) return null;
    return op === 'buffer'
      ? bufferFieldGeometry(originalGeom, meters)
      : simplifyFieldGeometry(originalGeom, tolerance);
  }, [originalGeom, op, meters, tolerance]);

  if (isLoading) return <LoadingState message="جارٍ تحميل الحقول…" />;
  if (isError) return <ErrorState title="تعذّر تحميل الحقول" onRetry={() => refetch()} />;
  if (options.length === 0) {
    return (
      <EmptyState
        icon={<Wrench className="w-8 h-8" />}
        title="لا حقول متاحة"
        hint="أضف حقلاً بحدود (هندسة) ثمّ عُد لتطبيق العمليّات المكانيّة عليه معاينةً."
      />
    );
  }

  const origArea = originalGeom ? areaSqMeters(originalGeom) : 0;
  const resArea = resultGeom ? areaSqMeters(resultGeom) : 0;
  const origVerts = countVertices(originalGeom);
  const resVerts = countVertices(resultGeom);
  const areaDeltaPct = origArea > 0 && resultGeom ? ((resArea - origArea) / origArea) * 100 : 0;

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <Wrench className="w-5 h-5 text-sky-400" />
        <h2 className="text-xl font-bold text-slate-100">أدوات الهندسة المكانيّة</h2>
      </div>
      <p className="text-sm text-slate-400">
        طبّق عمليّة هندسيّة (حِزام/تبسيط) على حدود حقلك مباشرةً في المتصفّح عبر Turf،
        وقارن المساحة وعدد الرؤوس قبل/بعد.
        <span className="text-amber-300"> معاينة فقط — لا يُحفَظ.</span>
      </p>

      {/* بانر معاينة فقط (بارز، صادق) */}
      <div className="rounded-xl border p-3 flex items-center gap-2" style={{ background: '#1a1400', borderColor: '#f59e0b55' }}>
        <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
        <span className="text-sm font-semibold text-amber-200">
          معاينة فقط — كلّ العمليّات في متصفّحك (Turf)، لا حفظ ولا تعديل على الخادم في هذا الإصدار.
        </span>
      </div>

      {/* اختيار الحقل + العمليّة + الوسيط */}
      <div className="rounded-xl border p-4 space-y-4" style={surfaceStyle}>
        {/* الحقل */}
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">الحقل</span>
          <select
            value={activeId}
            onChange={(e) => setSelectedId(e.target.value)}
            aria-label="اختيار الحقل"
            className="px-3 py-2 rounded-lg text-sm"
            style={inputStyle}
          >
            {options.map((o) => (
              <option key={o.id} value={o.id}>{o.name}</option>
            ))}
          </select>
        </label>

        {/* العمليّة (شرائح تبديل) */}
        <div className="space-y-1.5">
          <span className="text-xs text-slate-400">العمليّة</span>
          <div className="flex flex-wrap gap-2">
            {OPS.map((o) => {
              const Icon = o.icon;
              const active = op === o.id;
              return (
                <button
                  key={o.id}
                  type="button"
                  onClick={() => setOp(o.id)}
                  aria-pressed={active}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium"
                  style={active
                    ? { background: '#0c2233', color: '#7dd3fc', border: '1px solid #0ea5e955' }
                    : { ...inputStyle, color: '#cbd5e1' }}
                >
                  <Icon className="w-4 h-4" />
                  {o.label}
                </button>
              );
            })}
          </div>
          <p className="text-[12px] text-slate-500">
            {OPS.find((o) => o.id === op)?.hint}
          </p>
        </div>

        {/* وسيط العمليّة */}
        {op === 'buffer' ? (
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">المسافة (بالأمتار) — موجبة توسيعاً، سالبة تقليصاً</span>
            <input
              type="number"
              value={meters}
              step={1}
              onChange={(e) => setMeters(Number(e.target.value))}
              aria-label="مسافة الحِزام بالأمتار"
              className="px-3 py-2 rounded-lg text-sm w-40"
              style={inputStyle}
            />
          </label>
        ) : (
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">العتبة (Tolerance) — أكبر ⇒ تبسيط أعمق</span>
            <input
              type="number"
              value={tolerance}
              step={0.0005}
              min={0}
              onChange={(e) => setTolerance(Number(e.target.value))}
              aria-label="عتبة التبسيط"
              className="px-3 py-2 rounded-lg text-sm w-40"
              style={inputStyle}
            />
          </label>
        )}
      </div>

      {/* لا هندسة مساحيّة للحقل (فجوة بيانات صادقة) */}
      {!originalGeom && (
        <div className="rounded-xl border p-4 flex items-start gap-3" style={surfaceStyle}>
          <Info className="w-5 h-5 text-slate-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-slate-300">
            هذا الحقل لا يحمل حدوداً (هندسة مساحيّة) صالحة — لا يمكن تطبيق عمليّة مكانيّة عليه.
            اختر حقلاً ذا حدود مرسومة.
          </div>
        </div>
      )}

      {/* العمليّة لم تُنتج هندسة حقيقيّة (حِزام سالب أفنى الحقل مثلاً) */}
      {originalGeom && !resultGeom && (
        <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
          <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-amber-200">
            {op === 'buffer'
              ? 'لم تُنتج هذه المسافة هندسة صالحة — قد يكون الحِزام السالب أفنى الحقل كاملاً. جرّب قيمة أصغر.'
              : 'لم تُنتج هذه العتبة هندسة صالحة — جرّب قيمة مختلفة.'}
          </div>
        </div>
      )}

      {/* معاينة المقارنة (قبل/بعد) — قراءة فقط */}
      {originalGeom && resultGeom && (
        <div className="rounded-xl border overflow-hidden" style={surfaceStyle}>
          <div className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-slate-100" style={{ borderBottom: '1px solid #334155' }}>
            <Info className="w-4 h-4 text-sky-400" /> المقارنة (معاينة)
            {isMultiPolygon(resultGeom) && (
              <span className="text-[11px] px-2 py-0.5 rounded-full text-amber-200" style={{ background: '#1a1400', border: '1px solid #f59e0b44' }}>
                نتيجة متعدّدة الأجزاء (MultiPolygon)
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-px" style={{ background: '#334155' }}>
            {/* الأصل */}
            <div className="p-4 space-y-1" style={{ background: '#1e293b' }}>
              <div className="text-[11px] text-slate-400">الأصل</div>
              <div className="text-sm text-slate-100 font-semibold">{fmtArea(origArea)}</div>
              <div className="text-[11px] text-slate-500">{fmtSqm(origArea)}</div>
              <div className="text-[11px] text-slate-400 pt-1">الرؤوس: <span className="text-slate-200">{origVerts.toLocaleString('ar')}</span></div>
            </div>

            {/* السهم/الدلتا */}
            <div className="p-4 flex flex-col items-center justify-center gap-1" style={{ background: '#1e293b' }}>
              <ArrowLeft className="w-5 h-5 text-sky-400" aria-hidden="true" />
              <div className="text-[11px] text-slate-400">
                تغيّر المساحة:
                <span className={areaDeltaPct >= 0 ? 'text-emerald-300 mr-1' : 'text-amber-300 mr-1'}>
                  {areaDeltaPct >= 0 ? '+' : ''}{areaDeltaPct.toLocaleString('ar', { maximumFractionDigits: 1 })}٪
                </span>
              </div>
              <div className="text-[11px] text-slate-400">
                تغيّر الرؤوس:
                <span className="text-slate-200 mr-1">{(resVerts - origVerts).toLocaleString('ar')}</span>
              </div>
            </div>

            {/* الناتج */}
            <div className="p-4 space-y-1" style={{ background: '#1e293b' }}>
              <div className="text-[11px] text-slate-400">الناتج ({OPS.find((o) => o.id === op)?.label})</div>
              <div className="text-sm text-slate-100 font-semibold">{fmtArea(resArea)}</div>
              <div className="text-[11px] text-slate-500">{fmtSqm(resArea)}</div>
              <div className="text-[11px] text-slate-400 pt-1">الرؤوس: <span className="text-slate-200">{resVerts.toLocaleString('ar')}</span></div>
            </div>
          </div>
          <div className="px-4 py-2 text-[11px] text-slate-500" style={{ borderTop: '1px solid #334155' }}>
            معاينة محسوبة في المتصفّح عبر Turf — لا تُحفَظ ولا تُغيّر حدود الحقل على الخادم.
          </div>
        </div>
      )}
    </div>
  );
}
