import { SprayCan, AlertTriangle, ShieldCheck } from 'lucide-react';
import { useMemo } from 'react';
import { useFields } from '../../hooks/useApi';
import { useFieldDriftRisk } from '../../hooks/useFieldDriftRisk';
import { neighborZones, type FieldLike, type DriftRiskResponse } from '../../lib/driftZones';
import { T } from '../ds';

interface Props {
  fieldId?: string | null;
  enabled?: boolean;
}

/** بطاقة خطر انجراف الرشّ (V79-UI): يشتقّ الحقول المجاورة كمناطق حسّاسة، ويقيّم إن كان
 *  الرشّ الآن ينجرف نحوها (downwind من الريح السائدة). صدق: بلا ريح ⇒ unknown؛ بلا جوار
 *  ⇒ يُعلَن؛ القرار النهائيّ ميدانيّ (تقدير محافظ من نقطة /wind/drift-risk). */
export default function DriftRiskCard({ fieldId, enabled = true }: Props) {
  const fieldsQ = useFields();
  const zones = useMemo(
    () => neighborZones(fieldsQ.data as FieldLike[] | undefined, fieldId, 2),
    [fieldsQ.data, fieldId],
  );
  const q = useFieldDriftRisk(fieldId, zones, enabled);
  if (!enabled || !fieldId) return null;
  const data: DriftRiskResponse | undefined = q.data;
  const atRisk = data?.status === 'at_risk';

  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: T.line, background: T.card }}
      data-testid="drift-risk-card"
      aria-label="بطاقة خطر انجراف الرشّ"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <SprayCan className="w-4 h-4" style={{ color: T.gold }} aria-hidden="true" /> خطر انجراف الرشّ
        </span>
        {zones.length ? (
          <span className="text-[11px] font-semibold" style={{ color: T.muted }}>
            {zones.length} حقل مجاور
          </span>
        ) : null}
      </div>

      {zones.length === 0 ? (
        <p className="text-[12px]" style={{ color: T.muted }}>
          لا حقول مجاورة قريبة (ضمن 2كم) لتقييم الانجراف نحوها.
        </p>
      ) : q.isLoading ? (
        <p className="text-[12px]" style={{ color: T.muted }}>
          جارٍ تقييم الانجراف…
        </p>
      ) : q.isError || !data ? (
        <p className="text-[12px]" style={{ color: T.danger }}>
          تعذّر تقييم الانجراف حاليّاً.
        </p>
      ) : data.status === 'unknown' ? (
        <p className="text-[12px]" style={{ color: T.faint }}>
          لا اتّجاه ريح سائد كافٍ لتقييم الانجراف بعد.
        </p>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-[13px] font-bold">
            {atRisk ? (
              <>
                <AlertTriangle className="w-4 h-4" style={{ color: T.danger }} aria-hidden="true" />
                <span style={{ color: T.danger }}>
                  خطر: الرشّ ينجرف نحو {data.exposed_zones?.length ?? 0} حقل مجاور
                </span>
              </>
            ) : (
              <>
                <ShieldCheck className="w-4 h-4" style={{ color: T.green }} aria-hidden="true" />
                <span style={{ color: T.green }}>آمن: لا انجراف نحو الجوار الآن</span>
              </>
            )}
          </div>
          <p className="text-[11px]" style={{ color: T.muted }}>
            الريح تنجرف نحو {data.drift_azimuth_deg}° · المصدر:{' '}
            {data.wind_source === 'nasa_power_prevailing' ? 'الريح السائدة (NASA POWER)' : data.wind_source}
          </p>
          {atRisk && data.exposed_zones?.length ? (
            <div className="flex flex-wrap gap-1">
              {data.exposed_zones.map((z) => (
                <span
                  key={z.id}
                  className="px-2 py-0.5 rounded-full text-[10px]"
                  style={{ background: T.card2, color: T.ink }}
                >
                  {z.id} · {z.distance_m}م
                </span>
              ))}
            </div>
          ) : null}
          <p className="text-[10px]" style={{ color: T.faint }}>
            تقدير محافظ (مركز الحقل + مخروط) — لا ترشّ نحو الحقول المعرّضة؛ القرار النهائيّ ميدانيّ.
          </p>
        </div>
      )}
    </section>
  );
}
