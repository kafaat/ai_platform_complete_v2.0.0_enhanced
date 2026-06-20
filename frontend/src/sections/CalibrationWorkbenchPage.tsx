// ═══════════════════════════════════════════════════════════════
// SAHOOL — CalibrationWorkbenchPage (منضدة المعايرة للخبير الزراعيّ)
// منضدة عمل (لا لوحة عرض): يقارن الخبير القاعدة الموروثة بالقيم المُدامة لكلّ
// منطقة، يقترح قيماً فتُتحقَّق ضدّ حدود آمنة (يقترح لا يكتب)، يوافق فيُدِيم
// (override + source_ar إلزاميّ) أو يطبّق تكيّفاً محروساً بدليل مُدام (confirm=true
// صريح)، يرفض فيعكس (DELETE override)، ويراجع سجلّ التدقيق (أو التجاوزات المُدامة
// بديلاً إن غاب /audit).
// صدق: لا قيمة بلا API؛ كلّ حالات loading/empty/error صادقة؛ calibrated=false
// وحدود الأمان مُبرَزة؛ الكتابة لأصحاب الصلاحيّة فقط (canMutate/canManage). لا تلمس
// CalibrationPage.tsx (لوحة العرض). تطابق أنماط DecisionStudioPage بصريّاً ولونيّاً.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  SlidersHorizontal, GitCompare, FlaskConical, CheckCircle2, XCircle,
  AlertTriangle, ShieldCheck, History, RefreshCw, Lock, ArrowRightLeft,
} from 'lucide-react';
import {
  useRegionCalibration, useResolvedCalibration, useCalibrationOverrides,
  useCalibrationAudit, useProposeCalibrationValues, useSetRegionOverride,
  useDeleteRegionOverride, useApplyAdaptFromEvidence,
} from '../hooks/useApi';
import {
  apiErrorMessage,
  type CalibrationProfile, type ResolvedCalibration,
  type CalibrationValuesInput, type CalibrationValidation,
} from '../services/api';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate, canManage } from '../lib/permissions';
import { ErrorState, LoadingState, EmptyState } from '../components/StateViews';

// مناطق المعايرة المعروفة (تطابق REGION_NAMES_AR الخلفيّة، دون العامّ).
const REGIONS: { key: string; ar: string }[] = [
  { key: 'jawf',      ar: 'الجوف' },
  { key: 'tihama',    ar: 'تهامة' },
  { key: 'marib',     ar: 'مأرب' },
  { key: 'hadramout', ar: 'حضرموت' },
  { key: 'ibb',       ar: 'إب' },
];

// الحقول العدديّة القابلة للمعايرة + حدّها الآمن (يطابق calibration_ingest._BOUNDS).
// يُعرَض المدى للخبير كي يقترح ضمنه (إبراز حدود الأمان). uptake_fractions مُستثناة
// هنا (كتلة بمجموع=1) — تُعرَض للقراءة في المقارنة لا للإدخال (تبسيط آمن).
interface FieldSpec { key: keyof CalibrationValuesInput; ar: string; bounds: string; unit?: string }
const FIELD_SPECS: FieldSpec[] = [
  { key: 'kc_dyn_min',            ar: 'Kc أدنى',          bounds: '0.10–0.50' },
  { key: 'kc_dyn_max',            ar: 'Kc أقصى',          bounds: '0.80–1.50' },
  { key: 'raw_fraction',          ar: 'p (RAW)',          bounds: '0.30–0.70' },
  { key: 'root_depth_m',          ar: 'عمق الجذور',       bounds: '0–3.0', unit: 'م' },
  { key: 'forecast_infiltration', ar: 'ترشّح المطر',      bounds: '0–1.0' },
  { key: 'yield_uncertainty',     ar: 'عدم يقين الغلّة',  bounds: '0–1.0' },
  { key: 'price_uncertainty',     ar: 'عدم يقين السعر',   bounds: '0–1.0' },
];

// عتبات الإجهاد المعروضة في المقارنة (مشتقّة من القاعدة/المُحلّ) — قراءة فقط.
function fmtNum(v: unknown, digits = 2): string {
  if (v === null || v === undefined || typeof v !== 'number' || Number.isNaN(v)) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(digits);
}

// صفّ مقارنة حقل واحد: القاعدة مقابل المُدام مع إبراز الفرق.
function CompareRow({
  label, base, resolved, digits = 2, unit,
}: { label: string; base: unknown; resolved: unknown; digits?: number; unit?: string }) {
  const differ =
    typeof base === 'number' && typeof resolved === 'number'
      ? Math.abs(base - resolved) > 1e-9
      : base !== resolved;
  return (
    <tr className="text-slate-300" style={{ borderBottom: '1px solid #25303f' }}>
      <td className="px-3 py-1.5 font-medium text-slate-200">{label}</td>
      <td className="px-3 py-1.5 text-slate-400">{fmtNum(base, digits)}{unit ? ` ${unit}` : ''}</td>
      <td className="px-3 py-1.5">
        <span className={differ ? 'font-semibold text-emerald-300' : 'text-slate-400'}>
          {fmtNum(resolved, digits)}{unit ? ` ${unit}` : ''}
        </span>
      </td>
      <td className="px-3 py-1.5 text-center">
        {differ
          ? <ArrowRightLeft className="w-3.5 h-3.5 text-emerald-400 inline" />
          : <span className="text-slate-600 text-xs">=</span>}
      </td>
    </tr>
  );
}

// شارة حالة المعايرة (calibrated/validated) — إبراز صريح لغير المُعايَر.
function CalibratedBadge({ profile }: { profile: ResolvedCalibration }) {
  const isOverride = profile.override_source === 'db_override';
  return (
    <span
      className="text-[11px] px-2 py-0.5 rounded-full font-semibold flex items-center gap-1"
      style={
        isOverride
          ? { background: '#0c2a1a', color: '#4ade80' }
          : { background: '#2a1a00', color: '#fbbf24' }
      }
    >
      {isOverride
        ? <><CheckCircle2 className="w-3 h-3" /> مُعايَر مُدام</>
        : <><AlertTriangle className="w-3 h-3" /> موروث (calibrated=false)</>}
    </span>
  );
}

// لوح المقارنة: القاعدة (get_calibration) مقابل المُحلّ (resolved).
function ComparePanel({
  base, resolved,
}: { base: CalibrationProfile; resolved: ResolvedCalibration }) {
  return (
    <div className="rounded-xl border overflow-hidden" style={{ background: '#1e293b', borderColor: '#334155' }}>
      <div className="flex items-center justify-between gap-2 px-4 py-2 text-sm font-semibold text-slate-100"
        style={{ borderBottom: '1px solid #334155' }}>
        <span className="flex items-center gap-2"><GitCompare className="w-4 h-4 text-emerald-400" /> القاعدة مقابل المُدام</span>
        <CalibratedBadge profile={resolved} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[11px] text-slate-400" style={{ borderBottom: '1px solid #334155' }}>
              <th className="px-3 py-2 text-right font-medium">المعامل</th>
              <th className="px-3 py-2 text-right font-medium">القاعدة (موروث)</th>
              <th className="px-3 py-2 text-right font-medium">المُدام (resolved)</th>
              <th className="px-3 py-2 text-center font-medium">فرق</th>
            </tr>
          </thead>
          <tbody>
            <CompareRow label="Kc (أدنى)" base={base.kc_dyn_min} resolved={resolved.kc_dyn_min} />
            <CompareRow label="Kc (أقصى)" base={base.kc_dyn_max} resolved={resolved.kc_dyn_max} />
            <CompareRow label="p (RAW)" base={base.raw_fraction} resolved={resolved.raw_fraction} />
            <CompareRow label="عمق الجذور" base={base.root_depth_m} resolved={resolved.root_depth_m} unit="م" />
            <CompareRow label="ترشّح المطر" base={base.forecast_infiltration} resolved={resolved.forecast_infiltration} />
            <CompareRow label="عدم يقين الغلّة" base={base.yield_uncertainty} resolved={resolved.yield_uncertainty} />
            <CompareRow label="عدم يقين السعر" base={base.price_uncertainty} resolved={resolved.price_uncertainty} />
          </tbody>
        </table>
      </div>
      <div className="px-4 py-2 text-[11px] text-slate-500" style={{ borderTop: '1px solid #25303f' }}>
        المصدر: {resolved.source_ar}
        {resolved.override_applied.length > 0 && (
          <span className="text-emerald-400"> — حقول مُدامة: {resolved.override_applied.join('، ')}</span>
        )}
      </div>
    </div>
  );
}

// نتيجة التحقّق (accepted/rejected) بأسباب عربيّة — لا كتابة.
function ValidationResult({ v }: { v: CalibrationValidation }) {
  const accepted = Object.entries(v.accepted);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold"
          style={{ background: '#0a1f2e', color: '#38bdf8' }}>
          مقبولة {accepted.length} · مرفوضة {v.rejected.length}
        </span>
        {!v.ready_to_persist && (
          <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold flex items-center gap-1"
            style={{ background: '#2a1a00', color: '#fbbf24' }}>
            <AlertTriangle className="w-3 h-3" /> غير جاهز للإدامة
          </span>
        )}
      </div>
      {accepted.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {accepted.map(([k, val]) => (
            <div key={k} className="rounded-lg px-3 py-2 flex items-center gap-2"
              style={{ background: '#0c2a1a', border: '1px solid #14532d' }}>
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <div className="min-w-0">
                <div className="text-[11px] text-emerald-300/80 truncate">{k}</div>
                <div className="text-sm font-semibold text-emerald-200 truncate">
                  {typeof val === 'object' ? JSON.stringify(val) : fmtNum(val)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      {v.rejected.length > 0 && (
        <div className="space-y-1.5">
          {v.rejected.map((r, i) => (
            <div key={`${r.field}-${i}`} className="rounded-lg px-3 py-2 flex items-start gap-2"
              style={{ background: '#2a0d0d', border: '1px solid #7f1d1d' }}>
              <XCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
              <div className="text-[12px]">
                <span className="font-semibold text-red-200">{r.field}</span>
                <span className="text-red-300/80"> — {r.reason_ar}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      {v.warnings_ar.length > 0 && (
        <div className="rounded-lg px-3 py-2 space-y-1" style={{ background: '#1a1400', border: '1px solid #f59e0b33' }}>
          {v.warnings_ar.map((w, i) => (
            <div key={i} className="text-[11px] text-amber-200/90">• {w}</div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function CalibrationWorkbenchPage() {
  const role = useAuthStore((s) => s.user?.role);
  const mayMutate = canMutate(role);   // الكتابة (اقتراح/إدامة/حذف) لغير المُشاهِد
  const mayManage = canManage(role);   // تطبيق التكيّف الآليّ — owner/manager فقط

  const [region, setRegion] = useState<string>(REGIONS[0].key);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [sourceAr, setSourceAr] = useState('');
  const [validation, setValidation] = useState<CalibrationValidation | null>(null);
  const [confirmAdapt, setConfirmAdapt] = useState(false);
  const [actionMsg, setActionMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const base     = useRegionCalibration(region);
  const resolved = useResolvedCalibration(region);
  const audit    = useCalibrationAudit(region);
  const overrides = useCalibrationOverrides();

  const propose = useProposeCalibrationValues();
  const setOverride = useSetRegionOverride();
  const deleteOverride = useDeleteRegionOverride();
  const applyAdapt = useApplyAdaptFromEvidence();

  // يبني حمولة القيم من المدخلات الرقميّة غير الفارغة (لا قيمة بلا إدخال صريح).
  const buildValues = (withSource: boolean): CalibrationValuesInput => {
    const out: CalibrationValuesInput = {};
    for (const spec of FIELD_SPECS) {
      const raw = inputs[spec.key as string];
      if (raw !== undefined && raw.trim() !== '') {
        const n = Number(raw);
        if (!Number.isNaN(n)) (out as Record<string, number>)[spec.key as string] = n;
      }
    }
    if (withSource && sourceAr.trim()) out.source_ar = sourceAr.trim();
    return out;
  };

  const hasValues = FIELD_SPECS.some(
    (s) => (inputs[s.key as string] ?? '').trim() !== '',
  );

  const onRegionChange = (r: string) => {
    setRegion(r);
    setInputs({});
    setSourceAr('');
    setValidation(null);
    setConfirmAdapt(false);
    setActionMsg(null);
  };

  const onPropose = () => {
    setActionMsg(null);
    propose.mutate(
      { region, values: buildValues(true) },
      { onSuccess: (v) => setValidation(v) },
    );
  };

  const onApprove = () => {
    setActionMsg(null);
    if (!sourceAr.trim()) {
      setActionMsg({ ok: false, text: 'مصدر القياس (source_ar) إلزاميّ للموافقة على الإدامة.' });
      return;
    }
    if (!window.confirm('تأكيد: إدامة القيم المُتحقَّقة لهذه المنطقة (تُطبَّق على قرارات لاحقة، عكوسيّة عبر الرفض)؟')) return;
    setOverride.mutate(
      { region, values: buildValues(true) },
      {
        onSuccess: () => setActionMsg({ ok: true, text: 'أُدِيمت القيم المُعايَرة بنجاح — ظهرت في المقارنة.' }),
        onError:   (e) => setActionMsg({ ok: false, text: apiErrorMessage(e, 'تعذّرت الإدامة (قد تكون قيمة مرفوضة أو القاعدة غير متاحة).') }),
      },
    );
  };

  const onReject = () => {
    setActionMsg(null);
    if (!window.confirm('تأكيد: حذف التجاوز المُدام وإعادة المنطقة للوراثة العامّة (عكسٌ صريح)؟')) return;
    deleteOverride.mutate(region, {
      onSuccess: () => setActionMsg({ ok: true, text: 'أُعيدت المنطقة للوراثة العامّة (حُذف التجاوز).' }),
      onError:   (e) => setActionMsg({ ok: false, text: apiErrorMessage(e, 'تعذّر الحذف (القاعدة غير متاحة؟).') }),
    });
  };

  const onApplyAdapt = () => {
    setActionMsg(null);
    if (!confirmAdapt) {
      setActionMsg({ ok: false, text: 'تطبيق التكيّف يتطلّب تأكيداً صريحاً (confirm) — مبدأ الصدق.' });
      return;
    }
    if (!window.confirm('تأكيد: تطبيق التكيّف المحروس بالدليل المُدام (يُدِيم تجاوزاً عند التأهّل فقط)؟')) return;
    applyAdapt.mutate(
      { region, input: { confirm: true, ...(sourceAr.trim() ? { source_ar: sourceAr.trim() } : {}) } },
      {
        onSuccess: (r) =>
          setActionMsg({
            ok: r.applied,
            text: r.applied
              ? 'طُبِّق التكيّف وأُدِيم — ظهر في المقارنة.'
              : `لم يُطبَّق التكيّف (الحالة: ${r.status}) — غير مؤهَّل/بلا تغيير. لا تطبيق خفيّ.`,
          }),
        onError: (e) => setActionMsg({ ok: false, text: apiErrorMessage(e, 'تعذّر تطبيق التكيّف (بلا تأكيد/خارج الأمان/القاعدة غير متاحة).') }),
      },
    );
  };

  const regionAr = REGIONS.find((r) => r.key === region)?.ar ?? region;
  const currentOverride = overrides.data?.overrides.find((o) => o.region === region) ?? null;
  const busy = setOverride.isPending || deleteOverride.isPending || applyAdapt.isPending;

  return (
    <div className="space-y-6 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <SlidersHorizontal className="w-5 h-5 text-emerald-400" />
        <h2 className="text-xl font-bold text-slate-100">منضدة المعايرة</h2>
      </div>
      <p className="text-sm text-slate-400">
        منضدة الخبير الزراعيّ: قارِن <span className="text-emerald-300">القاعدة الموروثة</span> بالقيم
        <span className="text-emerald-300"> المُدامة</span>، اقترح قيماً فتُتحقَّق ضدّ
        <span className="text-amber-300"> حدود آمنة</span> (يقترح لا يكتب)، ثمّ وافِق فتُدام (بمصدر إلزاميّ)
        أو ارفض فتُعكَس. لا قيمة بلا API — كلّ كتابة محروسة بالصلاحيّة والتحقّق.
      </p>

      {/* اختيار المنطقة */}
      <div className="rounded-xl border p-4 flex flex-wrap items-center gap-2"
        style={{ background: '#1e293b', borderColor: '#334155' }}>
        <span className="text-xs text-slate-400">المنطقة:</span>
        {REGIONS.map((r) => (
          <button key={r.key} onClick={() => onRegionChange(r.key)}
            className="px-3 py-1.5 rounded-lg text-sm transition-colors"
            style={
              region === r.key
                ? { background: '#1e3a1e', color: '#4ade80', border: '1px solid #16a34a' }
                : { background: '#0f1117', color: '#94a3b8', border: '1px solid #25303f' }
            }>
            {r.ar}
          </button>
        ))}
        <button onClick={() => { base.refetch(); resolved.refetch(); audit.refetch(); overrides.refetch(); }}
          disabled={base.isFetching || resolved.isFetching}
          className="mr-auto flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm text-slate-300 disabled:opacity-60"
          style={{ background: '#1e293b', border: '1px solid #334155' }}>
          <RefreshCw className={`w-4 h-4 ${base.isFetching || resolved.isFetching ? 'animate-spin' : ''}`} />
          تحديث
        </button>
      </div>

      {!mayMutate && (
        <div className="rounded-xl border p-3 flex items-start gap-3" style={{ background: '#0f1117', borderColor: '#25303f' }}>
          <Lock className="w-5 h-5 text-slate-500 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-slate-400">
            دورك للعرض فقط — المقارنة والتدقيق متاحان، لكنّ الاقتراح والموافقة والرفض محصورة بأصحاب صلاحيّة التعديل.
          </div>
        </div>
      )}

      {/* ── مقارنة ── */}
      <section className="space-y-2">
        <div className="flex items-center gap-2">
          <GitCompare className="w-4 h-4 text-emerald-400" />
          <h3 className="text-base font-bold text-slate-100">مقارنة — {regionAr}</h3>
        </div>
        {(base.isLoading || resolved.isLoading) && <LoadingState message="جارٍ جلب ملفّ المعايرة…" />}
        {(base.isError || resolved.isError) && (
          <ErrorState title="تعذّر جلب ملفّ المعايرة"
            detail="قد تكون القاعدة غير متاحة (503) أو لا صلاحيّة عرض (403)."
            onRetry={() => { base.refetch(); resolved.refetch(); }} />
        )}
        {base.data && resolved.data && <ComparePanel base={base.data} resolved={resolved.data} />}
      </section>

      {/* ── اقتراح/تحقّق + موافقة/رفض ── */}
      {mayMutate && (
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-emerald-400" />
            <h3 className="text-base font-bold text-slate-100">اقتراح وتحقّق</h3>
            <span className="text-[11px] text-slate-500">— يقترح لا يكتب (حدود آمنة)</span>
          </div>
          <div className="rounded-xl border p-4 space-y-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {FIELD_SPECS.map((spec) => (
                <label key={spec.key as string} className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">
                    {spec.ar}{spec.unit ? ` (${spec.unit})` : ''}
                    <span className="text-[10px] text-amber-300/70"> · المدى {spec.bounds}</span>
                  </span>
                  <input
                    type="number" step="any" inputMode="decimal" dir="ltr"
                    value={inputs[spec.key as string] ?? ''}
                    onChange={(e) => setInputs((s) => ({ ...s, [spec.key as string]: e.target.value }))}
                    placeholder="—"
                    className="px-3 py-2 rounded-lg text-sm"
                    style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
                </label>
              ))}
            </div>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">مصدر القياس (source_ar) — إلزاميّ للموافقة</span>
              <input
                value={sourceAr} onChange={(e) => setSourceAr(e.target.value)}
                placeholder="مثال: قياسات حقليّة موسم 2026، 12 عيّنة"
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>

            <div className="flex flex-wrap gap-2">
              <button onClick={onPropose} disabled={!hasValues || propose.isPending}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-50"
                style={{ background: '#0ea5e9' }}>
                <FlaskConical className="w-4 h-4" />
                {propose.isPending ? 'جارٍ التحقّق…' : 'تحقّق (اقتراح)'}
              </button>
              <button onClick={onApprove} disabled={!hasValues || !sourceAr.trim() || busy}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-50"
                style={{ background: '#16a34a' }}>
                <ShieldCheck className="w-4 h-4" />
                {setOverride.isPending ? 'جارٍ الإدامة…' : 'وافِق وأَدِم'}
              </button>
              <button onClick={onReject} disabled={busy || !currentOverride}
                title={currentOverride ? undefined : 'لا تجاوز مُدام لهذه المنطقة'}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-red-200 disabled:opacity-50"
                style={{ background: '#2a0d0d', border: '1px solid #7f1d1d' }}>
                <XCircle className="w-4 h-4" />
                {deleteOverride.isPending ? 'جارٍ العكس…' : 'ارفض (اعكِس)'}
              </button>
            </div>

            {propose.isError && (
              <div className="text-[12px] text-red-300">{apiErrorMessage(propose.error, 'تعذّر التحقّق من القيم.')}</div>
            )}
            {validation && <ValidationResult v={validation} />}
            {actionMsg && (
              <div className="rounded-lg px-3 py-2 text-[12px] flex items-start gap-2"
                style={actionMsg.ok
                  ? { background: '#0c2a1a', color: '#86efac', border: '1px solid #14532d' }
                  : { background: '#2a0d0d', color: '#fca5a5', border: '1px solid #7f1d1d' }}>
                {actionMsg.ok ? <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" /> : <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />}
                <span>{actionMsg.text}</span>
              </div>
            )}
          </div>

          {/* تطبيق التكيّف بدليل مُدام — owner/manager فقط، confirm صريح */}
          {mayManage && (
            <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                <h4 className="text-sm font-bold text-amber-200">تطبيق التكيّف المحروس بالدليل المُدام</h4>
              </div>
              <p className="text-[12px] text-amber-200/80">
                يقرأ نتائج المنطقة المُدامة ويبني منها الدليل، ثمّ يُدِيم تجاوزاً <span className="font-semibold">عند التأهّل فقط</span>
                (دليل field_verified + إشارة اتّجاه + تغيير فعليّ ضمن الأمان). غير ذلك: لا إدامة (applied=false). يتطلّب تأكيداً صريحاً.
              </p>
              <label className="flex items-center gap-2 text-[12px] text-amber-200 cursor-pointer">
                <input type="checkbox" checked={confirmAdapt} onChange={(e) => setConfirmAdapt(e.target.checked)} />
                أؤكّد صراحةً تطبيق التكيّف (confirm=true)
              </label>
              <button onClick={onApplyAdapt} disabled={!confirmAdapt || busy}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-50"
                style={{ background: '#d97706' }}>
                <SlidersHorizontal className="w-4 h-4" />
                {applyAdapt.isPending ? 'جارٍ التطبيق…' : 'طبّق التكيّف'}
              </button>
            </div>
          )}
        </section>
      )}

      {/* ── تدقيق ── */}
      <section className="space-y-2">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-emerald-400" />
          <h3 className="text-base font-bold text-slate-100">سجلّ التدقيق</h3>
          <span className="text-[11px] text-slate-500">
            — {audit.data ? '/audit (الأحدث أوّلاً)' : 'بديل: التجاوزات المُدامة'}
          </span>
        </div>
        <div className="rounded-xl border p-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
          {audit.isLoading && <LoadingState message="جارٍ جلب سجلّ التدقيق…" />}
          {/* النقطة /audit أفضل-جهد (null عند 404) ⇒ نرتدّ إلى overrides/all */}
          {!audit.isLoading && audit.data && audit.data.entries.length > 0 ? (
            <div className="space-y-2">
              {audit.data.entries.map((e, i) => (
                <div key={i} className="rounded-lg px-3 py-2" style={{ background: '#0f1117', border: '1px solid #25303f' }}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-slate-200">{e.action ?? e.field ?? 'تغيير'}</span>
                    {e.created_at && <span className="text-[11px] text-slate-500" dir="ltr">{e.created_at}</span>}
                  </div>
                  <div className="text-[12px] text-slate-400 mt-1">
                    {e.field && <span>الحقل: {e.field} · </span>}
                    {e.old_value !== undefined && <span>من {fmtNum(e.old_value)} ← </span>}
                    {e.new_value !== undefined && <span>إلى {fmtNum(e.new_value)} · </span>}
                    {e.actor && <span>المنفّذ: {e.actor} · </span>}
                    {e.source_ar && <span className="text-slate-300">{e.source_ar}</span>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            // بديل صادق: source_ar + updated_at من overrides/all للمنطقة الحاليّة.
            <>
              {overrides.isLoading && <LoadingState message="جارٍ جلب التجاوزات المُدامة…" />}
              {overrides.isError && (
                <ErrorState title="تعذّر جلب سجلّ التدقيق"
                  detail="القاعدة غير متاحة (503)؟"
                  onRetry={() => overrides.refetch()} />
              )}
              {!overrides.isLoading && !overrides.isError && (
                currentOverride ? (
                  <div className="rounded-lg px-3 py-2" style={{ background: '#0f1117', border: '1px solid #25303f' }}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-slate-200">{regionAr} — تجاوز مُدام</span>
                      {currentOverride.updated_at && (
                        <span className="text-[11px] text-slate-500" dir="ltr">{currentOverride.updated_at}</span>
                      )}
                    </div>
                    <div className="text-[12px] text-slate-400 mt-1">
                      الحقول: {Object.keys(currentOverride.override_values).join('، ') || '—'}
                    </div>
                    {currentOverride.source_ar && (
                      <div className="text-[12px] text-slate-300 mt-0.5">المصدر: {currentOverride.source_ar}</div>
                    )}
                  </div>
                ) : (
                  <EmptyState
                    icon={<History className="w-8 h-8" />}
                    title="لا سجلّ تدقيق لهذه المنطقة بعد"
                    hint="لم يُدَم أيّ تجاوز معايرة لها — تظهر هنا التغييرات بعد أوّل موافقة/إدامة." />
                )
              )}
            </>
          )}
        </div>
      </section>
    </div>
  );
}
