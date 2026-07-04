import { Moon, Quote, Sprout } from 'lucide-react';
import { useCalendarToday, useProverbsForDate } from '../../hooks/useApi';
import { calendarFacts, plantingFitTone, topProverbs } from '../../lib/yemeniCalendar';
import { T } from '../ds';

interface Props {
  /** محصول الحقل النشط — يُفعِّل نافذة الزراعة وملاءمة الشهر. */
  cropLabel?: string | null;
  enabled?: boolean;
}

const FIT_COLOR: Record<string, string> = { good: '#86efac', ok: '#fde68a', bad: '#fca5a5', unknown: '#64748b' };

/** التقويم الزراعيّ اليمنيّ: المنزلة القمريّة + الشهر الحميريّ + نظام المنطقة + أمثال
 *  المنزلة النشطة + نافذة زراعة محصول الحقل. صدق: الخادم يصرّح display_only —
 *  سياق تراثيّ-رصديّ لا يدخل محرّك القرار (التوقيت الفعليّ على GDD/الفيزياء)،
 *  والتصريح يُعرَض حرفيّاً مع تنويه «التواريخ تقريبيّة». */
export default function YemeniCalendarCard({ cropLabel, enabled = true }: Props) {
  const todayQ = useCalendarToday(cropLabel ?? null, null, enabled);
  const proverbsQ = useProverbsForDate(todayQ.data?.date_iso ?? null, null, enabled && !!todayQ.data && !todayQ.data.error_ar);

  if (!enabled) return null;

  const ctx = todayQ.data ?? null;
  const facts = calendarFacts(ctx);
  const proverbs = topProverbs(proverbsQ.data);
  const window = ctx?.planting?.window;
  const fit = ctx?.planting?.current_month_fit;
  const fitTone = plantingFitTone(fit);

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="yemeni-calendar" aria-label="التقويم الزراعيّ اليمنيّ">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Moon className="w-4 h-4 text-emerald-300" aria-hidden="true" /> التقويم الزراعيّ اليمنيّ
          {ctx?.date_iso && <span className="text-[11px]" style={{ color: T.faint }}>· {ctx.date_iso}</span>}
        </span>
        <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.faint }}>
          سياق تراثيّ — لا يدخل القرار
        </span>
      </div>

      {todayQ.isLoading ? (
        <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة التقويم…</div>
      ) : ctx?.error_ar ? (
        <div className="text-[11px]" style={{ color: T.muted }}>{ctx.error_ar}</div>
      ) : facts.length === 0 ? (
        <div className="text-[11px]" style={{ color: T.muted }}>لا سياق تقويميّ متاح لهذا اليوم.</div>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-1.5">
            {facts.map((f) => (
              <span key={f.label} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                <span style={{ color: T.faint }}>{f.label}:</span> {f.value}
              </span>
            ))}
          </div>

          {/* نافذة زراعة محصول الحقل + ملاءمة الشهر (حكم الخادم) */}
          {window?.supported && (
            <div className="flex flex-col gap-1 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
              <div className="inline-flex items-center gap-1.5 text-[11px] font-bold" style={{ color: T.ink }}>
                <Sprout className="w-3.5 h-3.5 text-emerald-300" aria-hidden="true" />
                زراعة {window.crop_ar}: {window.window_ar ?? '—'}
                {window.optimal_ar && <span className="font-normal" style={{ color: T.faint }}>(الأمثل: {window.optimal_ar})</span>}
              </div>
              {fit?.supported && fit.status_ar && (
                <div className="text-[11px]" style={{ color: FIT_COLOR[fitTone] }}>
                  {fit.status_ar}{fit.advice_ar ? ` — ${fit.advice_ar}` : ''}
                </div>
              )}
              {window.yemen_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{window.yemen_note_ar}</div>}
            </div>
          )}

          {/* أمثال المنزلة النشطة */}
          {proverbs.length > 0 && (
            <div className="flex flex-col gap-1">
              {proverbs.map((p) => (
                <div key={p.text_ar} className="flex items-start gap-1.5 text-[11px]" style={{ color: T.muted }}>
                  <Quote className="w-3.5 h-3.5 shrink-0 text-amber-300" aria-hidden="true" />
                  <span>
                    <span className="font-bold" style={{ color: T.ink }}>«{p.text_ar}»</span>
                    {p.meaning_ar ? ` — ${p.meaning_ar}` : ''}
                    <span style={{ color: T.faint }}> ({p.marker_ar})</span>
                  </span>
                </div>
              ))}
            </div>
          )}

          {ctx?.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{ctx.disclaimer_ar}</div>}
        </div>
      )}
    </section>
  );
}
