// SeasonEvidenceCard — «بطاقة أدلّة الموسم»: تعرض الحقيقة التشغيليّة الموحّدة للحقل-الموسم
// (field_season_state_projection) كقراءة واحدة: المرحلة، حالة التقويم، GDD/الطور، الإجهاد
// المائيّ، مخاطر الطقس المرحليّة، تعارض الاستشعار، المهام المفتوحة، الثقة، والأدلّة الناقصة.
// صدق: لا اختلاق — الناقص يُعرَض صراحةً (evidence_missing)، والثقة سقفها MEDIUM.

import type { ReactNode } from 'react';
import { useFieldSeasonState } from '../../hooks/useFieldSeasonState';
import type { StageRisk } from '../../lib/fieldSeasonState';

interface Props {
  fieldId?: string | null;
  seasonId?: string | null;
  enabled?: boolean;
}

const SEV_COLOR: Record<string, string> = {
  high: 'bg-red-100 text-red-800 border-red-200',
  medium: 'bg-amber-100 text-amber-800 border-amber-200',
  low: 'bg-stone-100 text-stone-700 border-stone-200',
  none: 'bg-emerald-50 text-emerald-700 border-emerald-200',
};

// «متى» لا «ما الطور». و`insufficient_context` تُقال صراحةً: لا إسقاطَ يُختلَق
// من سياقٍ ناقص، ولا يُقرأ غيابُ الإسقاط سلامةً.
const WINDOW_LABEL: Record<string, string> = {
  upcoming: 'قادمة',
  in_window: 'الحقل داخلها الآن',
  past: 'انقضت حراريّاً',
  insufficient_context: 'لا إسقاط — سياق ناقص',
};

const COLLISION_LABEL: Record<string, string> = {
  collisions: 'تجاوزٌ للعتبة ⚠',
  clear: 'لا تجاوز ضمن الأفق المتاح',
  insufficient_context: 'لا تنبّؤ يوميّ — لا يُقاس ولا يُنفى',
  not_applicable: 'لا نافذة ⇒ لا تصادم',
};

const CAL_LABEL: Record<string, string> = {
  optimal: 'مثاليّ ✓',
  valid: 'داخل النافذة',
  unusual: 'غير معتاد ⚠',
  out_of_window: 'خارج النافذة ✗',
  unknown: 'غير معروف',
};

function Chip({ text, cls }: { text: string; cls: string }) {
  return (
    <span className={`inline-block rounded-full border px-2 py-0.5 text-xs ${cls}`}>{text}</span>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-stone-100 py-1.5 last:border-0">
      <span className="text-xs text-stone-500">{label}</span>
      <span className="text-sm font-medium text-stone-800">{children}</span>
    </div>
  );
}

export default function SeasonEvidenceCard({ fieldId, seasonId, enabled = true }: Props) {
  const { data, isLoading, isError } = useFieldSeasonState(fieldId, seasonId, enabled);

  if (!enabled || !fieldId || !seasonId) return null;

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm" dir="rtl">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-bold text-stone-800">🌱 حالة الموسم (حقيقة تشغيليّة موحّدة)</h3>
        {data && (
          <Chip
            text={`ثقة: ${data.season_confidence === 'medium' ? 'متوسّطة' : 'منخفضة'}`}
            cls={data.season_confidence === 'medium' ? SEV_COLOR.low : SEV_COLOR.medium}
          />
        )}
      </div>

      {isLoading && <p className="text-xs text-stone-400">جارٍ التحميل…</p>}
      {isError && (
        <p className="text-xs text-stone-400">تعذّر جلب حالة الموسم (لا بيانات مُختلَقة).</p>
      )}

      {data && (
        <div className="space-y-1">
          <Row label="المرحلة">
            {data.current_stage_ar ?? data.current_stage ?? '—'}
            {data.stage_source && (
              <span className="mr-1 text-xs text-stone-400">
                ({data.stage_source === 'gdd' ? 'حراريّ' : 'أيّام'})
              </span>
            )}
          </Row>
          <Row label="التقويم">
            <Chip
              text={CAL_LABEL[data.calendar_status ?? 'unknown'] ?? data.calendar_status ?? '—'}
              cls={
                data.calendar_status === 'optimal' || data.calendar_status === 'valid'
                  ? SEV_COLOR.none
                  : SEV_COLOR.medium
              }
            />
          </Row>
          <Row label="الطور (GDD)">
            {data.days_after_sowing != null ? `${data.days_after_sowing} يوماً` : '—'}
            {data.gdd_fraction != null && ` · ${Math.round(data.gdd_fraction * 100)}%`}
            {data.current_kc != null && ` · Kc ${data.current_kc}`}
          </Row>
          <Row label="الإجهاد المائيّ">
            {data.water_deficit_7d_mm != null
              ? `عجز 7ي ${Math.round(data.water_deficit_7d_mm)} مم`
              : '—'}
            {data.water_deficit_14d_mm != null && ` · 14ي ${Math.round(data.water_deficit_14d_mm)} مم`}
          </Row>
          <Row label="مخاطر الطقس (مرحليّة)">
            {data.weather_stage_risks && data.weather_stage_risks.risks.length > 0 ? (
              <span className="flex flex-wrap justify-end gap-1">
                {data.weather_stage_risks.risks.map((r: StageRisk) => (
                  <Chip key={r.code} text={r.code} cls={SEV_COLOR[r.severity] ?? SEV_COLOR.low} />
                ))}
              </span>
            ) : (
              '— لا مخاطر بارزة'
            )}
          </Row>
          <Row label="النافذة الحرجة القادمة">
            {data.critical_window ? (
              <span className="flex flex-col items-end gap-0.5">
                <span className="flex items-center gap-1">
                  <Chip
                    text={WINDOW_LABEL[data.critical_window.status] ?? data.critical_window.status}
                    cls={
                      data.critical_window.status === 'in_window'
                        ? SEV_COLOR.medium
                        : data.critical_window.status === 'upcoming'
                          ? SEV_COLOR.low
                          : SEV_COLOR.none
                    }
                  />
                  {data.critical_window.lead_days != null && (
                    <span>بعد {data.critical_window.lead_days} يوماً</span>
                  )}
                </span>
                {data.critical_window.name_ar && (
                  <span className="text-xs text-stone-500">{data.critical_window.name_ar}</span>
                )}
                {data.critical_window.start_date && (
                  <span className="text-xs text-stone-400">
                    {data.critical_window.start_date}
                    {data.critical_window.end_date && ` ← ${data.critical_window.end_date}`}
                  </span>
                )}
              </span>
            ) : (
              '—'
            )}
          </Row>
          {data.critical_window?.note_ar && (
            <p className="text-[11px] leading-snug text-stone-500">{data.critical_window.note_ar}</p>
          )}

          {data.critical_window_collisions && (
            <>
              <Row label="تصادمٌ داخل النافذة">
                <Chip
                  text={
                    COLLISION_LABEL[data.critical_window_collisions.status] ??
                    data.critical_window_collisions.status
                  }
                  cls={SEV_COLOR[data.critical_window_collisions.max_severity] ?? SEV_COLOR.none}
                />
              </Row>
              {data.critical_window_collisions.events.map((e) => (
                <p
                  key={`${e.code}-${e.lead_days}`}
                  className="rounded-md bg-amber-50 px-2 py-1 text-[11px] leading-snug text-amber-800"
                >
                  {e.reason_ar}
                </p>
              ))}
              {/* العتبةُ تُعرَض بمصدرها وحالة معايرتها — رقمٌ يحجب قراراً بلا أن يقول
                  من أين جاء هو نفسُه ما نستأصله (D5-COVERAGE-CUTOFF-…-01). */}
              <p className="text-[10px] leading-snug text-stone-400">
                العتبة: {data.critical_window_collisions.threshold_source} ·{' '}
                {data.critical_window_collisions.calibration === 'uncalibrated'
                  ? 'غير مُعايَرة محلّيّاً'
                  : data.critical_window_collisions.calibration}
                {data.critical_window_collisions.confidence &&
                  ` · ثقة: ${data.critical_window_collisions.confidence === 'medium' ? 'متوسّطة' : 'منخفضة'}`}
              </p>
              {data.critical_window_collisions.evidence_missing.length > 0 && (
                <div className="flex flex-wrap justify-end gap-1">
                  {data.critical_window_collisions.evidence_missing.map((m) => (
                    <Chip key={m} text={m} cls="bg-stone-50 text-stone-500 border-stone-200" />
                  ))}
                </div>
              )}
            </>
          )}

          <Row label="الاستشعار × المرحلة">
            {data.eo_stage_mismatch ? (
              <Chip
                text={
                  data.eo_stage_mismatch.status === 'below_expected'
                    ? 'أدنى من المتوقّع ⚠'
                    : data.eo_stage_mismatch.status === 'aligned'
                      ? 'متّسق ✓'
                      : data.eo_stage_mismatch.status === 'inconclusive'
                        ? 'غير حاسم'
                        : data.eo_stage_mismatch.status
                }
                cls={
                  data.eo_stage_mismatch.status === 'below_expected'
                    ? SEV_COLOR[data.eo_stage_mismatch.severity] ?? SEV_COLOR.medium
                    : SEV_COLOR.low
                }
              />
            ) : (
              '—'
            )}
          </Row>
          <Row label="المهام المفتوحة">{data.open_operations ?? '—'}</Row>

          {data.requires_review && (
            <p className="mt-2 rounded-md bg-amber-50 px-2 py-1 text-xs text-amber-800">
              ⚠ يحتاج مراجعة — إشارات متقاربة على مشكلة.
            </p>
          )}

          {data.evidence_missing.length > 0 && (
            <div className="mt-2">
              <p className="mb-1 text-xs text-stone-400">أدلّة ناقصة (صدق — لم تُختلَق):</p>
              <div className="flex flex-wrap gap-1">
                {data.evidence_missing.map((m) => (
                  <Chip key={m} text={m} cls="bg-stone-50 text-stone-500 border-stone-200" />
                ))}
              </div>
            </div>
          )}

          <p className="mt-2 text-[10px] leading-snug text-stone-400">{data.disclaimer_ar}</p>
        </div>
      )}
    </div>
  );
}
