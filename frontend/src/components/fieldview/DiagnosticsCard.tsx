import { useMemo, useState } from 'react';
import { Stethoscope, Bug, FlaskConical, ListChecks, ShieldAlert } from 'lucide-react';
import {
  useDiagnose, useDiagnosisSymptoms, useIpmCropPests, useIpmPests, useIpmPlan, useSalinityAssess,
} from '../../hooks/useApi';
import {
  advisoryNotes, buildDiagnosePayload, buildSalinityPayload, categoryLabelAr, categoryTone,
  confidencePct, cropPestMatches, fmtNum, ipmStageTone, planLadder, rankedCandidates,
  salinityRecommendations, serverMessage, sodiumHazardTone, soilSalinityTone,
  supportedPestsList, waterRiskTone,
} from '../../lib/fieldDiagnostics';
import { T, toneColors } from '../ds';

interface Props {
  /** حقل نشط اختياريّ — عند تمريره يُرفِق الخادم مقتطف الحالة الموحّدة (Stage F). */
  fieldId?: string | null;
  /** تسمية محصول الحقل النشط (كما هي في بيانات الحقل). */
  cropLabel?: string | null;
  enabled?: boolean;
}

/** منضدة التشخيص الحقليّ: أعراض مُختارة → مرشّحون مرتّبون من الخادم (لا حكم قاطع —
 *  next_step_ar يُعرَض كما جاء)، خطط IPM المتدرّجة (الكيميائيّ ملاذ أخير) لمحصول
 *  الحقل، وتقييم الملوحة FAO من قياسات المستخدم الفعليّة. الواجهة تعرض ولا تحكم. */
export default function DiagnosticsCard({ fieldId, cropLabel, enabled = true }: Props) {
  // — التشخيص: أعراض من كتالوج الخادم فقط (لا نصّ حرّ — أدقّ للمطابقة) —
  const symptomsQ = useDiagnosisSymptoms(enabled);
  const diagnoseMut = useDiagnose();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [diagError, setDiagError] = useState<string | null>(null);

  // — IPM: آفات محصول الحقل + الآفات المدعومة + خطّة الآفة المُختارة —
  const cropPestsQ = useIpmCropPests(enabled ? (cropLabel || undefined) : undefined);
  const pestsQ = useIpmPests(enabled);
  const [pickedPest, setPickedPest] = useState<string | null>(null);
  const planQ = useIpmPlan(pickedPest);

  // — الملوحة: قياسات المستخدم الحقيقيّة فقط (placeholder «من قياس») —
  const salinityMut = useSalinityAssess();
  const [ece, setEce] = useState('');
  const [ecw, setEcw] = useState('');
  const [sar, setSar] = useState('');
  const [threshold, setThreshold] = useState('');
  const [salError, setSalError] = useState<string | null>(null);

  const symptoms = symptomsQ.data?.symptoms ?? [];
  const candidates = useMemo(() => rankedCandidates(diagnoseMut.data), [diagnoseMut.data]);
  const notes = useMemo(() => advisoryNotes(diagnoseMut.data), [diagnoseMut.data]);
  const cropPests = useMemo(() => cropPestMatches(cropPestsQ.data), [cropPestsQ.data]);
  const allPests = useMemo(() => supportedPestsList(pestsQ.data), [pestsQ.data]);
  const ladder = useMemo(() => planLadder(planQ.data), [planQ.data]);
  const salRecs = useMemo(() => salinityRecommendations(salinityMut.data), [salinityMut.data]);
  const salComponents = salinityMut.data?.supported ? salinityMut.data.components : undefined;

  if (!enabled) return null;

  const toggleSymptom = (code: string) => {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  };

  const runDiagnose = () => {
    const built = buildDiagnosePayload({ crop: cropLabel, symptoms: [...picked], fieldId: fieldId ?? null });
    if (!built.ok) { setDiagError(built.error); return; }
    setDiagError(null);
    diagnoseMut.mutate(built.payload);
  };

  const runSalinity = () => {
    const built = buildSalinityPayload({ eceDsm: ece, ecwDsm: ecw, sar, cropThresholdEce: threshold });
    if (!built.ok) { setSalError(built.error); return; }
    setSalError(null);
    salinityMut.mutate(built.payload);
  };

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="field-diagnostics" aria-label="منضدة التشخيص الحقليّ">
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Stethoscope className="w-4 h-4 text-emerald-300" aria-hidden="true" /> منضدة التشخيص الحقليّ
          {cropLabel && <span className="text-[11px]" style={{ color: T.faint }}>· {cropLabel}</span>}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {/* ١) التشخيص الأوّلي: اختيار أعراض من كتالوج الخادم → مرشّحون مرتّبون */}
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
          <span className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
            <ListChecks className="w-3.5 h-3.5 text-emerald-300" aria-hidden="true" /> الأعراض المرصودة:
          </span>
          {symptomsQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة كتالوج الأعراض…</div>
          ) : symptoms.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {symptoms.map((s) => (
                <button
                  key={s.code}
                  type="button"
                  onClick={() => toggleSymptom(s.code)}
                  className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                  style={{
                    border: `1px solid ${picked.has(s.code) ? '#14532d' : T.line}`,
                    color: picked.has(s.code) ? '#86efac' : T.muted,
                    background: picked.has(s.code) ? 'rgba(20,83,45,.25)' : 'rgba(15,23,42,.45)',
                  }}
                >
                  {s.name_ar}
                </button>
              ))}
            </div>
          ) : (
            <div className="text-[11px]" style={{ color: T.muted }}>لا كتالوج أعراض متاحاً من الخادم بعد.</div>
          )}

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={runDiagnose}
              disabled={diagnoseMut.isPending}
              className="text-[11px] px-3 py-1 rounded-lg font-bold"
              style={{ border: `1px solid ${T.line}`, color: '#86efac', background: 'rgba(20,83,45,.25)' }}
            >
              {diagnoseMut.isPending ? 'جارٍ التشخيص…' : 'شخّص'}
            </button>
            {diagError && <span className="text-[10px]" style={{ color: '#fdba74' }}>{diagError}</span>}
            {diagnoseMut.isError && <span className="text-[10px]" style={{ color: '#fdba74' }}>تعذّر الوصول لخدمة التشخيص — أعد المحاولة.</span>}
          </div>

          {diagnoseMut.data && (
            <div className="flex flex-col gap-1.5">
              {candidates.length > 0 ? candidates.map((c) => {
                const tc = toneColors(categoryTone(c.category));
                return (
                  <div key={c.issue_code} className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
                    <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ color: tc.fg, background: tc.bg }}>
                      {categoryLabelAr(c.category)}
                    </span>
                    <span className="font-bold" style={{ color: T.ink }}>{c.name_ar}</span>
                    <span style={{ color: T.faint }}>ثقة {confidencePct(c.confidence)}</span>
                    <span className="text-[10px]" style={{ color: T.faint }}>{c.matched_ar}</span>
                  </div>
                );
              }) : (
                <div className="text-[11px]" style={{ color: T.muted }}>لا مرشّحين مطابقين — انظر الخطوة التالية أدناه.</div>
              )}
              {/* حكم الخادم الصادق (لا قاطع — يوصي بتأكيد بشريّ/مختبر) يمرّ حرفيّاً */}
              <div className="text-[11px]" style={{ color: T.ink }}>{diagnoseMut.data.next_step_ar}</div>
              {notes.map((n) => (
                <div key={n} className="text-[10px]" style={{ color: '#fdba74' }}>⚠ {n}</div>
              ))}
              {diagnoseMut.data.field_state?.execution_mode && (
                <div className="text-[10px]" style={{ color: T.faint }}>
                  وضع تنفيذ الحقل (الحالة الموحّدة): {diagnoseMut.data.field_state.execution_mode}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ٢) IPM: آفات محصول الحقل المحتملة + الآفات المدعومة → خطّة متدرّجة */}
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
          <span className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
            <Bug className="w-3.5 h-3.5 text-amber-300" aria-hidden="true" /> الإدارة المتكاملة للآفات (IPM):
          </span>

          {cropLabel && (
            cropPestsQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة آفات المحصول…</div>
            ) : serverMessage(cropPestsQ.data) ? (
              <div className="text-[11px]" style={{ color: T.muted }}>{serverMessage(cropPestsQ.data)}</div>
            ) : cropPests.length > 0 ? (
              <div className="flex flex-col gap-1">
                <div className="text-[11px]" style={{ color: T.muted }}>
                  آفات محتملة لـ<span className="font-bold" style={{ color: T.ink }}>{cropPestsQ.data?.crop_ar ?? cropLabel}</span>:
                </div>
                {cropPests.map((p) => (
                  <div key={p.pest} className="text-[11px]" style={{ color: T.muted }}>
                    • <span className="font-bold" style={{ color: T.ink }}>{p.name_ar}</span> — {p.severity_ar}
                  </div>
                ))}
                {cropPestsQ.data?.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{cropPestsQ.data.note_ar}</div>}
              </div>
            ) : null
          )}

          {pestsQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة الآفات المدعومة…</div>
          ) : allPests.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] font-bold" style={{ color: T.ink }}>الخطط المتاحة:</span>
              {allPests.map((p) => (
                <button
                  key={p.pest}
                  type="button"
                  onClick={() => setPickedPest(pickedPest === p.pest ? null : p.pest)}
                  className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                  style={{
                    border: `1px solid ${pickedPest === p.pest ? '#92400e' : T.line}`,
                    color: pickedPest === p.pest ? '#fcd34d' : T.muted,
                    background: pickedPest === p.pest ? 'rgba(146,64,14,.25)' : 'rgba(15,23,42,.45)',
                  }}
                >
                  {p.name_ar}
                </button>
              ))}
            </div>
          ) : (
            <div className="text-[11px]" style={{ color: T.muted }}>لا آفات مدعومة بخطط IPM من الخادم بعد.</div>
          )}

          {pickedPest && (
            planQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة خطّة الإدارة…</div>
            ) : serverMessage(planQ.data) ? (
              <div className="text-[11px]" style={{ color: T.muted }}>{serverMessage(planQ.data)}</div>
            ) : planQ.data?.supported ? (
              <div className="flex flex-col gap-1 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
                <div className="text-[11px] font-bold" style={{ color: T.ink }}>
                  {planQ.data.name_ar ?? '—'}
                  {planQ.data.scientific && <span className="font-normal italic" style={{ color: T.faint }}> ({planQ.data.scientific})</span>}
                </div>
                {planQ.data.severity_ar && <div className="text-[11px]" style={{ color: T.muted }}>الخطورة: {planQ.data.severity_ar}</div>}
                {ladder.map((s) => {
                  const tc = toneColors(ipmStageTone(s.stage));
                  return (
                    <div key={s.stage} className="flex flex-col gap-0.5">
                      <span className="self-start text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ color: tc.fg, background: tc.bg }}>
                        {s.stage_ar}
                      </span>
                      {s.actions_ar.map((a) => (
                        <div key={a} className="text-[11px] pr-2" style={{ color: T.muted }}>• {a}</div>
                      ))}
                    </div>
                  );
                })}
                {planQ.data.economic_threshold_ar && (
                  <div className="text-[11px]" style={{ color: T.muted }}>
                    <span className="font-bold" style={{ color: T.ink }}>العتبة الاقتصاديّة:</span> {planQ.data.economic_threshold_ar}
                  </div>
                )}
                {planQ.data.philosophy_ar && <div className="text-[10px]" style={{ color: T.faint }}>{planQ.data.philosophy_ar}</div>}
                {planQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{planQ.data.disclaimer_ar}</div>}
              </div>
            ) : null
          )}
        </div>

        {/* ٣) الملوحة: قياسات المستخدم (ECe/ECw/SAR + عتبة المحصول) → أحكام FAO خادميّة */}
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
          <span className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
            <FlaskConical className="w-3.5 h-3.5 text-amber-300" aria-hidden="true" /> تقييم الملوحة (من قياسات مختبريّة):
          </span>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            {([
              ['diag-ece', 'ECe تربة (dS/m)', ece, setEce],
              ['diag-ecw', 'ECw ماء (dS/m)', ecw, setEcw],
              ['diag-sar', 'SAR', sar, setSar],
              ['diag-threshold', 'عتبة المحصول ECe', threshold, setThreshold],
            ] as const).map(([id, label, value, setter]) => (
              <span key={id} className="inline-flex items-center gap-1">
                <label htmlFor={id} className="font-bold" style={{ color: T.ink }}>{label}:</label>
                <input
                  id={id}
                  type="number"
                  min="0"
                  step="0.1"
                  value={value}
                  onChange={(e) => setter(e.target.value)}
                  placeholder="من قياس"
                  className="w-20 px-2 py-0.5 rounded-lg text-[11px]"
                  style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }}
                />
              </span>
            ))}
            <button
              type="button"
              onClick={runSalinity}
              disabled={salinityMut.isPending}
              className="text-[11px] px-3 py-1 rounded-lg font-bold"
              style={{ border: `1px solid ${T.line}`, color: '#fcd34d', background: 'rgba(146,64,14,.25)' }}
            >
              {salinityMut.isPending ? 'جارٍ التقييم…' : 'قيّم'}
            </button>
          </div>
          {salError && <div className="text-[10px]" style={{ color: '#fdba74' }}>{salError}</div>}
          {salinityMut.isError && <div className="text-[10px]" style={{ color: '#fdba74' }}>تعذّر الوصول لخدمة تقييم الملوحة — أعد المحاولة.</div>}
          {serverMessage(salinityMut.data) && (
            <div className="text-[11px]" style={{ color: T.muted }}>{serverMessage(salinityMut.data)}</div>
          )}

          {salComponents && (
            <div className="flex flex-col gap-1.5">
              {salComponents.soil_salinity && (() => {
                const c = salComponents.soil_salinity;
                const tc = toneColors(soilSalinityTone(c.class));
                return (
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
                    <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ color: tc.fg, background: tc.bg }}>
                      تربة: {c.class_ar}
                    </span>
                    <span style={{ color: T.faint }}>ECe {fmtNum(c.ece_dsm, 1)}</span>
                    <span>{c.effect_ar}</span>
                  </div>
                );
              })()}
              {salComponents.water_salinity && (() => {
                const c = salComponents.water_salinity;
                const tc = toneColors(waterRiskTone(c.risk));
                return (
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
                    <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ color: tc.fg, background: tc.bg }}>
                      ماء الريّ: {c.risk_ar}
                    </span>
                    <span style={{ color: T.faint }}>ECw {fmtNum(c.ecw_dsm, 1)}</span>
                    <span>{c.note_ar}</span>
                  </div>
                );
              })()}
              {salComponents.sodium_hazard && (() => {
                const c = salComponents.sodium_hazard;
                const tc = toneColors(sodiumHazardTone(c.class));
                return (
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
                    <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ color: tc.fg, background: tc.bg }}>
                      صوديوم: {c.class_ar}
                    </span>
                    <span style={{ color: T.faint }}>SAR {fmtNum(c.sar, 1)}</span>
                    <span>{c.effect_ar} {c.remedy_ar}</span>
                  </div>
                );
              })()}
              {salComponents.leaching && (
                <div className="text-[11px]" style={{ color: T.muted }}>
                  <span className="font-bold" style={{ color: T.ink }}>احتياج الغسيل:</span>{' '}
                  {salComponents.leaching.feasible
                    ? `${fmtNum(salComponents.leaching.leaching_pct, 1)}٪ — ${salComponents.leaching.advice_ar ?? '—'}`
                    : (salComponents.leaching.message_ar ?? '—')}
                  {salComponents.leaching.yemen_note_ar && (
                    <div className="text-[10px]" style={{ color: T.faint }}>{salComponents.leaching.yemen_note_ar}</div>
                  )}
                </div>
              )}
              {salRecs.length > 0 && (
                <div className="flex flex-col gap-0.5">
                  <span className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
                    <ShieldAlert className="w-3.5 h-3.5 text-amber-300" aria-hidden="true" /> التوصيات:
                  </span>
                  {salRecs.map((r) => (
                    <div key={r} className="text-[11px]" style={{ color: T.muted }}>• {r}</div>
                  ))}
                </div>
              )}
              {salinityMut.data?.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{salinityMut.data.disclaimer_ar}</div>}
              {salinityMut.data?.yemen_context_ar && <div className="text-[10px]" style={{ color: T.faint }}>{salinityMut.data.yemen_context_ar}</div>}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
