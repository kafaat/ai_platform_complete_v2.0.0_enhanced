import { useMemo, useState } from 'react';
import { CloudRain, Droplets, Landmark, Waves } from 'lucide-react';
import {
  useIrrigationMethodProfiles,
  useWaterHarvestMethodGuide,
  useWaterHarvestPotential,
  useWaterHarvestingMethods,
} from '../../hooks/useApi';
import {
  guideBenefits,
  irrigationProfiles,
  methodPills,
  potentialFacts,
  profileFacts,
  serverMessage,
} from '../../lib/waterHarvesting';
import { T } from '../ds';

interface Props {
  /** تسمية محصول الحقل النشط — سياق عرض فقط (المحرّكان محايدا المحصول). */
  cropLabel?: string | null;
  enabled?: boolean;
}

// أسطح الالتقاط التي يعرفها الخادم (_RUNOFF_COEFF) — القيم مفاتيح API، التسمية عرض.
const SURFACES: { key: string; label_ar: string }[] = [
  { key: 'roof', label_ar: 'سطح مبنى' },
  { key: 'compacted', label_ar: 'أرض مدكوكة' },
  { key: 'natural', label_ar: 'أرض طبيعيّة' },
  { key: 'terrace', label_ar: 'مدرّجات' },
];

/** «من أين يأتي الماء؟»: إمكانات حصاد الأمطار (من قياسَي مساحة/مطر يُدخِلهما
 *  المستخدم) + الطرق التراثيّة اليمنيّة ودليلها + ملامح طرق الريّ (كفاءات FAO
 *  موسومة غير معايَرة). الأحكام والنصوص كلّها من الخادم — الواجهة تعرض ولا تحكم. */
export default function WaterHarvestingCard({ cropLabel, enabled = true }: Props) {
  // — قياسات المستخدم (لا تخمين): مساحة سطح الالتقاط + المطر السنويّ —
  const [areaInput, setAreaInput] = useState('');
  const [rainInput, setRainInput] = useState('');
  const [surface, setSurface] = useState('roof');
  const areaM2 = useMemo(() => {
    const v = Number(areaInput);
    return areaInput.trim() !== '' && Number.isFinite(v) ? v : null;
  }, [areaInput]);
  const rainMm = useMemo(() => {
    const v = Number(rainInput);
    return rainInput.trim() !== '' && Number.isFinite(v) ? v : null;
  }, [rainInput]);

  const potentialQ = useWaterHarvestPotential(areaM2, rainMm, surface, enabled);
  const methodsQ = useWaterHarvestingMethods(enabled);
  const [pickedMethod, setPickedMethod] = useState<string | null>(null);
  const guideQ = useWaterHarvestMethodGuide(pickedMethod);
  const irrigationQ = useIrrigationMethodProfiles(enabled);
  const [pickedIrrigation, setPickedIrrigation] = useState<string | null>(null);

  const pFacts = useMemo(() => potentialFacts(potentialQ.data), [potentialQ.data]);
  const pills = useMemo(() => methodPills(methodsQ.data), [methodsQ.data]);
  const benefits = useMemo(() => guideBenefits(guideQ.data), [guideQ.data]);
  const profiles = useMemo(() => irrigationProfiles(irrigationQ.data), [irrigationQ.data]);
  const pickedProfile = profiles.find((p) => p.method === pickedIrrigation) ?? null;
  const irrFacts = useMemo(() => profileFacts(pickedProfile), [pickedProfile]);

  if (!enabled) return null;

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="water-harvesting" aria-label="حصاد المياه وطريقة الريّ">
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Droplets className="w-4 h-4 text-sky-300" aria-hidden="true" /> حصاد المياه وطريقة الريّ
          {cropLabel && <span className="text-[11px]" style={{ color: T.faint }}>· {cropLabel}</span>}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {/* إمكانات الحصاد — قياسات حقيقيّة من المستخدم، الحكم من الخادم */}
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <CloudRain className="w-3.5 h-3.5 shrink-0 text-sky-300" aria-hidden="true" />
            <label htmlFor="wh-area" className="font-bold" style={{ color: T.ink }}>مساحة الالتقاط (م²):</label>
            <input
              id="wh-area"
              type="number"
              min="0"
              step="1"
              value={areaInput}
              onChange={(e) => setAreaInput(e.target.value)}
              placeholder="من قياس"
              className="w-20 px-2 py-0.5 rounded-lg text-[11px]"
              style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }}
            />
            <label htmlFor="wh-rain" className="font-bold" style={{ color: T.ink }}>المطر السنويّ (مم):</label>
            <input
              id="wh-rain"
              type="number"
              min="0"
              step="1"
              value={rainInput}
              onChange={(e) => setRainInput(e.target.value)}
              placeholder="من قياس"
              className="w-20 px-2 py-0.5 rounded-lg text-[11px]"
              style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }}
            />
            <label htmlFor="wh-surface" className="font-bold" style={{ color: T.ink }}>السطح:</label>
            <select
              id="wh-surface"
              value={surface}
              onChange={(e) => setSurface(e.target.value)}
              className="px-2 py-0.5 rounded-lg text-[11px]"
              style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }}
            >
              {SURFACES.map((s) => (
                <option key={s.key} value={s.key}>{s.label_ar}</option>
              ))}
            </select>
          </div>

          {areaM2 == null || rainMm == null ? (
            <div className="text-[10px]" style={{ color: T.faint }}>أدخِل مساحة الالتقاط والمطر السنويّ (من قياس) لتقدير الإمكانات.</div>
          ) : potentialQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تقدير إمكانات الحصاد…</div>
          ) : serverMessage(potentialQ.data) ? (
            <div className="text-[11px]" style={{ color: T.muted }}>{serverMessage(potentialQ.data)}</div>
          ) : potentialQ.data?.supported ? (
            <>
              {pFacts.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {pFacts.map((f) => (
                    <span key={f.label} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                      <span style={{ color: T.faint }}>{f.label}:</span> {f.value}
                    </span>
                  ))}
                </div>
              )}
              {potentialQ.data.advice_ar && <div className="text-[11px]" style={{ color: T.muted }}>{potentialQ.data.advice_ar}</div>}
              {potentialQ.data.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{potentialQ.data.note_ar}</div>}
            </>
          ) : null}
        </div>

        {/* طرق الحصاد التراثيّة — قائمة الخادم، والدليل عند الاختيار */}
        {methodsQ.isLoading ? (
          <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة طرق حصاد المياه…</div>
        ) : pills.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
              <Landmark className="w-3.5 h-3.5 text-emerald-300" aria-hidden="true" /> الطرق:
            </span>
            {pills.map((m) => (
              <button
                key={m.method}
                type="button"
                onClick={() => setPickedMethod(pickedMethod === m.method ? null : m.method)}
                className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                style={{
                  border: `1px solid ${pickedMethod === m.method ? '#14532d' : T.line}`,
                  color: pickedMethod === m.method ? '#86efac' : T.muted,
                  background: pickedMethod === m.method ? 'rgba(20,83,45,.25)' : 'rgba(15,23,42,.45)',
                }}
              >
                {m.name_ar}
              </button>
            ))}
          </div>
        ) : (
          <div className="text-[11px]" style={{ color: T.muted }}>لا طرق حصاد متاحة من الخادم بعد.</div>
        )}

        {pickedMethod && (
          guideQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة دليل الطريقة…</div>
          ) : serverMessage(guideQ.data) ? (
            <div className="text-[11px]" style={{ color: T.muted }}>{serverMessage(guideQ.data)}</div>
          ) : guideQ.data?.supported ? (
            <div className="flex flex-col gap-1 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
              <div className="text-[11px] font-bold" style={{ color: T.ink }}>
                {guideQ.data.name_ar ?? '—'}
                {guideQ.data.best_for_ar && <span className="font-normal" style={{ color: T.faint }}> · الأنسب: {guideQ.data.best_for_ar}</span>}
              </div>
              {guideQ.data.what_ar && <div className="text-[11px]" style={{ color: T.muted }}>{guideQ.data.what_ar}</div>}
              {benefits.map((b) => (
                <div key={b} className="text-[11px]" style={{ color: T.muted }}>• {b}</div>
              ))}
              {guideQ.data.caution_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>⚠ {guideQ.data.caution_ar}</div>}
              {guideQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{guideQ.data.disclaimer_ar}</div>}
            </div>
          ) : null
        )}

        {/* ملامح طرق الريّ — كفاءات FAO من الخادم (calibrated=false تُعرَض تحذيراتها) */}
        {irrigationQ.isLoading ? (
          <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة ملامح طرق الريّ…</div>
        ) : profiles.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
              <Waves className="w-3.5 h-3.5 text-sky-300" aria-hidden="true" /> طرق الريّ:
            </span>
            {profiles.map((p) => (
              <button
                key={p.method}
                type="button"
                onClick={() => setPickedIrrigation(pickedIrrigation === p.method ? null : p.method)}
                className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                style={{
                  border: `1px solid ${pickedIrrigation === p.method ? '#0c4a6e' : T.line}`,
                  color: pickedIrrigation === p.method ? '#7dd3fc' : T.muted,
                  background: pickedIrrigation === p.method ? 'rgba(12,74,110,.25)' : 'rgba(15,23,42,.45)',
                }}
              >
                {p.method_ar}
              </button>
            ))}
          </div>
        ) : (
          <div className="text-[11px]" style={{ color: T.muted }}>لا ملامح طرق ريّ متاحة من الخادم بعد.</div>
        )}

        {pickedProfile && (
          <div className="flex flex-col gap-1 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
            {irrFacts.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {irrFacts.map((f) => (
                  <span key={f.label} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                    <span style={{ color: T.faint }}>{f.label}:</span> {f.value}
                  </span>
                ))}
              </div>
            )}
            {(pickedProfile.warnings_ar ?? []).map((w) => (
              <div key={w} className="text-[10px]" style={{ color: '#fdba74' }}>⚠ {w}</div>
            ))}
          </div>
        )}

        {methodsQ.data?.principle_ar && <div className="text-[10px]" style={{ color: T.faint }}>{methodsQ.data.principle_ar}</div>}
        {methodsQ.data?.yemen_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{methodsQ.data.yemen_note_ar}</div>}
      </div>
    </section>
  );
}
