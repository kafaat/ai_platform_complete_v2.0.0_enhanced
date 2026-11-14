import { useEffect, useMemo, useState } from 'react';
import { MapContainer, TileLayer, Polygon, Marker, CircleMarker, Tooltip, useMapEvents } from 'react-leaflet';
import '../lib/leafletSetup';
import { LabSampleReview } from './LabSampleReview';
import { FlaskConical, MapPin, Plus, ShieldCheck } from 'lucide-react';
import { useSelectedField } from '../hooks/useSelectedField';
import { useCreateLabSample, useLabDecisionContext, useLabSamples, useSubmitSoilLabResult } from '../hooks/useApi';
import { asApiError, apiErrorMessage, apiFieldErrors, type SamplingOrigin, type LabSampleCreateInput, type SoilLabResultInput, type SoilECMethod } from '../services/api';
import { LoadingState, ErrorState, EmptyState } from '../components/StateViews';
import { geomToPolygon, fieldRepresentativePoint } from '../lib/geo';
import { useAuthStore } from '../hooks/useAuth';
import { canManage, canMutate } from '../lib/permissions';
import { useLabSubmission } from './useLabSubmission';
import { useLocation, useNavigate } from 'react-router';

// يبني رسالة خطأ تُسمّي الحقول المُخالِفة من 422 (بدل رسالة واحدة عامّة — continuation-3 P2).
// تسميات عربيّة للحقول الشائعة؛ غير المعروف يظهر باسمه الحرفيّ.
const LAB_FIELD_LABELS: Record<string, string> = {
  latitude: 'خط العرض', longitude: 'خط الطول', ph: 'pH', ec_dsm: 'EC',
  depth_cm_from: 'العمق من', depth_cm_to: 'العمق إلى', gps_accuracy_m: 'دقّة GPS',
  organic_matter_pct: 'المادة العضويّة %', nitrogen_mg_kg: 'النيتروجين',
  phosphorus_mg_kg: 'الفوسفور', potassium_mg_kg: 'البوتاسيوم',
};
function labErrorMessage(e: unknown, fallback: string): string {
  const fields = apiFieldErrors(e);
  if (fields.length) {
    return fields.map((f) => `${LAB_FIELD_LABELS[f.field] ?? (f.field || 'حقل')}: ${f.msg}`).join('؛ ');
  }
  return apiErrorMessage(e, fallback);
}


const BASEMAP_SAT = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

function SamplePointPicker({ value, onPick, polygon, center, planned, disabled }: {
  value: [number, number] | null;
  onPick: (lat: number, lng: number) => void;
  polygon?: [number, number][];
  center: [number, number];
  planned?: SamplingOrigin;
  disabled: boolean;
}) {
  function ClickLayer() {
    useMapEvents({ click: (e) => onPick(e.latlng.lat, e.latlng.lng) });
    return null;
  }
  return (
    <div className="rounded-xl overflow-hidden border border-slate-800" style={{ height: 260 }}>
      <MapContainer center={value ?? center} zoom={16} style={{ height: '100%', width: '100%' }}>
        <TileLayer url={BASEMAP_SAT} attribution="Tiles &copy; Esri — World Imagery" />
        {polygon && polygon.length >= 3 ? <Polygon positions={polygon} pathOptions={{ color: '#34d399', weight: 2, fillOpacity: 0.08 }} /> : null}
        {planned && <CircleMarker center={[planned.latitude, planned.longitude]} radius={9} pathOptions={{color: '#f59e0b', fillOpacity: 0.2}}>
          <Tooltip>نقطة الخطة {planned.point_id}</Tooltip>
        </CircleMarker>}
        {value ? <Marker position={value} title="موقع الجمع الفعلي" /> : null}
        {!disabled && <ClickLayer />}
      </MapContainer>
    </div>
  );
}

function localDate() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

function n(v: FormDataEntryValue | null): number | null {
  const s = String(v ?? '').trim();
  if (!s) return null;
  const x = Number(s);
  return Number.isFinite(x) ? x : null;
}

// تحقّق مجال عدديّ/إحداثيّ لعيّنة المختبر قبل الإرسال (continuation-3 P0): حدود
// خط العرض/الطول، عمق غير سالب، عمق النهاية > البداية، دقّة GPS غير سالبة. يُعيد
// رسالة خطأ عربيّة أو null. (n() يرفض NaN/Infinity أصلاً بإعادته null.)
export function validateSampleNumerics(v: {
  lat: number; lon: number; dFrom: number | null; dTo: number | null; gps: number | null;
}): string | null {
  if (!Number.isFinite(v.lat) || v.lat < -90 || v.lat > 90) return 'خط العرض يجب أن يكون بين -90 و90.';
  if (!Number.isFinite(v.lon) || v.lon < -180 || v.lon > 180) return 'خط الطول يجب أن يكون بين -180 و180.';
  if (v.dFrom != null && v.dFrom < 0) return 'عمق البداية يجب أن يكون صفراً أو أكثر.';
  if (v.dTo != null && v.dTo < 0) return 'عمق النهاية يجب أن يكون صفراً أو أكثر.';
  if (v.dFrom != null && v.dTo != null && v.dTo <= v.dFrom) return 'عمق النهاية يجب أن يكون أكبر من عمق البداية.';
  if (v.gps != null && v.gps < 0) return 'دقّة GPS يجب أن تكون صفراً أو أكثر.';
  return null;
}

const purposeLabel = {
  fertility: 'الخصوبة', nitrate: 'النترات', salinity: 'الملوحة', orchard: 'البساتين',
  texture: 'القوام', no_till: 'الزراعة دون حراثة',
};

function PlannedSamplingDetails({ origin }: { origin: SamplingOrigin }) {
  const sources = Object.entries(origin.indicator_sources ?? {});
  return <details className="text-sm">
    <summary>المنطقة {origin.zone_id} · نقطة الخطة {origin.point_id}</summary>
    <div>موقع الخطة <bdi>{origin.latitude}, {origin.longitude}</bdi></div>
    {origin.sampling_purpose && <div>غرض الجمع: {purposeLabel[origin.sampling_purpose]}</div>}
    {origin.planned_depth_cm && <div>العمق المخطط: {origin.planned_depth_cm.join('–')} سم</div>}
    {origin.composite !== undefined && <div>{origin.composite ? 'عينة مركّبة' : 'عينة موضعية'}</div>}
    {sources.map(([index, src]) => <div key={index}><bdi>{index.toUpperCase()} · {src.scene_id ?? src.asset_id} {src.acquisition_date}</bdi></div>)}
  </details>;
}

type PlanState = { fieldId?: string; planId?: string; origin?: SamplingOrigin; depth?: number[] } | null;
export default function LabSamplingPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const route = location.state as PlanState;
  const selected = useSelectedField({routeFieldId: route?.fieldId});
  const tenant = useAuthStore(state => state.tenantId);
  const actor = useAuthStore(state => state.user?.id ?? state.user?.email);
  // A plan point names one collection: once a sample is saved from it, later samples in
  // this visit are independent unless the user opens a plan point again.
  const [consumedPlan, setConsumedPlan] = useState<string | null>(null);
  const planKey = JSON.stringify([route?.fieldId, route?.planId, route?.origin?.point_id]);
  const planState = selected.fieldId === route?.fieldId && consumedPlan !== planKey ? route : null;
  const fieldScope = JSON.stringify([tenant, actor, selected.fieldId]);
  const scope = JSON.stringify([fieldScope, planState?.planId, planState?.origin?.point_id]);
  // The message lives here so it survives the remount that follows a consumed plan point.
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { setMsg(null); }, [selected.fieldId]);
  return <LabForms key={scope} selection={selected} planState={planState} scope={scope} fieldScope={fieldScope}
    msg={msg} setMsg={setMsg}
    consumePlan={() => {
      setConsumedPlan(planKey);
      navigate('.', {replace: true, state: {fieldId: selected.fieldId}});
    }}
    changeField={id => {
      if (route?.fieldId) navigate(location.pathname + location.search, {replace: true, state: null});
      selected.setFieldId(id);
    }} />;
}

function LabForms({selection, planState, scope, fieldScope, msg, setMsg, consumePlan, changeField}: {
  selection: ReturnType<typeof useSelectedField>; planState: PlanState; scope: string; fieldScope: string;
  msg: string | null; setMsg: (msg: string | null) => void; consumePlan: () => void; changeField: (id: string) => void;
}) {
  const {fieldId, options} = selection;
  const role = useAuthStore(state => state.user?.role);
  const samplesQ = useLabSamples(fieldId || undefined);
  const contextQ = useLabDecisionContext(fieldId || undefined);
  const createSample = useCreateLabSample();
  const submitSoil = useSubmitSoilLabResult();
  const sampleWrite = useLabSubmission('sample', scope, createSample.mutateAsync);
  const resultWrite = useLabSubmission('result', fieldScope, submitSoil.mutateAsync);
  const selected = options.find((f) => f.id === fieldId);
  const fieldPolygon = useMemo(() => geomToPolygon(selected?.geometry), [selected?.geometry]);
  const rep = selected ? fieldRepresentativePoint(selected) : null;
  const mapCenter = (planState?.origin ? [planState.origin.latitude, planState.origin.longitude] : rep ?? fieldPolygon?.[0] ?? [15.0, 44.0]) as [number, number];
  const [coords, setCoords] = useState({field: fieldId, lat: '', lon: ''});
  const lat = sampleWrite.pending ? String(sampleWrite.pending.latitude) : coords.lat;
  const lon = sampleWrite.pending ? String(sampleWrite.pending.longitude) : coords.lon;
  const pickedPoint: [number, number] | null = lat && lon ? [Number(lat), Number(lon)] : null;
  const soilSamples = useMemo(() => (samplesQ.data ?? []).filter((s) => s.kind === 'soil'), [samplesQ.data]);

  const buildSample = (fd: FormData): LabSampleCreateInput | undefined => {
    if (!fieldId) return;
    setMsg(null);
    const latitude = n(fd.get('latitude')) ?? NaN;
    const longitude = n(fd.get('longitude')) ?? NaN;
    const depth_cm_from = n(fd.get('depth_cm_from'));
    const depth_cm_to = n(fd.get('depth_cm_to'));
    const gps_accuracy_m = n(fd.get('gps_accuracy_m'));
    const err = validateSampleNumerics({ lat: latitude, lon: longitude, dFrom: depth_cm_from, dTo: depth_cm_to, gps: gps_accuracy_m });
    if (err) { setMsg(err); return; }
    // The API rejects a soil sample without both depths; say so before the request.
    if (fd.get('kind') !== 'water' && (depth_cm_from == null || depth_cm_to == null)) { setMsg('عمق البداية والنهاية مطلوبان لعيّنة التربة.'); return; }
    const payload: LabSampleCreateInput = {
      field_id: fieldId,
      ...(fd.get('kind') !== 'water' && planState?.origin && planState.planId
        ? {sampling_plan_id: planState.planId, sampling_origin: planState.origin} : {}),
      kind: fd.get('kind') === 'water' ? 'water' : 'soil',
      latitude,
      longitude,
      sampled_on: String(fd.get('sampled_on') || localDate()),
      depth_cm_from,
      depth_cm_to,
      source: String(fd.get('source') || ''),
      gps_accuracy_m,
      status: 'collected',
    };
    return payload;
  };

  const buildResult = (fd: FormData): SoilLabResultInput => {
    const observed = String(fd.get('observed_at') || '');
    const payload: SoilLabResultInput = {
      ...(observed ? {observed_at: new Date(observed).toISOString()} : {}),
      sample_id: String(fd.get('sample_id') || ''),
      ph: n(fd.get('ph')),
      ec_dsm: n(fd.get('ec_dsm')),
      ...(n(fd.get('ec_dsm')) === null ? {} : {ec_extraction_method: String(fd.get('ec_extraction_method') || 'unspecified') as SoilECMethod}),
      organic_matter_pct: n(fd.get('organic_matter_pct')),
      nitrogen_mg_kg: n(fd.get('nitrogen_mg_kg')),
      phosphorus_mg_kg: n(fd.get('phosphorus_mg_kg')),
      potassium_mg_kg: n(fd.get('potassium_mg_kg')),
      cec_cmol_kg: n(fd.get('cec_cmol_kg')),
      calcium_carbonate_pct: n(fd.get('calcium_carbonate_pct')),
      sand_pct: n(fd.get('sand_pct')), silt_pct: n(fd.get('silt_pct')), clay_pct: n(fd.get('clay_pct')),
      texture: String(fd.get('texture') || ''),
      // لا نُرسِل approved من نموذج الإدخال: الإدخال العاديّ يُنشئ نتيجة «مُستلَمة» غير
      // مُعتمَدة، والاعتماد انتقال حالة منفصل مُصرَّح به خادميّاً (/lab/samples/{id}/transition
      // → approved) بهويّة مُعتمِد مُصادَقة — لا يجوز للعميل تصديق نتيجته بنفسه (فصل الواجبات).
    };
    return payload;
  };

  return (
    <div dir="rtl" className="space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2"><FlaskConical className="text-emerald-400" /> فحوصات التربة والمياه</h1>
          <p className="text-sm text-slate-400 mt-1">نقاط أخذ العينات، إحداثيات GPS، نتائج المختبر، وربطها بعقل القرار.</p>
        </div>
        <select value={fieldId ?? ''} onChange={(e) => changeField(e.target.value)} className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100">
          <option value="">اختر الحقل</option>
          {options.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      </div>

      {!fieldId ? <EmptyState title="اختر حقلاً" hint="يجب اختيار حقل قبل إضافة عينة." /> : null}
      {samplesQ.isLoading ? <LoadingState message="جارٍ تحميل العينات…" /> : null}
      {samplesQ.isError ? <ErrorState title="تعذر تحميل العينات" detail={apiErrorMessage(asApiError(samplesQ.error), 'خطأ غير معروف')} onRetry={() => { void samplesQ.refetch(); }} /> : null}
      {msg ? <div className="rounded-xl border border-emerald-900 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-200">{msg}</div> : null}

      {fieldId ? (
        <div className="grid gap-4 lg:grid-cols-3">
          {canMutate(role) && <form className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 space-y-3" onSubmit={async event => {
            event.preventDefault();
            const form = event.currentTarget;
            try {
              const row = await sampleWrite.submit(() => buildSample(new FormData(form)));
              if (row) {
                setMsg('تم حفظ نقطة العينة وربطها بالحقل والخريطة.');
                form.reset();
                setCoords({field: fieldId, lat: '', lon: ''});
                if (planState?.origin) consumePlan();
              }
            } catch (error) { setMsg(labErrorMessage(error, 'فشل حفظ العينة')); }
          }}>
            <h2 className="font-semibold text-slate-100 flex items-center gap-2"><MapPin size={18} /> إضافة نقطة عينة</h2>
            {sampleWrite.blocked && <p role="alert">تعذّر قراءة محاولة الحفظ المحلية. أعد فتح هذه الصفحة بعد استعادة تخزين التبويب.</p>}
            {sampleWrite.pending && <p role="status">طلب سابق بانتظار التأكيد. ستُرسل البيانات المحفوظة نفسها عند إعادة المحاولة.</p>}
            <fieldset className="space-y-3" disabled={sampleWrite.busy || !!sampleWrite.pending || sampleWrite.blocked}>
            <label className="block text-sm text-slate-300">نوع العينة<select name="kind" className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2"><option value="soil">تربة</option><option value="water">مياه</option></select></label>
            {planState?.origin && <><PlannedSamplingDetails origin={planState.origin} /><p>حدّد أدناه موقع الجمع الفعلي.</p></>}
            <SamplePointPicker disabled={sampleWrite.busy || !!sampleWrite.pending || sampleWrite.blocked} planned={planState?.origin} value={pickedPoint} onPick={(lat, lng) => setCoords({field: fieldId, lat: String(lat), lon: String(lng)})} polygon={fieldPolygon} center={mapCenter} />
            <p className="text-[11px] text-slate-400">انقر داخل الخريطة لتحديد نقطة العينة، أو أدخل الإحداثيات يدويًا.</p>
            <div className="grid grid-cols-2 gap-2"><label className="text-sm text-slate-300">Latitude<input required name="latitude" type="number" step="any" min={-90} max={90} value={lat} onChange={(e) => setCoords({field: fieldId, lat: e.target.value, lon})} className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></label><label className="text-sm text-slate-300">Longitude<input required name="longitude" type="number" step="any" min={-180} max={180} value={lon} onChange={(e) => setCoords({field: fieldId, lat, lon: e.target.value})} className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></label></div>
            <div className="grid grid-cols-2 gap-2"><label className="text-sm text-slate-300">من عمق سم<input name="depth_cm_from" defaultValue={planState?.depth?.[0]} type="number" className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></label><label className="text-sm text-slate-300">إلى عمق سم<input name="depth_cm_to" defaultValue={planState?.depth?.[1]} type="number" className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></label></div>
            <label className="block text-sm text-slate-300">تاريخ العينة<input name="sampled_on" type="date" defaultValue={localDate()} className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></label>
            <label className="block text-sm text-slate-300">مصدر/ملاحظة<input name="source" className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" placeholder="بئر 3 / شبكة 1 / قطاع شمالي" /></label>
            <label className="block text-sm text-slate-300">دقة GPS بالمتر<input name="gps_accuracy_m" type="number" step="any" className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></label>
            </fieldset>
            <button disabled={!fieldId || sampleWrite.busy || sampleWrite.blocked} className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-white disabled:opacity-50"><Plus size={16} /> {sampleWrite.pending ? 'إعادة إرسال العينة' : 'حفظ العينة'}</button>
          </form>}

          {canManage(role) && <form className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 space-y-3" onSubmit={async event => {
            event.preventDefault();
            const form = event.currentTarget;
            try {
              const row = await resultWrite.submit(() => buildResult(new FormData(form)));
              if (row) {
                setMsg(row.decision_usable ? 'نتيجة التربة مكتملة ومعتمدة وجاهزة لعقل التوصيات.' : 'تم حفظ النتيجة وهي بانتظار استكمال القيم أو الاعتماد.');
                form.reset();
              }
            } catch (error) { setMsg(labErrorMessage(error, 'فشل حفظ نتيجة المختبر')); }
          }}>
            <h2 className="font-semibold text-slate-100 flex items-center gap-2"><ShieldCheck size={18} /> إدخال تحليل تربة</h2>
            {resultWrite.blocked && <p role="alert">تعذّر قراءة محاولة الحفظ المحلية. أعد فتح هذه الصفحة بعد استعادة تخزين التبويب.</p>}
            {resultWrite.pending && <p role="status">تحليل العينة {resultWrite.pending.sample_id} بانتظار التأكيد. ستُرسل البيانات المحفوظة نفسها عند إعادة المحاولة.</p>}
            <fieldset className="space-y-3" disabled={resultWrite.busy || !!resultWrite.pending || resultWrite.blocked}>
            <label className="block text-sm text-slate-300">العينة<select name="sample_id" required className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2"><option value="">اختر عينة</option>{soilSamples.map((s) => <option key={s.sample_id} value={s.sample_id}>{s.sample_id} · {s.sampled_on ?? 'بدون تاريخ'}</option>)}</select></label>
            <label className="block text-sm">وقت التحليل بالتوقيت المحلي كما يورده المختبر
              <input name="observed_at" type="datetime-local" className="block rounded-xl bg-slate-900 p-2" />
            </label>
            <label className="block text-sm">طريقة استخلاص ملوحة التربة
              <select name="ec_extraction_method" defaultValue="unspecified" className="block rounded-xl bg-slate-900 p-2">
                <option value="unspecified">غير مذكورة في تقرير المختبر</option>
                <option value="saturated_paste">مستخلص العجينة المشبعة (ECe)</option>
                <option value="soil_water_1_1">تربة إلى ماء 1:1</option>
                <option value="soil_water_1_2_5">تربة إلى ماء 1:2.5</option>
                <option value="soil_water_1_5">تربة إلى ماء 1:5</option>
              </select>
            </label>
            <div className="grid grid-cols-3 gap-2"><input name="ph" type="number" step="any" placeholder="pH" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /><input name="ec_dsm" type="number" step="any" placeholder="EC dS/m" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /><input name="organic_matter_pct" type="number" step="any" placeholder="OM %" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></div>
            <div className="grid grid-cols-3 gap-2"><input name="nitrogen_mg_kg" type="number" step="any" placeholder="N" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /><input name="phosphorus_mg_kg" type="number" step="any" placeholder="P" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /><input name="potassium_mg_kg" type="number" step="any" placeholder="K" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></div>
            <div className="grid grid-cols-3 gap-2">{([['sand_pct','الرمل'],['silt_pct','الغرين'],['clay_pct','الطين']] as const).map(([name,label]) => <label key={name}>{label} %<input name={name} type="number" min="0" max="100" step="any" className="w-full rounded-xl bg-slate-900 p-2" /></label>)}</div>
            <div className="grid grid-cols-3 gap-2"><input name="cec_cmol_kg" type="number" step="any" placeholder="CEC" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /><input name="calcium_carbonate_pct" type="number" step="any" placeholder="CaCO3 %" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /><input name="texture" placeholder="Texture" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></div>
            <p className="text-[11px] text-slate-400">تُحفَظ النتيجة كـ«مُستلَمة» بانتظار الاعتماد. اعتماد المختبر خطوة منفصلة مُصرَّح بها (انتقال حالة) لا يُصدِّقها مُدخِل البيانات بنفسه.</p>
            </fieldset>
            <button disabled={resultWrite.busy || resultWrite.blocked} className="rounded-xl bg-emerald-600 px-4 py-2 text-white disabled:opacity-50">{resultWrite.pending ? 'إعادة إرسال التحليل' : 'حفظ التحليل'}</button>
          </form>}

          <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
            <h2 className="font-semibold text-slate-100">سياق القرار</h2>
            <p className="text-sm text-slate-400 mt-1">الحقل: {selected?.name ?? fieldId}</p>
            {contextQ.isLoading ? <LoadingState message="جارٍ قراءة سياق المختبر…" /> : null}
            {contextQ.isError ? <ErrorState title="تعذّر تحميل سياق المختبر" detail={labErrorMessage(contextQ.error, 'تعذّر الاتصال بالخدمة')} onRetry={() => { void contextQ.refetch(); }} /> : contextQ.data ? <div className="mt-3 space-y-2 text-sm"><div>بوابة التوصية: <b className="text-emerald-300">{contextQ.data.recommendation_gate}</b></div><div>جاهزية التربة للتسميد: {contextQ.data.soil_lab_ready_for_fertilizer ? 'نعم' : 'تحتاج مراجعة'}</div><ul className="list-disc pr-5 text-amber-200">{contextQ.data.warnings_ar.map((w) => <li key={w}>{w}</li>)}</ul></div> : !contextQ.isLoading ? <p className="text-sm text-slate-500 mt-3">لا يوجد سياق قرار متاح بعد.</p> : null}
          </section>
        </div>
      ) : null}



      {fieldId && samplesQ.data ? (
        <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
          <h2 className="font-semibold text-slate-100 mb-3">العينات المسجلة</h2>
          {samplesQ.data.length === 0 ? <EmptyState title="لا توجد عينات" hint="أضف أول نقطة عينة لتظهر كطبقة فوق الخريطة الموحدة." /> : <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="text-slate-400"><tr><th className="text-right py-2">العينة</th><th className="text-right">النوع</th><th className="text-right">الإحداثيات</th><th className="text-right">الحالة</th><th className="text-right">EC/pH</th></tr></thead><tbody>{samplesQ.data.map((s) => <tr key={s.sample_id} className="border-t border-slate-800"><td className="py-2 text-slate-100">{s.sample_id}{s.sampling_origin && <PlannedSamplingDetails origin={s.sampling_origin} />}</td><td>{s.kind === 'soil' ? 'تربة' : 'مياه'}</td><td>{s.latitude.toFixed(5)}, {s.longitude.toFixed(5)}</td><td>{s.status}<LabSampleReview sample={s} /></td><td>{s.ec_dsm ?? '—'} / {s.ph ?? '—'}</td></tr>)}</tbody></table></div>}
        </section>
      ) : null}
    </div>
  );
}
