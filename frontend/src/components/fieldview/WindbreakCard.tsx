import { Wind, Trees, Compass } from 'lucide-react';
import { useFieldWindPrevailing } from '../../hooks/useFieldWindPrevailing';
import {
  protectionSummaryAr,
  topRoseSectors,
  windMissingReasonAr,
  type WindPrevailingResponse,
} from '../../lib/windbreak';
import { T } from '../ds';

interface Props {
  fieldId?: string | null;
  enabled?: boolean;
}

/** بطاقة الرياح السائدة + المصدّ (V73-UI): من أين تأتي الرياح غالباً؟ وكيف أوجّه مصدّاً
 *  شجريّاً؟ من تاريخ NASA POWER (~0.5°). صدق: المحسوب بقيمته والمتعذّر بسببه صراحةً. */
export default function WindbreakCard({ fieldId, enabled = true }: Props) {
  const q = useFieldWindPrevailing(fieldId, { enabled });
  if (!enabled || !fieldId) return null;
  const data: WindPrevailingResponse | undefined = q.data;

  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: T.line, background: T.card }}
      data-testid="windbreak-card"
      aria-label="بطاقة الرياح السائدة والمصدّات"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Wind className="w-4 h-4" style={{ color: T.gold }} aria-hidden="true" /> الرياح السائدة والمصدّات
        </span>
        {data?.computed && data.n_observations ? (
          <span className="text-[11px] font-semibold" style={{ color: T.muted }}>
            {data.n_observations} يوم · {data.years} سنوات
          </span>
        ) : null}
      </div>

      {q.isLoading ? (
        <p className="text-[12px]" style={{ color: T.muted }}>
          جارٍ حساب الرياح السائدة…
        </p>
      ) : q.isError ? (
        <p className="text-[12px]" style={{ color: T.danger }}>
          تعذّر حساب الرياح السائدة حاليّاً.
        </p>
      ) : !data ? (
        <p className="text-[12px]" style={{ color: T.muted }}>
          لا بيانات رياح لهذا الحقل بعد.
        </p>
      ) : !data.computed ? (
        <p className="text-[12px]" style={{ color: T.faint }}>
          {windMissingReasonAr(data.reason)}
        </p>
      ) : (
        <div className="space-y-2">
          <Row icon={<Compass className="w-3.5 h-3.5" aria-hidden="true" />} label="الاتّجاه السائد">
            <span style={{ color: T.ink }}>
              تأتي الريح من {data.prevailing?.label_ar ?? '—'}
              {data.windbreak?.wind_towards?.label_ar
                ? ` ← نحو ${data.windbreak.wind_towards.label_ar}`
                : ''}
            </span>
          </Row>

          <Row icon={<Trees className="w-3.5 h-3.5" aria-hidden="true" />} label="توصية المصدّ">
            <span style={{ color: T.ink }}>
              وجّه المصدّ عموديّاً (سَمت {data.windbreak?.barrier_orientation_deg ?? '—'}°) · ازرع على
              الحافة {data.windbreak?.plant_side ?? '—'}
            </span>
          </Row>

          <Row icon={<Trees className="w-3.5 h-3.5" aria-hidden="true" />} label="الحماية">
            <span style={{ color: T.muted }}>{protectionSummaryAr(data.windbreak)}</span>
          </Row>

          {/* أعلى قطاعات وردة الرياح (من أين تأتي غالباً) */}
          <div className="flex flex-wrap gap-1 pt-1">
            {topRoseSectors(data.wind_rose).map((s) => (
              <span
                key={s.key}
                className="px-2 py-0.5 rounded-full text-[10px]"
                style={{ background: T.card2, color: T.muted }}
              >
                {s.key}: {s.count}
              </span>
            ))}
          </div>

          <p className="text-[10px]" style={{ color: T.faint }}>
            المصدر: NASA POWER {data.resolution ?? ''} — مقياس منطقة لا نقطة حقل دقيقة.
          </p>
        </div>
      )}
    </section>
  );
}

function Row({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 text-[12px]">
      <span className="inline-flex items-center gap-1.5 font-semibold" style={{ color: T.muted }}>
        {icon}
        {label}
      </span>
      <span className="text-left">{children}</span>
    </div>
  );
}
