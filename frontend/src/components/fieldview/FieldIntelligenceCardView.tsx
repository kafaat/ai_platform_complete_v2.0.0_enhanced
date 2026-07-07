import { Brain, Satellite, AlertTriangle, ShieldCheck, Layers } from 'lucide-react';
import { useFieldIntelligenceCard } from '../../hooks/useFieldIntelligenceCard';
import {
  completenessPct,
  isPresent,
  missingReasonAr,
  ndviLabelAr,
  ndviLabelTone,
  SECTION_LABELS_AR,
  type FieldIntelligenceCard,
} from '../../lib/fieldIntelligenceCard';
import { T } from '../ds';

interface Props {
  fieldId?: string | null;
  enabled?: boolean;
}

/** بطاقة ذكاء الحقل الموحّدة (V65): أحدث مشهد · حالة المزوّدين · NDVI مقابل التاريخيّ ·
 *  عجز مائيّ · مناطق ضعيفة · تنبيهات · توصية استطلاع · أدلّة · ثقة. صدق: كلّ قسم
 *  يُعرَض حاضراً بقيمته أو مفقوداً بسببه صراحةً — الواجهة لا تختلق ما لم يرجعه الخادم. */
export default function FieldIntelligenceCardView({ fieldId, enabled = true }: Props) {
  const q = useFieldIntelligenceCard(fieldId, enabled);
  if (!enabled || !fieldId) return null;

  const card: FieldIntelligenceCard | undefined = q.data?.field_intelligence_card;

  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: T.line, background: T.card }}
      data-testid="field-intelligence-card"
      aria-label="بطاقة ذكاء الحقل"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Brain className="w-4 h-4" style={{ color: T.gold }} aria-hidden="true" /> بطاقة ذكاء الحقل
        </span>
        {card ? (
          <span className="text-[11px] font-semibold" style={{ color: T.muted }}>
            الاكتمال {completenessPct(card.completeness)}%
          </span>
        ) : null}
      </div>

      {q.isLoading ? (
        <p className="text-[12px]" style={{ color: T.muted }}>
          جارٍ تجميع البطاقة…
        </p>
      ) : q.isError ? (
        <p className="text-[12px]" style={{ color: T.danger }}>
          تعذّر تجميع البطاقة حاليّاً.
        </p>
      ) : !card ? (
        <p className="text-[12px]" style={{ color: T.muted }}>
          لا بطاقة متاحة لهذا الحقل بعد.
        </p>
      ) : (
        <div className="space-y-2">
          {/* شريط الاكتمال */}
          <div className="h-1.5 rounded-full overflow-hidden" style={{ background: T.card2 }}>
            <div
              className="h-full rounded-full"
              style={{ width: `${completenessPct(card.completeness)}%`, background: T.green }}
            />
          </div>

          {/* أحدث مشهد */}
          <Row icon={<Satellite className="w-3.5 h-3.5" aria-hidden="true" />} label={SECTION_LABELS_AR.latest_scene}>
            {isPresent(card.sections.latest_scene) ? (
              <span style={{ color: T.ink }}>
                {card.sections.latest_scene.acquisition_date ?? '—'} ·{' '}
                {card.sections.latest_scene.provider ?? '—'}
                {typeof card.sections.latest_scene.cloud_cover === 'number'
                  ? ` · غيوم ${card.sections.latest_scene.cloud_cover}%`
                  : ''}
              </span>
            ) : (
              <Missing reason={card.sections.latest_scene.reason} />
            )}
          </Row>

          {/* NDVI مقابل التاريخيّ */}
          <Row icon={<Layers className="w-3.5 h-3.5" aria-hidden="true" />} label={SECTION_LABELS_AR.ndvi_vs_historical}>
            {isPresent(card.sections.ndvi_vs_historical) ? (
              <span style={{ color: ndviLabelTone(card.sections.ndvi_vs_historical.label) }}>
                {ndviLabelAr(card.sections.ndvi_vs_historical.label)}
                {typeof card.sections.ndvi_vs_historical.anomaly === 'number'
                  ? ` (${card.sections.ndvi_vs_historical.anomaly > 0 ? '+' : ''}${card.sections.ndvi_vs_historical.anomaly})`
                  : ''}
              </span>
            ) : (
              <Missing reason={card.sections.ndvi_vs_historical.reason} />
            )}
          </Row>

          {/* حالة المزوّدين */}
          <Row icon={<ShieldCheck className="w-3.5 h-3.5" aria-hidden="true" />} label={SECTION_LABELS_AR.provider_status}>
            {isPresent(card.sections.provider_status) ? (
              <span style={{ color: T.ink }}>
                الافتراضيّ {card.sections.provider_status.providers?.default ?? '—'} · نشط{' '}
                {(card.sections.provider_status.providers?.active ?? []).length}
              </span>
            ) : (
              <Missing reason={card.sections.provider_status.reason} />
            )}
          </Row>

          {/* التنبيهات + الثقة (دائماً حاضرة) */}
          <Row icon={<AlertTriangle className="w-3.5 h-3.5" aria-hidden="true" />} label={SECTION_LABELS_AR.risk_alerts}>
            <span style={{ color: card.sections.risk_alerts.count > 0 ? T.warn : T.muted }}>
              {card.sections.risk_alerts.count} تنبيه
              {card.sections.risk_alerts.top_severity ? ` · ${card.sections.risk_alerts.top_severity}` : ''}
            </span>
          </Row>
          <Row icon={<ShieldCheck className="w-3.5 h-3.5" aria-hidden="true" />} label={SECTION_LABELS_AR.confidence}>
            <span style={{ color: T.ink }}>
              {typeof card.sections.confidence.value === 'number'
                ? `${Math.round(card.sections.confidence.value * 100)}%`
                : '—'}
            </span>
          </Row>

          {/* الأقسام المفقودة صراحةً (صدق: لا اختلاق) */}
          {card.missing_sections.length > 0 ? (
            <div className="flex flex-wrap gap-1 pt-1">
              {card.missing_sections.map((s) => (
                <span
                  key={s}
                  className="px-2 py-0.5 rounded-full text-[10px]"
                  style={{ background: T.card2, color: T.faint }}
                >
                  {SECTION_LABELS_AR[s] ?? s}: غير متاح
                </span>
              ))}
            </div>
          ) : null}
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

function Missing({ reason }: { reason?: string }) {
  return <span style={{ color: T.faint }}>{missingReasonAr(reason)}</span>;
}
