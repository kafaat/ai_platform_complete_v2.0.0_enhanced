import { useMemo, useState } from 'react';
import { BookOpen, Sprout, ShieldCheck, CalendarClock, FlaskConical } from 'lucide-react';
import {
  useCropCardsIndex, useCropCard, useVarietyDiseaseWatch, useVarietyExpectedHarvest, useVarietySalinity,
} from '../../hooks/useApi';
import { matchCropId, summarizeCropCard } from '../../lib/fieldCropCard';
import { T } from '../ds';

interface Props {
  /** تسمية محصول الحقل النشط (كما هي في بيانات الحقل). */
  cropLabel?: string | null;
  /** تاريخ بذار الموسم النشط (ISO) — يُفعِّل الحصاد المتوقَّع للصنف. */
  sowingDate?: string | null;
  enabled?: boolean;
}

/** بطاقة المحصول/الصنف: تعكس المعرفة المرجعيّة المُخزَّنة (FAO-56 Kc · Maas-Hoffman ·
 *  GDD · مقاومات الأصناف اليمنيّة) على الحقل النشط. صدق: معرفة محايدة الموقع (note_ar
 *  تُعرَض)، لا مطابقة عند الالتباس، وECe يُدخِله المستخدم من قياس حقيقيّ. */
export default function CropKnowledgeCard({ cropLabel, sowingDate, enabled = true }: Props) {
  const indexQ = useCropCardsIndex(enabled && !!cropLabel);
  const cropId = useMemo(
    () => matchCropId(cropLabel, indexQ.data?.crops),
    [cropLabel, indexQ.data],
  );
  const cardQ = useCropCard(cropId);
  const facts = useMemo(() => summarizeCropCard(cardQ.data?.card), [cardQ.data]);

  const varieties = cardQ.data?.varieties ?? [];
  const [varietyId, setVarietyId] = useState<string | null>(null);
  const [eceInput, setEceInput] = useState('');
  const ece = useMemo(() => {
    const v = Number(eceInput);
    return eceInput.trim() !== '' && Number.isFinite(v) && v >= 0 ? v : null;
  }, [eceInput]);

  const diseaseQ = useVarietyDiseaseWatch(varietyId);
  const harvestQ = useVarietyExpectedHarvest(varietyId, sowingDate ?? null);
  const salinityQ = useVarietySalinity(varietyId, ece);

  if (!enabled || !cropLabel) return null;

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="crop-knowledge" aria-label="بطاقة المحصول">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <BookOpen className="w-4 h-4 text-emerald-300" aria-hidden="true" /> بطاقة المحصول
          <span className="text-[11px]" style={{ color: T.faint }}>· {cropLabel}</span>
        </span>
        {cardQ.data?.card?.crop_family && (
          <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.faint }}>
            {cardQ.data.card.crop_family}
          </span>
        )}
      </div>

      {indexQ.isLoading || cardQ.isLoading ? (
        <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة بطاقات المعرفة…</div>
      ) : !cropId ? (
        <div className="text-[11px]" style={{ color: T.muted }}>
          لا بطاقة معرفيّة مرجعيّة لمحصول «{cropLabel}» بعد
          {indexQ.data ? ` (المتاح: ${indexQ.data.total_crops} محصولاً · ${indexQ.data.total_varieties} صنفاً)` : ''}.
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {/* حقائق الفيزياء/الفسيولوجيا المرجعيّة */}
          {facts.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {facts.map((f) => (
                <span key={f.label} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                  <span style={{ color: T.faint }}>{f.label}:</span> {f.value}
                </span>
              ))}
            </div>
          )}

          {/* الأصناف المحلّيّة المُوثَّقة */}
          {varieties.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
                <Sprout className="w-3.5 h-3.5 text-emerald-300" aria-hidden="true" /> الأصناف:
              </span>
              {varieties.map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setVarietyId(varietyId === v ? null : v)}
                  className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                  style={{
                    border: `1px solid ${varietyId === v ? '#14532d' : T.line}`,
                    color: varietyId === v ? '#86efac' : T.muted,
                    background: varietyId === v ? 'rgba(20,83,45,.25)' : 'rgba(15,23,42,.45)',
                  }}
                >
                  {v}
                </button>
              ))}
            </div>
          )}

          {/* تفاصيل الصنف المُختار — مقاومات + حصاد متوقَّع + ملاءمة ملوحة */}
          {varietyId && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
              {diseaseQ.data && diseaseQ.data.resistant_ar.length > 0 && (
                <div className="flex items-start gap-1.5 text-[11px]" style={{ color: T.muted }}>
                  <ShieldCheck className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-hidden="true" />
                  <span><span className="font-bold" style={{ color: T.ink }}>مقاومات مُوثَّقة:</span> {diseaseQ.data.resistant_ar.join(' · ')}</span>
                </div>
              )}
              {diseaseQ.data?.note_ar && (
                <div className="text-[10px]" style={{ color: T.faint }}>{diseaseQ.data.note_ar}</div>
              )}

              {sowingDate ? (
                harvestQ.data && (
                  <div className="flex items-start gap-1.5 text-[11px]" style={{ color: T.muted }}>
                    <CalendarClock className="w-3.5 h-3.5 shrink-0 text-sky-300" aria-hidden="true" />
                    <span>
                      <span className="font-bold" style={{ color: T.ink }}>من بذار {harvestQ.data.sowing_date}:</span>{' '}
                      تزهير ~{harvestQ.data.expected_flowering_date ?? '—'} · حصاد ~{harvestQ.data.expected_harvest_date ?? '—'}
                      {harvestQ.data.days_to_maturity != null ? ` (${harvestQ.data.days_to_maturity} يوماً)` : ''}
                    </span>
                  </div>
                )
              ) : (
                <div className="text-[10px]" style={{ color: T.faint }}>أضِف تاريخ بذار للموسم لعرض الحصاد المتوقَّع.</div>
              )}

              {/* ملاءمة الملوحة — قياس حقيقيّ من المستخدم، لا افتراض */}
              <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
                <FlaskConical className="w-3.5 h-3.5 shrink-0 text-amber-300" aria-hidden="true" />
                <label htmlFor="crop-ece" className="font-bold" style={{ color: T.ink }}>ملوحة مقيسة ECe (dS/m):</label>
                <input
                  id="crop-ece"
                  type="number"
                  min="0"
                  step="0.1"
                  value={eceInput}
                  onChange={(e) => setEceInput(e.target.value)}
                  placeholder="من قياس"
                  className="w-20 px-2 py-0.5 rounded-lg text-[11px]"
                  style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }}
                />
                {salinityQ.data && (
                  salinityQ.data.class ? (
                    <span style={{ color: salinityQ.data.class === 'suitable' ? '#86efac' : '#fdba74' }}>
                      {salinityQ.data.class === 'suitable' ? 'ملائم' : salinityQ.data.class}
                      {salinityQ.data.expected_yield_loss_pct != null && salinityQ.data.expected_yield_loss_pct > 0
                        ? ` · خسارة متوقَّعة ~${salinityQ.data.expected_yield_loss_pct}٪`
                        : ''}
                      {salinityQ.data.threshold_ece_ds_m != null ? ` (العتبة ${salinityQ.data.threshold_ece_ds_m})` : ''}
                    </span>
                  ) : (
                    <span style={{ color: T.faint }}>{salinityQ.data.note_ar ?? 'بيانات غير كافية'}</span>
                  )
                )}
              </div>
            </div>
          )}

          {indexQ.data?.note_ar && (
            <div className="text-[10px]" style={{ color: T.faint }}>{indexQ.data.note_ar}</div>
          )}
        </div>
      )}
    </section>
  );
}
