import { useMemo, useState } from 'react';
import { Bug, CloudSun, ClipboardList, MapPin, Mountain, Sprout } from 'lucide-react';
import {
  useDistrictActivePests,
  useDistrictDetail,
  useDistrictsIndex,
  useFieldWeatherSummary,
  useGeoLocateRecommend,
  useOnboardingQuestionnaire,
  useSubmitOnboarding,
  useWeatherAnalysis,
  useWeatherPlantingGuide,
} from '../../hooks/useDistrictsWeather';
import {
  activePestsList,
  analysisFacts,
  answeredCount,
  buildSubmitPayload,
  districtLabel,
  districtOptions,
  geoRecommendFacts,
  isDisabled,
  missingRequiredIds,
  monthNameAr,
  monthOptions,
  operationLabelAr,
  operationRows,
  parseWeatherRecords,
  pestWindows,
  plantingMonths,
  plantingWindowColor,
  riskMonthsText,
  serverMessage,
  severityColor,
  severityLabelAr,
  stringList,
  suitabilityColor,
  suitabilityLabelAr,
  weatherAlerts,
  type PestWindow,
} from '../../lib/districtsWeather';
import { T } from '../ds';

interface Props {
  /** معرّف الحقل النشط — يُربَط به ردّ الاستبيان (onboarding/responses) إن وُجد. */
  fieldId?: string | null;
  /** تسمية محصول الحقل النشط — سياق عرض فقط (لا يُغيّر عقود الخادم). */
  cropLabel?: string | null;
  enabled?: boolean;
}

type SectionKey = 'districts' | 'geo' | 'weather' | 'onboarding';

const SECTIONS: { key: SectionKey; label_ar: string }[] = [
  { key: 'districts', label_ar: 'دليل المديريّات' },
  { key: 'geo', label_ar: 'توصية الموقع الجغرافيّ' },
  { key: 'weather', label_ar: 'طقس الحقل وتحليلاته' },
  { key: 'onboarding', label_ar: 'استبيان التهيئة' },
];

const inputStyle = { border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink } as const;
const boxStyle = { borderColor: T.line, background: 'rgba(15,23,42,.35)' } as const;

/** قياس نصّيّ ⇒ رقم أو null (فارغ/غير رقميّ ⇒ null — لا تخمين، سابقة parseMeasure). */
function parseMeasure(raw: string): number | null {
  const v = Number(raw);
  return raw.trim() !== '' && Number.isFinite(v) ? v : null;
}

/** 404 من الخادم ⇒ إعلان «غير مُفعَّل» صادق (الميزة غير منشورة على هذا الخادم). */
function DisabledNote() {
  return <div className="text-[11px]" style={{ color: T.muted }}>هذه الميزة غير مُفعَّلة على هذا الخادم.</div>;
}

function NumField(props: {
  id: string; label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; width?: string;
}) {
  return (
    <>
      <label htmlFor={props.id} className="font-bold" style={{ color: T.ink }}>{props.label}</label>
      <input
        id={props.id}
        type="number"
        step="any"
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        placeholder={props.placeholder ?? 'من قياس'}
        className={`${props.width ?? 'w-24'} px-2 py-0.5 rounded-lg text-[11px]`}
        style={inputStyle}
      />
    </>
  );
}

function FactPills({ facts }: { facts: { label: string; value: string }[] }) {
  if (facts.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {facts.map((f) => (
        <span key={f.label} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
          <span style={{ color: T.faint }}>{f.label}:</span> {f.value}
        </span>
      ))}
    </div>
  );
}

/** بطاقة نافذة خطر واحدة — نصوصها كلّها من الخادم (لا يُعاد الحكم على الشدّة/المصدر). */
function PestWindowRow({ w }: { w: PestWindow }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border p-2" style={boxStyle}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-bold" style={{ color: T.ink }}>{w.pest_ar || w.pest || '—'}</span>
        <span className="text-[10px] px-1.5 py-0.5 rounded-full font-semibold" style={{ border: `1px solid ${severityColor(w.severity)}`, color: severityColor(w.severity) }}>
          {severityLabelAr(w.severity)}
        </span>
        <span className="text-[10px]" style={{ color: T.faint }}>الأشهر: {riskMonthsText(w)}</span>
      </div>
      {Array.isArray(w.crops) && w.crops.length > 0 && (
        <div className="text-[10px]" style={{ color: T.muted }}>المحاصيل: {w.crops.join('، ')}</div>
      )}
      {w.scouting_cue_ar && <div className="text-[11px]" style={{ color: T.muted }}>مؤشّر المسح: {w.scouting_cue_ar}</div>}
      {w.source && <div className="text-[10px]" style={{ color: T.faint }}>المصدر: {w.source}</div>}
    </div>
  );
}

/**
 * «المديريّات والطقس والتهيئة»: يعرض طبقة المعرفة الإقليميّة (نوافذ خطر الآفات
 * بمصادرها + الآفات النشطة شهريّاً) · توصية الموقع الجغرافيّ من الإحداثيّات ·
 * ملخّص طقس الحقل (صلاحيّة عمليّات + تنبيهات) وتحليلات سجلّ الطقس ودليل الزراعة ·
 * استبيان التهيئة (أسئلة الخادم ⇒ إرسال صادق «يُرسَل المُدخَل»). الأحكام والنصوص
 * كلّها من الخادم — الواجهة تعرض ولا تحكم؛ 404 ⇒ «غير مُفعَّل» صادقة، والإحداثيّات/
 * السجلّ/الإجابات يُدخِلها المستخدم من مصدر حقيقيّ لا تُخمَّن.
 */
export default function DistrictsWeatherCard({ fieldId, cropLabel, enabled = true }: Props) {
  const [open, setOpen] = useState<SectionKey>('districts');

  // — المديريّات: الفهرس دائماً عند فتح القسم؛ التفصيل والآفات عند الاختيار —
  const indexQ = useDistrictsIndex(enabled && open === 'districts');
  const districts = useMemo(() => districtOptions(indexQ.data), [indexQ.data]);
  const [pickedDistrict, setPickedDistrict] = useState<string | null>(null);
  const [month, setMonth] = useState<number>(new Date().getMonth() + 1);
  const detailQ = useDistrictDetail(pickedDistrict, enabled && open === 'districts');
  const activeQ = useDistrictActivePests(pickedDistrict, month, enabled && open === 'districts');
  const windows = useMemo(() => pestWindows(detailQ.data), [detailQ.data]);
  const active = useMemo(() => activePestsList(activeQ.data), [activeQ.data]);

  // — إحداثيّات مشتركة (توصية الموقع + ملخّص الطقس): موقع الحقل، تُدخَل مرّة —
  const [latInput, setLatInput] = useState('');
  const [lonInput, setLonInput] = useState('');
  const [elevInput, setElevInput] = useState('');
  const lat = useMemo(() => parseMeasure(latInput), [latInput]);
  const lon = useMemo(() => parseMeasure(lonInput), [lonInput]);
  const elevM = useMemo(() => parseMeasure(elevInput), [elevInput]);

  const geoQ = useGeoLocateRecommend(lat, lon, elevM, enabled && open === 'geo');
  const geoFacts = useMemo(() => geoRecommendFacts(geoQ.data), [geoQ.data]);
  const rec = geoQ.data?.recommendation_ar;

  // — ملخّص طقس الحقل + تحليلات السجلّ (JSON يُدخِله المستخدم) —
  const summaryQ = useFieldWeatherSummary(lat, lon, enabled && open === 'weather');
  const ops = useMemo(() => operationRows(summaryQ.data), [summaryQ.data]);
  const alerts = useMemo(() => weatherAlerts(summaryQ.data), [summaryQ.data]);
  const [logInput, setLogInput] = useState('');
  const parsedLog = useMemo(() => parseWeatherRecords(logInput), [logInput]);
  const analyzeQ = useWeatherAnalysis(parsedLog.records, enabled && open === 'weather');
  const guideQ = useWeatherPlantingGuide(parsedLog.records, enabled && open === 'weather');
  const anFacts = useMemo(() => analysisFacts(analyzeQ.data), [analyzeQ.data]);
  const months = useMemo(() => plantingMonths(guideQ.data), [guideQ.data]);

  // — استبيان التهيئة: أسئلة الخادم ⇒ إجابات محليّة ⇒ إرسال صريح بزرّ —
  const questQ = useOnboardingQuestionnaire(null, enabled && open === 'onboarding');
  const sections = useMemo(() => (questQ.data && !isDisabled(questQ.data) ? questQ.data.sections ?? [] : []), [questQ.data]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const setAnswer = (id: string) => (v: string) => setAnswers((p) => ({ ...p, [id]: v }));
  const missing = useMemo(() => missingRequiredIds(questQ.data, answers), [questQ.data, answers]);
  const answered = useMemo(() => answeredCount(answers), [answers]);
  const submitM = useSubmitOnboarding();

  if (!enabled) return null;

  const coordInputs = (prefix: string, withElevation: boolean) => (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
      <MapPin className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-hidden="true" />
      <NumField id={`${prefix}-lat`} label="خطّ العرض:" value={latInput} onChange={setLatInput} placeholder="15.35" width="w-20" />
      <NumField id={`${prefix}-lon`} label="خطّ الطول:" value={lonInput} onChange={setLonInput} placeholder="44.20" width="w-20" />
      {withElevation && (
        <NumField id={`${prefix}-elev`} label="الارتفاع (م، اختياريّ):" value={elevInput} onChange={setElevInput} placeholder="من GPS" width="w-20" />
      )}
    </div>
  );

  const needCoords = lat == null || lon == null;

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="districts-weather" aria-label="المديريّات والطقس والتهيئة">
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Mountain className="w-4 h-4 text-emerald-300" aria-hidden="true" /> المديريّات والطقس والتهيئة
          {cropLabel && <span className="text-[11px]" style={{ color: T.faint }}>· {cropLabel}</span>}
        </span>
      </div>

      {/* أقسام قابلة للطيّ — استعلام كلّ قسم لا يُطلق إلّا عند فتحه (لا استدعاء ميّت). */}
      <div className="flex flex-wrap items-center gap-1.5 mb-2">
        {SECTIONS.map((s) => (
          <button
            key={s.key}
            type="button"
            onClick={() => setOpen(s.key)}
            className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
            style={{
              border: `1px solid ${open === s.key ? '#0c4a6e' : T.line}`,
              color: open === s.key ? '#7dd3fc' : T.muted,
              background: open === s.key ? 'rgba(12,74,110,.25)' : 'rgba(15,23,42,.45)',
            }}
          >
            {s.label_ar}
          </button>
        ))}
      </div>

      {/* ── دليل المديريّات: فهرس ⇒ اختيار ⇒ نوافذ الخطر + الآفات النشطة شهريّاً ── */}
      {open === 'districts' && (
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
          {isDisabled(indexQ.data) ? (
            <DisabledNote />
          ) : indexQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة فهرس المديريّات…</div>
          ) : districts.length === 0 ? (
            <div className="text-[11px]" style={{ color: T.muted }}>لا مديريّات متاحة من الخادم بعد.</div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-1.5">
                {districts.map((d) => (
                  <button
                    key={d.district_id}
                    type="button"
                    onClick={() => setPickedDistrict(pickedDistrict === d.district_id ? null : d.district_id)}
                    className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                    style={{
                      border: `1px solid ${pickedDistrict === d.district_id ? '#14532d' : T.line}`,
                      color: pickedDistrict === d.district_id ? '#86efac' : T.muted,
                      background: pickedDistrict === d.district_id ? 'rgba(20,83,45,.25)' : 'rgba(15,23,42,.45)',
                    }}
                  >
                    {districtLabel(d)}
                  </button>
                ))}
              </div>
              {indexQ.data?.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{indexQ.data.note_ar}</div>}
            </>
          )}

          {!pickedDistrict ? (
            <div className="text-[10px]" style={{ color: T.faint }}>اختر مديريّة لعرض نوافذ خطر الآفات ومصادرها.</div>
          ) : (
            <>
              {/* بطاقة المديريّة (كلّ نوافذ الخطر بمصادرها) */}
              {isDisabled(detailQ.data) ? (
                <DisabledNote />
              ) : detailQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة بطاقة المديريّة…</div>
              ) : detailQ.data ? (
                <div className="flex flex-col gap-1.5">
                  <div className="text-[11px] font-bold" style={{ color: T.ink }}>
                    {detailQ.data.name_ar || detailQ.data.district_id || '—'}
                    {detailQ.data.agro_ecological_zone_ar && (
                      <span className="font-normal" style={{ color: T.faint }}> · {detailQ.data.agro_ecological_zone_ar}</span>
                    )}
                  </div>
                  {windows.length > 0 ? (
                    windows.map((w) => <PestWindowRow key={w.pest} w={w} />)
                  ) : (
                    <div className="text-[11px]" style={{ color: T.muted }}>لا نوافذ خطر مسجّلة لهذه المديريّة.</div>
                  )}
                </div>
              ) : null}

              {/* الآفات النشطة في شهر مختار (lookup مرجعيّ) */}
              <div className="flex flex-wrap items-center gap-1.5 text-[11px] mt-1" style={{ color: T.muted }}>
                <Bug className="w-3.5 h-3.5 shrink-0 text-amber-300" aria-hidden="true" />
                <label htmlFor="dw-month" className="font-bold" style={{ color: T.ink }}>الآفات النشطة في شهر:</label>
                <select id="dw-month" value={month} onChange={(e) => setMonth(Number(e.target.value))} className="px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle}>
                  {monthOptions().map((m) => <option key={m.value} value={m.value}>{m.label_ar}</option>)}
                </select>
              </div>
              {isDisabled(activeQ.data) ? (
                <DisabledNote />
              ) : activeQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة الآفات النشطة…</div>
              ) : active.length > 0 ? (
                <div className="flex flex-col gap-1.5">
                  {active.map((w) => <PestWindowRow key={w.pest} w={w} />)}
                </div>
              ) : (
                <div className="text-[11px]" style={{ color: T.muted }}>لا آفة نشطة تنطبق في {monthNameAr(month)} (قائمة فارغة صادقة).</div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── توصية الموقع الجغرافيّ: تحديد الإقليم + محاصيل ملائمة من الإحداثيّات ── */}
      {open === 'geo' && (
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
          {coordInputs('dw-geo', true)}
          {needCoords ? (
            <div className="text-[10px]" style={{ color: T.faint }}>حدّد موقع الحقل (خطّا العرض/الطول من GPS) لتوصية الإقليم والمحاصيل.</div>
          ) : isDisabled(geoQ.data) ? (
            <DisabledNote />
          ) : geoQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تحديد الموقع والتوصية…</div>
          ) : serverMessage(geoQ.data) ? (
            <div className="text-[11px]" style={{ color: T.muted }}>{serverMessage(geoQ.data)}</div>
          ) : geoQ.data?.supported ? (
            <>
              <FactPills facts={geoFacts} />
              {geoQ.data.zone_source_ar && <div className="text-[10px]" style={{ color: T.faint }}>مصدر التصنيف: {geoQ.data.zone_source_ar}</div>}
              {stringList(rec?.suited_crops_ar ?? geoQ.data.suited_crops_ar).length > 0 && (
                <div className="text-[11px]" style={{ color: T.muted }}>
                  <span style={{ color: '#86efac' }}>محاصيل ملائمة:</span> {stringList(rec?.suited_crops_ar ?? geoQ.data.suited_crops_ar).join('، ')}
                </div>
              )}
              {stringList(rec?.avoid_ar ?? geoQ.data.avoid_ar).length > 0 && (
                <div className="text-[11px]" style={{ color: T.muted }}>
                  <span style={{ color: '#fca5a5' }}>تجنّب:</span> {stringList(rec?.avoid_ar ?? geoQ.data.avoid_ar).join('، ')}
                </div>
              )}
              {rec?.water_note_ar && <div className="text-[11px]" style={{ color: T.muted }}>{rec.water_note_ar}</div>}
              {rec?.next_step_ar && <div className="text-[11px]" style={{ color: T.muted }}>الخطوة التالية: {rec.next_step_ar}</div>}
              {geoQ.data.multi_zone_warning_ar && <div className="text-[10px]" style={{ color: '#fdba74' }}>{geoQ.data.multi_zone_warning_ar}</div>}
              {geoQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{geoQ.data.disclaimer_ar}</div>}
            </>
          ) : null}
        </div>
      )}

      {/* ── طقس الحقل: ملخّص لحظيّ + تحليل سجلّ يوميّ + دليل الزراعة الموسميّ ── */}
      {open === 'weather' && (
        <div className="flex flex-col gap-2 rounded-xl border p-2" style={boxStyle}>
          {/* ملخّص الطقس (يحتاج إحداثيّات) */}
          <div className="flex flex-col gap-1.5">
            <span className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
              <CloudSun className="w-3.5 h-3.5 text-sky-300" aria-hidden="true" /> ملخّص طقس الحقل
            </span>
            {coordInputs('dw-wx', false)}
            {needCoords ? (
              <div className="text-[10px]" style={{ color: T.faint }}>حدّد موقع الحقل (خطّا العرض/الطول) لجلب ملخّص الطقس وصلاحيّة العمليّات.</div>
            ) : isDisabled(summaryQ.data) ? (
              <DisabledNote />
            ) : summaryQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ جلب ملخّص الطقس…</div>
            ) : summaryQ.data?.operations ? (
              <>
                <div className="flex flex-wrap gap-1.5">
                  {ops.map((o) => (
                    <span key={o.operation} className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ border: `1px solid ${suitabilityColor(o.suitability)}`, color: suitabilityColor(o.suitability) }}>
                      {operationLabelAr(o.operation)}: {suitabilityLabelAr(o.suitability)}
                    </span>
                  ))}
                </div>
                {alerts.map((a) => (
                  <div key={a} className="text-[10px]" style={{ color: '#fdba74' }}>⚠ {a}</div>
                ))}
                {summaryQ.data.upstream_error && <div className="text-[10px]" style={{ color: '#fca5a5' }}>تعذّر تحديث المصدر — قد تكون البيانات مخبّأة.</div>}
              </>
            ) : null}
          </div>

          {/* تحليلات سجلّ الطقس (سجلّ يوميّ يُدخِله المستخدم) */}
          <div className="flex flex-col gap-1.5">
            <span className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
              <Sprout className="w-3.5 h-3.5 text-emerald-300" aria-hidden="true" /> تحليل سجلّ الطقس ودليل الزراعة
            </span>
            <label htmlFor="dw-log" className="text-[10px]" style={{ color: T.faint }}>
              الصق سجلّ طقس يوميّ (JSON): مصفوفة عناصر بها date وtemp_max_c وtemp_min_c (واختيارياً precipitation_mm/wind_speed_kmh).
            </label>
            <textarea
              id="dw-log"
              value={logInput}
              onChange={(e) => setLogInput(e.target.value)}
              placeholder='[{"date":"2025-01-01","temp_max_c":28,"temp_min_c":12,"precipitation_mm":0}]'
              rows={3}
              className="w-full px-2 py-1 rounded-lg text-[11px] font-mono"
              style={inputStyle}
            />
            {parsedLog.error_ar && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{parsedLog.error_ar}</div>}

            {parsedLog.records && parsedLog.records.length > 0 && (
              <>
                {/* تحليل السجلّ */}
                {isDisabled(analyzeQ.data) ? (
                  <DisabledNote />
                ) : analyzeQ.isLoading ? (
                  <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تحليل السجلّ…</div>
                ) : serverMessage(analyzeQ.data) ? (
                  <div className="text-[11px]" style={{ color: T.muted }}>{serverMessage(analyzeQ.data)}</div>
                ) : analyzeQ.data?.supported ? (
                  <div className="flex flex-col gap-1">
                    <FactPills facts={anFacts} />
                    {analyzeQ.data.irrigation_dependency_ar && <div className="text-[11px]" style={{ color: T.muted }}>{analyzeQ.data.irrigation_dependency_ar}</div>}
                    {analyzeQ.data.heat_window_ar && <div className="text-[11px]" style={{ color: T.muted }}>{analyzeQ.data.heat_window_ar}</div>}
                    {analyzeQ.data.verdict_ar && <div className="text-[11px]" style={{ color: T.muted }}>{analyzeQ.data.verdict_ar}</div>}
                    {analyzeQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{analyzeQ.data.disclaimer_ar}</div>}
                  </div>
                ) : null}

                {/* دليل الزراعة الموسميّ */}
                {isDisabled(guideQ.data) ? null : guideQ.isLoading ? (
                  <div className="text-[11px]" style={{ color: T.faint }}>جارٍ استخلاص دليل الزراعة…</div>
                ) : serverMessage(guideQ.data) ? (
                  <div className="text-[11px]" style={{ color: T.muted }}>{serverMessage(guideQ.data)}</div>
                ) : guideQ.data?.supported ? (
                  <div className="flex flex-col gap-1">
                    {months.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {months.map((m) => (
                          <span key={m.month} className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ border: `1px solid ${plantingWindowColor(m.window)}`, color: plantingWindowColor(m.window) }}>
                            {m.month_ar} · {m.window_ar}
                          </span>
                        ))}
                      </div>
                    )}
                    {guideQ.data.summary_ar && <div className="text-[11px]" style={{ color: T.muted }}>{guideQ.data.summary_ar}</div>}
                    {guideQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{guideQ.data.disclaimer_ar}</div>}
                  </div>
                ) : null}
              </>
            )}
          </div>
        </div>
      )}

      {/* ── استبيان التهيئة: أسئلة الخادم ⇒ إرسال صادق «يُرسَل المُدخَل» ── */}
      {open === 'onboarding' && (
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
          <span className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
            <ClipboardList className="w-3.5 h-3.5 text-sky-300" aria-hidden="true" /> استبيان تهيئة الحقل
          </span>
          {isDisabled(questQ.data) ? (
            <DisabledNote />
          ) : questQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة الاستبيان…</div>
          ) : sections.length === 0 ? (
            <div className="text-[11px]" style={{ color: T.muted }}>لا استبيان متاح من الخادم بعد.</div>
          ) : (
            <>
              {sections.map((sec) => (
                <div key={sec.id} className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
                  <div className="text-[11px] font-bold" style={{ color: T.ink }}>
                    {sec.title_ar}
                    <span className="font-normal text-[10px]" style={{ color: T.faint }}> · {sec.phase === 1 ? 'إلزاميّ مبدئيّ' : 'تعميق اختياريّ'}</span>
                  </div>
                  {(sec.questions || []).map((q) => (
                    <div key={q.id} className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
                      <label htmlFor={`dw-q-${q.id}`} className="font-bold" style={{ color: T.ink }}>
                        {q.label_ar}{q.required ? <span style={{ color: '#fca5a5' }}> *</span> : null}
                        {q.unit ? <span className="font-normal" style={{ color: T.faint }}> ({q.unit})</span> : null}:
                      </label>
                      {Array.isArray(q.options) && q.options.length > 0 ? (
                        <select
                          id={`dw-q-${q.id}`}
                          value={answers[q.id] ?? ''}
                          onChange={(e) => setAnswer(q.id)(e.target.value)}
                          className="px-2 py-0.5 rounded-lg text-[11px]"
                          style={inputStyle}
                        >
                          <option value="">—</option>
                          {q.options.map((o) => <option key={o} value={o}>{o}</option>)}
                        </select>
                      ) : (
                        <input
                          id={`dw-q-${q.id}`}
                          type={q.type === 'number' ? 'number' : q.type === 'date' ? 'date' : 'text'}
                          step={q.type === 'number' ? 'any' : undefined}
                          value={answers[q.id] ?? ''}
                          onChange={(e) => setAnswer(q.id)(e.target.value)}
                          placeholder={q.hint_ar ?? ''}
                          className="w-40 px-2 py-0.5 rounded-lg text-[11px]"
                          style={inputStyle}
                        />
                      )}
                      {q.hint_ar && <span className="text-[10px]" style={{ color: T.faint }}>{q.hint_ar}</span>}
                    </div>
                  ))}
                </div>
              ))}

              {/* إرسال صادق: نعرض عدد المُجاب والناقص (معاينة عميل)، والحكم النهائيّ من الخادم */}
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={submitM.isPending || fieldId == null}
                  onClick={() => submitM.mutate(buildSubmitPayload(fieldId, answers))}
                  className="text-[11px] px-3 py-1 rounded-lg font-semibold"
                  style={{
                    border: `1px solid ${fieldId == null ? T.line : '#14532d'}`,
                    color: fieldId == null ? T.faint : '#86efac',
                    background: fieldId == null ? 'rgba(15,23,42,.45)' : 'rgba(20,83,45,.25)',
                    opacity: submitM.isPending ? 0.6 : 1,
                  }}
                >
                  {submitM.isPending ? 'جارٍ الإرسال…' : 'إرسال الاستبيان'}
                </button>
                <span className="text-[10px]" style={{ color: T.faint }}>
                  مُجاب: {answered}{missing.length > 0 ? ` · ناقص إلزاميّ: ${missing.length}` : ' · لا ناقص إلزاميّ'}
                </span>
              </div>
              {fieldId == null && <div className="text-[10px]" style={{ color: T.faint }}>اختر حقلاً لربط ردّ الاستبيان به قبل الإرسال.</div>}
              {submitM.isError && <div className="text-[11px]" style={{ color: '#fca5a5' }}>تعذّر إرسال الاستبيان إلى الخادم — أعد المحاولة.</div>}
              {submitM.data && !isDisabled(submitM.data) && (
                <div className="flex flex-col gap-0.5 rounded-xl border p-2" style={boxStyle}>
                  <div className="text-[11px] font-bold" style={{ color: submitM.data.valid ? '#86efac' : '#fdba74' }}>
                    {submitM.data.valid ? 'حُفِظ الردّ مكتملاً.' : 'حُفِظ الردّ (تنقص حقول إلزاميّة).'}
                  </div>
                  <div className="text-[10px]" style={{ color: T.faint }}>عدد المُجاب (الخادم): {submitM.data.answered_count ?? '—'}</div>
                  {Array.isArray(submitM.data.missing_required) && submitM.data.missing_required.length > 0 && (
                    <div className="text-[10px]" style={{ color: '#fdba74' }}>الناقص الإلزاميّ: {submitM.data.missing_required.join('، ')}</div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
