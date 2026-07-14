import { useMemo, useState } from 'react';
import { MapContainer, TileLayer, Polygon, Marker, useMapEvents } from 'react-leaflet';
import '../lib/leafletSetup';
import { FlaskConical, MapPin, Plus, ShieldCheck } from 'lucide-react';
import { useSelectedField } from '../hooks/useSelectedField';
import { useCreateLabSample, useLabDecisionContext, useLabSamples, useSubmitSoilLabResult } from '../hooks/useApi';
import { asApiError, apiErrorMessage, apiFieldErrors, type LabSampleCreateInput, type SoilLabResultInput } from '../services/api';
import { LoadingState, ErrorState, EmptyState } from '../components/StateViews';
import { geomToPolygon, fieldRepresentativePoint } from '../lib/geo';
import { useLocation } from 'react-router-dom';

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

function SamplePointPicker({ value, onPick, polygon, center }: {
  value: [number, number] | null;
  onPick: (lat: number, lng: number) => void;
  polygon?: [number, number][];
  center: [number, number];
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
        {value ? <Marker position={value} /> : null}
        <ClickLayer />
      </MapContainer>
    </div>
  );
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

export default function LabSamplingPage() {
  const location = useLocation();
  const routeFieldId = ((location.state as { fieldId?: string } | null)?.fieldId) ?? null;
  const { fieldId, options, setFieldId } = useSelectedField({ routeFieldId });
  const samplesQ = useLabSamples(fieldId || undefined);
  const contextQ = useLabDecisionContext(fieldId || undefined);
  const createSample = useCreateLabSample();
  const submitSoil = useSubmitSoilLabResult();
  const [msg, setMsg] = useState<string | null>(null);
  const selected = options.find((f) => f.id === fieldId);
  const fieldPolygon = useMemo(() => geomToPolygon(selected?.geometry), [selected?.geometry]);
  const rep = selected ? fieldRepresentativePoint(selected) : null;
  const mapCenter = (rep ?? fieldPolygon?.[0] ?? [15.0, 44.0]) as [number, number];
  const [pickedPoint, setPickedPoint] = useState<[number, number] | null>(null);
  const soilSamples = useMemo(() => (samplesQ.data ?? []).filter((s) => s.kind === 'soil'), [samplesQ.data]);

  const onCreateSample = async (fd: FormData) => {
    if (!fieldId) return;
    setMsg(null);
    const latitude = Number(fd.get('latitude') || pickedPoint?.[0]);
    const longitude = Number(fd.get('longitude') || pickedPoint?.[1]);
    const depth_cm_from = n(fd.get('depth_cm_from'));
    const depth_cm_to = n(fd.get('depth_cm_to'));
    const gps_accuracy_m = n(fd.get('gps_accuracy_m'));
    const err = validateSampleNumerics({ lat: latitude, lon: longitude, dFrom: depth_cm_from, dTo: depth_cm_to, gps: gps_accuracy_m });
    if (err) { setMsg(err); return; }
    const payload: LabSampleCreateInput = {
      field_id: fieldId,
      kind: fd.get('kind') === 'water' ? 'water' : 'soil',
      latitude,
      longitude,
      sampled_on: String(fd.get('sampled_on') || new Date().toISOString().slice(0, 10)),
      depth_cm_from,
      depth_cm_to,
      source: String(fd.get('source') || ''),
      gps_accuracy_m,
      status: 'collected',
    };
    try {
      await createSample.mutateAsync(payload);
      setMsg('تم حفظ نقطة العينة وربطها بالحقل والخريطة.');
    } catch (e) { setMsg(labErrorMessage(e, 'فشل حفظ العينة')); }
  };

  const onSubmitSoil = async (fd: FormData) => {
    setMsg(null);
    const payload: SoilLabResultInput = {
      sample_id: String(fd.get('sample_id') || ''),
      ph: n(fd.get('ph')),
      ec_dsm: n(fd.get('ec_dsm')),
      organic_matter_pct: n(fd.get('organic_matter_pct')),
      nitrogen_mg_kg: n(fd.get('nitrogen_mg_kg')),
      phosphorus_mg_kg: n(fd.get('phosphorus_mg_kg')),
      potassium_mg_kg: n(fd.get('potassium_mg_kg')),
      cec_cmol_kg: n(fd.get('cec_cmol_kg')),
      calcium_carbonate_pct: n(fd.get('calcium_carbonate_pct')),
      texture: String(fd.get('texture') || ''),
      // لا نُرسِل approved من نموذج الإدخال: الإدخال العاديّ يُنشئ نتيجة «مُستلَمة» غير
      // مُعتمَدة، والاعتماد انتقال حالة منفصل مُصرَّح به خادميّاً (/lab/samples/{id}/transition
      // → approved) بهويّة مُعتمِد مُصادَقة — لا يجوز للعميل تصديق نتيجته بنفسه (فصل الواجبات).
    };
    try {
      const res = await submitSoil.mutateAsync(payload);
      setMsg(res.decision_usable ? 'نتيجة التربة مكتملة ومعتمدة وجاهزة لعقل التوصيات.' : 'تم حفظ النتيجة، لكنها تحتاج اعتماداً أو قيماً ناقصة قبل استخدامها في القرار.');
    } catch (e) { setMsg(labErrorMessage(e, 'فشل حفظ نتيجة المختبر')); }
  };

  return (
    <div dir="rtl" className="space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2"><FlaskConical className="text-emerald-400" /> فحوصات التربة والمياه</h1>
          <p className="text-sm text-slate-400 mt-1">نقاط أخذ العينات، إحداثيات GPS، نتائج المختبر، وربطها بعقل القرار.</p>
        </div>
        <select value={fieldId ?? ''} onChange={(e) => setFieldId(e.target.value)} className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100">
          <option value="">اختر الحقل</option>
          {options.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      </div>

      {!fieldId ? <EmptyState title="اختر حقلاً" hint="يجب اختيار حقل قبل إضافة عينة." /> : null}
      {samplesQ.isLoading ? <LoadingState message="جارٍ تحميل العينات…" /> : null}
      {samplesQ.isError ? <ErrorState title="تعذر تحميل العينات" detail={apiErrorMessage(asApiError(samplesQ.error), 'خطأ غير معروف')} /> : null}
      {msg ? <div className="rounded-xl border border-emerald-900 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-200">{msg}</div> : null}

      {fieldId ? (
        <div className="grid gap-4 lg:grid-cols-3">
          <form className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 space-y-3" action={(fd) => void onCreateSample(fd)}>
            <h2 className="font-semibold text-slate-100 flex items-center gap-2"><MapPin size={18} /> إضافة نقطة عينة</h2>
            <label className="block text-sm text-slate-300">نوع العينة<select name="kind" className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2"><option value="soil">تربة</option><option value="water">مياه</option></select></label>
            <SamplePointPicker value={pickedPoint} onPick={(lat, lng) => setPickedPoint([lat, lng])} polygon={fieldPolygon} center={mapCenter} />
            <p className="text-[11px] text-slate-400">انقر داخل الخريطة لتحديد نقطة العينة، أو أدخل الإحداثيات يدويًا.</p>
            <div className="grid grid-cols-2 gap-2"><label className="text-sm text-slate-300">Latitude<input required name="latitude" type="number" step="any" min={-90} max={90} value={pickedPoint?.[0] ?? ''} onChange={(e) => setPickedPoint([Number(e.target.value), pickedPoint?.[1] ?? mapCenter[1]])} className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></label><label className="text-sm text-slate-300">Longitude<input required name="longitude" type="number" step="any" min={-180} max={180} value={pickedPoint?.[1] ?? ''} onChange={(e) => setPickedPoint([pickedPoint?.[0] ?? mapCenter[0], Number(e.target.value)])} className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></label></div>
            <div className="grid grid-cols-2 gap-2"><label className="text-sm text-slate-300">من عمق سم<input name="depth_cm_from" type="number" className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></label><label className="text-sm text-slate-300">إلى عمق سم<input name="depth_cm_to" type="number" className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></label></div>
            <label className="block text-sm text-slate-300">تاريخ العينة<input name="sampled_on" type="date" defaultValue={new Date().toISOString().slice(0, 10)} className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></label>
            <label className="block text-sm text-slate-300">مصدر/ملاحظة<input name="source" className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" placeholder="بئر 3 / شبكة 1 / قطاع شمالي" /></label>
            <label className="block text-sm text-slate-300">دقة GPS بالمتر<input name="gps_accuracy_m" type="number" step="any" className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></label>
            <button disabled={!fieldId || createSample.isPending} className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-white disabled:opacity-50"><Plus size={16} /> حفظ العينة</button>
          </form>

          <form className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 space-y-3" action={(fd) => void onSubmitSoil(fd)}>
            <h2 className="font-semibold text-slate-100 flex items-center gap-2"><ShieldCheck size={18} /> إدخال تحليل تربة</h2>
            <label className="block text-sm text-slate-300">العينة<select name="sample_id" required className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2"><option value="">اختر عينة</option>{soilSamples.map((s) => <option key={s.sample_id} value={s.sample_id}>{s.sample_id} · {s.sampled_on ?? 'بدون تاريخ'}</option>)}</select></label>
            <div className="grid grid-cols-3 gap-2"><input name="ph" type="number" step="any" placeholder="pH" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /><input name="ec_dsm" type="number" step="any" placeholder="EC dS/m" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /><input name="organic_matter_pct" type="number" step="any" placeholder="OM %" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></div>
            <div className="grid grid-cols-3 gap-2"><input name="nitrogen_mg_kg" type="number" step="any" placeholder="N" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /><input name="phosphorus_mg_kg" type="number" step="any" placeholder="P" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /><input name="potassium_mg_kg" type="number" step="any" placeholder="K" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></div>
            <div className="grid grid-cols-3 gap-2"><input name="cec_cmol_kg" type="number" step="any" placeholder="CEC" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /><input name="calcium_carbonate_pct" type="number" step="any" placeholder="CaCO3 %" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /><input name="texture" placeholder="Texture" className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2" /></div>
            <p className="text-[11px] text-slate-400">تُحفَظ النتيجة كـ«مُستلَمة» بانتظار الاعتماد. اعتماد المختبر خطوة منفصلة مُصرَّح بها (انتقال حالة) لا يُصدِّقها مُدخِل البيانات بنفسه.</p>
            <button disabled={submitSoil.isPending} className="rounded-xl bg-emerald-600 px-4 py-2 text-white disabled:opacity-50">حفظ التحليل</button>
          </form>

          <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
            <h2 className="font-semibold text-slate-100">سياق القرار</h2>
            <p className="text-sm text-slate-400 mt-1">الحقل: {selected?.name ?? fieldId}</p>
            {contextQ.isLoading ? <LoadingState message="جارٍ قراءة سياق المختبر…" /> : null}
            {contextQ.data ? <div className="mt-3 space-y-2 text-sm"><div>بوابة التوصية: <b className="text-emerald-300">{contextQ.data.recommendation_gate}</b></div><div>جاهزية التربة للتسميد: {contextQ.data.soil_lab_ready_for_fertilizer ? 'نعم' : 'تحتاج مراجعة'}</div><ul className="list-disc pr-5 text-amber-200">{contextQ.data.warnings_ar.map((w) => <li key={w}>{w}</li>)}</ul></div> : <p className="text-sm text-slate-500 mt-3">لا يوجد سياق قرار متاح بعد.</p>}
          </section>
        </div>
      ) : null}

      {fieldId && samplesQ.data ? (
        <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
          <h2 className="font-semibold text-slate-100 mb-3">العينات المسجلة</h2>
          {samplesQ.data.length === 0 ? <EmptyState title="لا توجد عينات" hint="أضف أول نقطة عينة لتظهر كطبقة فوق الخريطة الموحدة." /> : <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="text-slate-400"><tr><th className="text-right py-2">العينة</th><th className="text-right">النوع</th><th className="text-right">الإحداثيات</th><th className="text-right">الحالة</th><th className="text-right">EC/pH</th></tr></thead><tbody>{samplesQ.data.map((s) => <tr key={s.sample_id} className="border-t border-slate-800"><td className="py-2 text-slate-100">{s.sample_id}</td><td>{s.kind === 'soil' ? 'تربة' : 'مياه'}</td><td>{s.latitude.toFixed(5)}, {s.longitude.toFixed(5)}</td><td>{s.status}</td><td>{s.ec_dsm ?? '—'} / {s.ph ?? '—'}</td></tr>)}</tbody></table></div>}
        </section>
      ) : null}
    </div>
  );
}
