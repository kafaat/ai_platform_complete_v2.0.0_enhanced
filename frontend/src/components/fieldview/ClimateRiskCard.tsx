import { useState } from 'react';
import { CloudSun, Droplets, Snowflake, Globe2, AlertTriangle } from 'lucide-react';
import {
  useChillHoursEstimate,
  useClimateAnalogRegions,
  useSeasonalRiskCalendar,
  useWaterSensitivityCalendar,
} from '../../hooks/useApi';
import {
  SENSITIVITY_COLOR,
  SEVERITY_COLOR,
  ZONE_OPTIONS,
  analogRows,
  chillCropFit,
  chillFacts,
  hazardRows,
  waterCalendarFacts,
  waterStageRows,
} from '../../lib/fieldClimateRisk';
import { T } from '../ds';

interface Props {
  /** الحقل النشط — البطاقة لا تُعرَض بدونه. */
  fieldId?: string | null;
  /** تسمية محصول الحقل (كما هي في بيانات الحقل) — تُفعِّل التقويم المائي. */
  cropLabel?: string | null;
  enabled?: boolean;
}

/** بطاقة مخاطر المناخ والماء: الحساسيّة المائيّة للمراحل (FAO-56) + نوافذ المخاطر
 *  الموسميّة وساعات البرودة للإقليم + المناطق العالميّة المشابهة مناخيّاً — قدرات
 *  خلفيّة كانت بلا قارئ واجهة. صدق: أحكام الخادم (sensitivity/severity/verdict)
 *  تُعرَض كما هي، الإقليم اختيار يدويّ صريح (لا استنتاج آليّ من الموقع)،
 *  وdisclaimer_ar/note_ar من الخادم تُعرَض حرفيّاً. */
export default function ClimateRiskCard({ fieldId, cropLabel, enabled = true }: Props) {
  const [zone, setZone] = useState<string | null>(null);
  const [showAnalogs, setShowAnalogs] = useState(false);

  const waterQ = useWaterSensitivityCalendar(cropLabel ?? null, enabled && !!fieldId);
  const riskQ = useSeasonalRiskCalendar(zone, enabled && !!fieldId);
  const chillQ = useChillHoursEstimate(zone, enabled && !!fieldId);
  const analogsQ = useClimateAnalogRegions(enabled && !!fieldId && showAnalogs);

  if (!enabled || !fieldId) return null;

  const water = waterQ.data ?? null;
  const waterFacts = waterCalendarFacts(water);
  const stages = waterStageRows(water);
  const risk = riskQ.data ?? null;
  const hazards = hazardRows(risk);
  const chill = chillQ.data ?? null;
  const chillFit = chillCropFit(chill);
  const analogs = analogRows(analogsQ.data ?? null);

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="climate-risk" aria-label="مخاطر المناخ والماء">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <CloudSun className="w-4 h-4 text-emerald-300" aria-hidden="true" /> مخاطر المناخ والماء
          {cropLabel && <span className="text-[11px]" style={{ color: T.faint }}>· {cropLabel}</span>}
        </span>
        <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.faint }}>
          إرشاد توجيهي — لا تنبّؤ يومي
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {/* ── الحساسيّة المائيّة لمراحل محصول الحقل (FAO-56 + سياق يمنيّ) ── */}
        {!cropLabel ? (
          <div className="text-[11px]" style={{ color: T.faint }}>حدّد محصول الحقل لعرض تقويمه المائي.</div>
        ) : waterQ.isLoading ? (
          <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة التقويم المائي…</div>
        ) : water && !water.supported ? (
          <div className="text-[11px]" style={{ color: T.muted }}>{water.message_ar ?? 'لا بيانات حساسيّة مائيّة لهذا المحصول.'}</div>
        ) : water ? (
          <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }} data-testid="climate-risk-water">
            <div className="inline-flex items-center gap-1.5 text-[11px] font-bold" style={{ color: T.ink }}>
              <Droplets className="w-3.5 h-3.5 text-sky-300" aria-hidden="true" />
              الحساسيّة المائيّة — {water.crop_ar ?? cropLabel}
            </div>
            {waterFacts.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {waterFacts.map((f) => (
                  <span key={f.label} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                    <span style={{ color: T.faint }}>{f.label}:</span> {f.value}
                  </span>
                ))}
              </div>
            )}
            {stages.length > 0 && (
              <div className="flex flex-col gap-1">
                {stages.map((s) => (
                  <div key={s.key} className="flex items-start gap-1.5 text-[11px]" style={{ color: T.muted }}>
                    <span className="shrink-0 font-bold" style={{ color: SENSITIVITY_COLOR[s.tone] }}>
                      {s.label_ar ?? s.sensitivity ?? '—'}
                    </span>
                    <span>
                      <span className="font-bold" style={{ color: T.ink }}>{s.name_ar}</span>
                      {s.share_pct != null ? ` · ~${s.share_pct}٪ من الاحتياج` : ''}
                      {s.is_critical_window ? ' · نافذة حرجة' : ''}
                      {s.note_ar ? <span style={{ color: T.faint }}> — {s.note_ar}</span> : null}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {water.yemen_context_ar && <div className="text-[10px]" style={{ color: T.faint }}>{water.yemen_context_ar}</div>}
            {water.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{water.disclaimer_ar}</div>}
          </div>
        ) : null}

        {/* ── اختيار الإقليم — يدويّ صريح (لا يُستنتج آليّاً من الموقع) ── */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-bold" style={{ color: T.ink }}>إقليم الحقل:</span>
          {ZONE_OPTIONS.map((z) => (
            <button
              key={z.key}
              type="button"
              onClick={() => setZone(zone === z.key ? null : z.key)}
              className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
              style={{
                border: `1px solid ${zone === z.key ? '#14532d' : T.line}`,
                color: zone === z.key ? '#86efac' : T.muted,
                background: zone === z.key ? 'rgba(20,83,45,.25)' : 'rgba(15,23,42,.45)',
              }}
            >
              {z.ar}
            </button>
          ))}
        </div>

        {!zone ? (
          <div className="text-[10px]" style={{ color: T.faint }}>
            اختر إقليم الحقل يدويّاً لعرض نوافذ المخاطر الموسميّة وساعات البرودة (اختيار المستخدم، لا استنتاج آليّ).
          </div>
        ) : (
          <>
            {/* ── نوافذ المخاطر المناخيّة الموسميّة للإقليم ── */}
            {riskQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة مخاطر الإقليم…</div>
            ) : risk && !risk.supported ? (
              <div className="text-[11px]" style={{ color: T.muted }}>{risk.message_ar ?? 'لا بيانات مخاطر لهذا الإقليم.'}</div>
            ) : risk ? (
              <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }} data-testid="climate-risk-hazards">
                <div className="inline-flex items-center gap-1.5 text-[11px] font-bold" style={{ color: T.ink }}>
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-300" aria-hidden="true" />
                  نوافذ المخاطر — {risk.zone_name_ar ?? '—'}
                </div>
                {hazards.length === 0 ? (
                  <div className="text-[11px]" style={{ color: T.muted }}>لا مخاطر موسميّة مسجَّلة لهذا الإقليم.</div>
                ) : (
                  hazards.map((h) => (
                    <div key={h.hazard_ar} className="flex items-start gap-1.5 text-[11px]" style={{ color: T.muted }}>
                      <span className="mt-1 w-2 h-2 rounded-full shrink-0" style={{ background: SEVERITY_COLOR[h.tone] }} aria-hidden="true" />
                      <span>
                        <span className="font-bold" style={{ color: T.ink }}>{h.hazard_ar}</span>
                        {h.season_ar ? ` · ${h.season_ar}` : ''}
                        {h.risk_to_ar ? <span style={{ color: T.faint }}> — يهدّد: {h.risk_to_ar}</span> : null}
                      </span>
                    </div>
                  ))
                )}
                {risk.advice_ar && <div className="text-[11px]" style={{ color: T.ink }}>{risk.advice_ar}</div>}
                {risk.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{risk.disclaimer_ar}</div>}
              </div>
            ) : null}

            {/* ── ساعات البرودة (للأشجار المتساقطة) — حكم الخادم يُعرَض كما هو ── */}
            {chillQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تقدير ساعات البرودة…</div>
            ) : chill && !chill.supported ? (
              <div className="text-[11px]" style={{ color: T.muted }}>{chill.message_ar ?? 'لا تقدير برودة لهذا الإقليم.'}</div>
            ) : chill ? (
              <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }} data-testid="climate-risk-chill">
                <div className="inline-flex items-center gap-1.5 text-[11px] font-bold" style={{ color: T.ink }}>
                  <Snowflake className="w-3.5 h-3.5 text-sky-300" aria-hidden="true" /> ساعات البرودة
                </div>
                {chillFacts(chill).length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {chillFacts(chill).map((f) => (
                      <span key={f.label} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                        <span style={{ color: T.faint }}>{f.label}:</span> {f.value}
                      </span>
                    ))}
                  </div>
                )}
                {chill.verdict_ar && <div className="text-[11px]" style={{ color: T.muted }}>{chill.verdict_ar}</div>}
                {chillFit.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {chillFit.map((c) => (
                      <span
                        key={c.crop_ar}
                        className="text-[10px] px-2 py-0.5 rounded-full"
                        style={{ border: `1px solid ${T.line}`, color: c.satisfied ? '#86efac' : '#fca5a5' }}
                      >
                        {c.crop_ar} ({c.need_hours} س) {c.satisfied ? '✓' : '✗'}
                      </span>
                    ))}
                  </div>
                )}
                {chill.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{chill.disclaimer_ar}</div>}
              </div>
            ) : null}
          </>
        )}

        {/* ── المناطق العالميّة المشابهة مناخيّاً — جلب عند الطلب ── */}
        <button
          type="button"
          onClick={() => setShowAnalogs(!showAnalogs)}
          className="self-start inline-flex items-center gap-1.5 text-[11px] font-semibold px-2 py-0.5 rounded-full"
          style={{ border: `1px solid ${T.line}`, color: showAnalogs ? '#86efac' : T.muted, background: 'rgba(15,23,42,.45)' }}
          data-testid="climate-risk-analogs-toggle"
        >
          <Globe2 className="w-3.5 h-3.5" aria-hidden="true" />
          المناطق المشابهة عالميّاً {showAnalogs ? '▴' : '▾'}
        </button>
        {showAnalogs && (
          analogsQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة المناطق المشابهة…</div>
          ) : analogs.length === 0 ? (
            <div className="text-[11px]" style={{ color: T.muted }}>لا مناطق مشابهة متاحة.</div>
          ) : (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }} data-testid="climate-risk-analogs">
              {analogs.map((r) => (
                <div key={r.region_ar} className="text-[11px]" style={{ color: T.muted }}>
                  <span className="font-bold" style={{ color: T.ink }}>{r.region_ar}</span>
                  {r.country_ar ? ` (${r.country_ar})` : ''} · تشابه {r.similarity_pct != null ? `${r.similarity_pct}٪` : '—'}
                  {r.relevance_ar ? <span style={{ color: T.faint }}> — {r.relevance_ar}</span> : null}
                  {r.proven_crops_ar.length > 0 && (
                    <div className="text-[10px]" style={{ color: T.faint }}>محاصيل مثبتة: {r.proven_crops_ar.join(' · ')}</div>
                  )}
                </div>
              ))}
              {analogsQ.data?.principle_ar && <div className="text-[10px]" style={{ color: T.faint }}>{analogsQ.data.principle_ar}</div>}
              {analogsQ.data?.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{analogsQ.data.disclaimer_ar}</div>}
            </div>
          )
        )}
      </div>
    </section>
  );
}
