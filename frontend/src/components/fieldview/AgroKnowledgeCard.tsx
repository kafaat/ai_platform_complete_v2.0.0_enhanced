import { useMemo } from 'react';
import { Sprout, Warehouse, Coffee, ShieldAlert, Info } from 'lucide-react';
import {
  useCropPropagation, usePostharvestBestPractices,
  useCoffeeGuide, useCoffeeVarieties, useCoffeePests,
} from '../../hooks/useApi';
import {
  isCoffeeCrop, propagationFacts, provenanceNotes,
  coffeeVarietyRows, coffeePestRows, practiceRows,
} from '../../lib/fieldAgroKnowledge';
import { T } from '../ds';

interface Props {
  /** تسمية محصول الحقل النشط (كما هي في بيانات الحقل). */
  cropLabel?: string | null;
  enabled?: boolean;
}

/** بطاقة المعرفة الزراعيّة الخبيرة: تعكس طبقة خلفيّة يتيمة عن الواجهة — الإكثار
 *  المناسب للمحصول + ممارسات ما بعد الحصاد + (للبنّ فقط) دليل/أصناف/آفات البنّ
 *  اليمني. صدق: معرفة مرجعيّة موثّقة (لا معايرة موقع)؛ حقول المنشأ (note/source/
 *  disclaimer) تُعرَض؛ الغائب «—»؛ حالات فارغة/تحميل صريحة لا تلفيق. */
export default function AgroKnowledgeCard({ cropLabel, enabled = true }: Props) {
  const on = enabled && !!cropLabel;
  const coffee = useMemo(() => isCoffeeCrop(cropLabel), [cropLabel]);

  const propQ = useCropPropagation(on ? cropLabel : null);
  const postQ = usePostharvestBestPractices(on ? cropLabel : null, on);
  const guideQ = useCoffeeGuide(on && coffee);
  const varietiesQ = useCoffeeVarieties(on && coffee);
  const pestsQ = useCoffeePests(on && coffee);

  const propFacts = useMemo(() => propagationFacts(propQ.data), [propQ.data]);
  const postPractices = useMemo(() => practiceRows(postQ.data?.practices_ar), [postQ.data]);
  const postNotes = useMemo(() => provenanceNotes(postQ.data as unknown as Record<string, unknown>), [postQ.data]);
  const guidePractices = useMemo(() => practiceRows(guideQ.data?.practices_ar), [guideQ.data]);
  const varieties = useMemo(() => coffeeVarietyRows(varietiesQ.data), [varietiesQ.data]);
  const pests = useMemo(() => coffeePestRows(pestsQ.data), [pestsQ.data]);

  if (!on) return null;

  const propSupported = propQ.data?.supported === true;
  const anyLoading = propQ.isLoading || postQ.isLoading || (coffee && (guideQ.isLoading || varietiesQ.isLoading || pestsQ.isLoading));

  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}
      data-testid="agro-knowledge"
      aria-label="بطاقة المعرفة الزراعيّة"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Sprout className="w-4 h-4 text-emerald-300" aria-hidden="true" /> المعرفة الزراعيّة
          <span className="text-[11px]" style={{ color: T.faint }}>· {cropLabel}</span>
        </span>
        {coffee && (
          <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: '#fdba74' }}>
            <Coffee className="w-3 h-3" aria-hidden="true" /> بُنّ
          </span>
        )}
      </div>

      {anyLoading ? (
        <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة المعرفة الزراعيّة…</div>
      ) : (
        <div className="flex flex-col gap-2">
          {/* الإكثار المناسب للمحصول */}
          <div className="rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }} data-testid="agro-propagation">
            <div className="inline-flex items-center gap-1.5 text-[11px] font-bold mb-1" style={{ color: T.ink }}>
              <Sprout className="w-3.5 h-3.5 text-emerald-300" aria-hidden="true" /> الإكثار المناسب
            </div>
            {propSupported ? (
              <div className="flex flex-col gap-1">
                {propFacts.map((f) => (
                  <div key={f.label} className="text-[11px]" style={{ color: T.muted }}>
                    <span className="font-bold" style={{ color: T.ink }}>{f.label}:</span> {f.value}
                  </div>
                ))}
                {propQ.data?.disclaimer_ar && (
                  <div className="text-[10px]" style={{ color: T.faint }}>{propQ.data.disclaimer_ar}</div>
                )}
              </div>
            ) : (
              <div className="text-[11px]" style={{ color: T.muted }}>
                {propQ.data?.message_ar ?? `لا توصية إكثار مرجعيّة لمحصول «${cropLabel}» بعد.`}
              </div>
            )}
          </div>

          {/* ممارسات ما بعد الحصاد */}
          {postPractices.length > 0 && (
            <div className="rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }} data-testid="agro-postharvest">
              <div className="inline-flex items-center gap-1.5 text-[11px] font-bold mb-1" style={{ color: T.ink }}>
                <Warehouse className="w-3.5 h-3.5 text-amber-300" aria-hidden="true" /> ما بعد الحصاد
              </div>
              {postQ.data?.crop_moisture_ar && (
                <div className="text-[11px] mb-1" style={{ color: '#86efac' }}>{postQ.data.crop_moisture_ar}</div>
              )}
              <ul className="flex flex-col gap-0.5">
                {postPractices.map((p, i) => (
                  <li key={`${p.topic}-${i}`} className="text-[11px]" style={{ color: T.muted }}>
                    <span className="font-bold" style={{ color: T.ink }}>{p.topic}:</span> {p.detail}
                  </li>
                ))}
              </ul>
              {postNotes.map((n, i) => (
                <div key={i} className="text-[10px] mt-1 flex items-start gap-1" style={{ color: T.faint }}>
                  <Info className="w-3 h-3 shrink-0 mt-0.5" aria-hidden="true" /> <span>{n}</span>
                </div>
              ))}
            </div>
          )}

          {/* دليل البنّ اليمني (للبنّ فقط) */}
          {coffee && guidePractices.length > 0 && (
            <div className="rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }} data-testid="agro-coffee-guide">
              <div className="inline-flex items-center gap-1.5 text-[11px] font-bold mb-1" style={{ color: T.ink }}>
                <Coffee className="w-3.5 h-3.5 text-amber-300" aria-hidden="true" /> دليل زراعة البنّ
                {guideQ.data?.type_ar && <span className="text-[10px] font-normal" style={{ color: T.faint }}>· {guideQ.data.type_ar}</span>}
              </div>
              <ul className="flex flex-col gap-0.5">
                {guidePractices.map((p, i) => (
                  <li key={`${p.topic}-${i}`} className="text-[11px]" style={{ color: T.muted }}>
                    <span className="font-bold" style={{ color: T.ink }}>{p.topic}:</span> {p.detail}
                  </li>
                ))}
              </ul>
              {guideQ.data?.economic_note_ar && (
                <div className="text-[10px] mt-1" style={{ color: T.faint }}>{guideQ.data.economic_note_ar}</div>
              )}
              {guideQ.data?.disclaimer_ar && (
                <div className="text-[10px] mt-0.5" style={{ color: T.faint }}>{guideQ.data.disclaimer_ar}</div>
              )}
            </div>
          )}

          {/* أصناف البنّ اليمنيّة */}
          {coffee && varieties.length > 0 && (
            <div className="rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }} data-testid="agro-coffee-varieties">
              <div className="inline-flex items-center gap-1.5 text-[11px] font-bold mb-1" style={{ color: T.ink }}>
                <Sprout className="w-3.5 h-3.5 text-emerald-300" aria-hidden="true" /> أصناف البنّ
              </div>
              <div className="flex flex-wrap gap-1.5">
                {varieties.map((v, i) => (
                  <span key={`${v.name}-${i}`} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }} title={v.note}>
                    {v.name} <span style={{ color: T.faint }}>· {v.region}</span>
                  </span>
                ))}
              </div>
              {varietiesQ.data?.note_ar && (
                <div className="text-[10px] mt-1" style={{ color: T.faint }}>{varietiesQ.data.note_ar}</div>
              )}
            </div>
          )}

          {/* آفات البنّ (IPM) */}
          {coffee && pests.length > 0 && (
            <div className="rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }} data-testid="agro-coffee-pests">
              <div className="inline-flex items-center gap-1.5 text-[11px] font-bold mb-1" style={{ color: T.ink }}>
                <ShieldAlert className="w-3.5 h-3.5 text-rose-300" aria-hidden="true" /> آفات البنّ
              </div>
              <ul className="flex flex-col gap-1">
                {pests.map((p, i) => (
                  <li key={`${p.name}-${i}`} className="text-[11px]" style={{ color: T.muted }}>
                    <span className="font-bold" style={{ color: T.ink }}>{p.name}</span>
                    {p.scientific !== '—' && <span className="italic" style={{ color: T.faint }}> ({p.scientific})</span>}
                    {p.note !== '—' && <> — {p.note}</>}
                  </li>
                ))}
              </ul>
              {pestsQ.data?.ipm_note_ar && (
                <div className="text-[10px] mt-1" style={{ color: T.faint }}>{pestsQ.data.ipm_note_ar}</div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
