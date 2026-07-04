import { useMemo, useState } from 'react';
import { RefreshCcw, CheckCircle2, MinusCircle, XCircle } from 'lucide-react';
import { useRotationSuggest, usePlantingCheck } from '../../hooks/useApi';
import { groupRanked, monthOfIso, ratingColor, type RotationCandidate } from '../../lib/plantingAdvisor';
import { plantingFitTone } from '../../lib/yemeniCalendar';
import { T } from '../ds';

interface Props {
  /** محصول الحقل الحاليّ — يقود اقتراح الدورة الزراعيّة. */
  cropLabel?: string | null;
  /** تاريخ اليوم ISO (من سياق التقويم) — لملاءمة الشهر؛ غيابه يعطّل الفحص لا يخمّنه. */
  todayIso?: string | null;
  enabled?: boolean;
}

const FIT_COLOR: Record<string, string> = { good: '#86efac', ok: '#fde68a', bad: '#fca5a5', unknown: '#64748b' };

/** «ماذا أزرع بعد محصولي؟»: اقتراح الدورة الزراعيّة (good/acceptable/avoid بأسباب
 *  يمنيّة من جدول الدورة) + ملاءمة الشهر الحاليّ للمرشَّح المُختار — الأحكام كلّها
 *  من الخادم، وdisclaimer «توجّه لا تفرض» يُعرَض. */
export default function PlantingAdvisorCard({ cropLabel, todayIso, enabled = true }: Props) {
  const suggestQ = useRotationSuggest(cropLabel ?? null, enabled);
  const groups = useMemo(() => groupRanked(suggestQ.data), [suggestQ.data]);
  const [picked, setPicked] = useState<RotationCandidate | null>(null);
  const month = monthOfIso(todayIso);
  const checkQ = usePlantingCheck(picked?.candidate_crop ?? null, month);
  const fitTone = plantingFitTone(checkQ.data);

  if (!enabled || !cropLabel) return null;

  const pill = (c: RotationCandidate, Icon: typeof CheckCircle2) => (
    <button
      key={c.candidate_crop}
      type="button"
      onClick={() => setPicked(picked?.candidate_crop === c.candidate_crop ? null : c)}
      className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full font-semibold"
      style={{
        border: `1px solid ${picked?.candidate_crop === c.candidate_crop ? ratingColor(c.rating) : T.line}`,
        color: ratingColor(c.rating),
        background: 'rgba(15,23,42,.45)',
      }}
    >
      <Icon className="w-3 h-3" aria-hidden="true" /> {c.candidate_crop}
    </button>
  );

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="planting-advisor" aria-label="ماذا أزرع؟">
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <RefreshCcw className="w-4 h-4 text-emerald-300" aria-hidden="true" /> ماذا أزرع بعد {suggestQ.data?.previous_crop ?? cropLabel}؟
        </span>
      </div>

      {suggestQ.isLoading ? (
        <div className="text-[11px]" style={{ color: T.faint }}>جارٍ حساب الدورة الزراعيّة…</div>
      ) : suggestQ.data && !suggestQ.data.supported ? (
        <div className="text-[11px]" style={{ color: T.muted }}>{suggestQ.data.message_ar ?? 'المحصول غير معروف في جدول الدورة.'}</div>
      ) : (
        <div className="flex flex-col gap-2">
          {groups.good.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] font-bold" style={{ color: '#86efac' }}>جيّد:</span>
              {groups.good.map((c) => pill(c, CheckCircle2))}
            </div>
          )}
          {groups.acceptable.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] font-bold" style={{ color: '#fde68a' }}>مقبول:</span>
              {groups.acceptable.map((c) => pill(c, MinusCircle))}
            </div>
          )}
          {groups.avoid.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] font-bold" style={{ color: '#fca5a5' }}>تجنّب:</span>
              {groups.avoid.map((c) => pill(c, XCircle))}
            </div>
          )}

          {/* تفاصيل المرشَّح: أسباب الدورة + ملاءمة الشهر الحاليّ (حكم الخادم) */}
          {picked && (
            <div className="flex flex-col gap-1 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
              <div className="text-[11px] font-bold" style={{ color: ratingColor(picked.rating) }}>
                {picked.candidate_crop} — {picked.rating_ar}
              </div>
              {picked.reasons_ar.map((r) => (
                <div key={r} className="text-[11px]" style={{ color: T.muted }}>• {r}</div>
              ))}
              {month != null && checkQ.data?.supported && checkQ.data.status_ar && (
                <div className="text-[11px]" style={{ color: FIT_COLOR[fitTone] }}>
                  {checkQ.data.status_ar}{checkQ.data.advice_ar ? ` — ${checkQ.data.advice_ar}` : ''}
                </div>
              )}
              {month == null && (
                <div className="text-[10px]" style={{ color: T.faint }}>لا تاريخ سياق — تعذّر فحص ملاءمة الشهر.</div>
              )}
            </div>
          )}

          {suggestQ.data?.yemen_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{suggestQ.data.yemen_note_ar}</div>}
          {suggestQ.data?.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{suggestQ.data.disclaimer_ar}</div>}
        </div>
      )}
    </section>
  );
}
