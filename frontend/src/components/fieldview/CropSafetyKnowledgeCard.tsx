import { useMemo, useState } from 'react';
import { Bug, CalendarDays, Gem, ShieldAlert, Sprout } from 'lucide-react';
import {
  useBannedChemicals,
  useChemicalSafetyCheck,
  useHighValueCropDetail,
  useIntroductionCandidates,
  useNicheCropDetail,
  usePlantingCrops,
  usePlantingWindow,
  usePostharvestPests,
} from '../../hooks/useCropSafetyKnowledge';
import {
  INTRODUCTION_ZONE_OPTIONS,
  bannedRows,
  chemicalLimitFacts,
  chemicalStatusColor,
  highValueDetailRows,
  introductionCandidates,
  nicheDetailRows,
  pestRows,
  plantingCropRows,
  plantingWindowFacts,
  serverUnsupportedMessage,
  severityColor,
  textOrDash,
  type ChemicalCheckInput,
  type DetailRow,
} from '../../lib/cropSafetyKnowledge';
import { parseMeasure } from '../../lib/irrigationDecisionAids';
import { T } from '../ds';

interface Props {
  /** تسمية محصول الحقل النشط — سياق عرض فقط (النقاط كلّها محايدة الحقل). */
  cropLabel?: string | null;
  enabled?: boolean;
}

type SectionKey = 'chemical' | 'planting' | 'postharvest' | 'valueCrops';

const SECTIONS: { key: SectionKey; label_ar: string }[] = [
  { key: 'chemical', label_ar: 'سلامة كيميائيّة' },
  { key: 'planting', label_ar: 'ماذا أزرع؟' },
  { key: 'postharvest', label_ar: 'آفات التخزين' },
  { key: 'valueCrops', label_ar: 'محاصيل عالية القيمة' },
];

const inputStyle = { border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink } as const;
const boxStyle = { borderColor: T.line, background: 'rgba(15,23,42,.35)' } as const;

/** خطأ شبكة/خادم ⇒ نصّ إعادة محاولة صادق (لا إخفاء ولا تلفيق). */
function RetryNote({ q, label }: { q: { refetch: () => void }; label: string }) {
  return (
    <div className="text-[11px]" style={{ color: '#fca5a5' }}>
      تعذّر جلب {label} من الخادم.
      <button type="button" onClick={() => q.refetch()} className="ms-1 underline" style={{ color: '#fca5a5' }}>
        أعد المحاولة
      </button>
    </div>
  );
}

/** 404 من الخادم ⇒ إعلان «غير مُفعَّلة» صادق (الميزة غير منشورة على هذا الخادم). */
function DisabledNote() {
  return <div className="text-[11px]" style={{ color: T.muted }}>هذه الميزة غير مُفعَّلة على هذا الخادم.</div>;
}

function DetailRows({ rows }: { rows: DetailRow[] }) {
  if (rows.length === 0) return null;
  return (
    <>
      {rows.map((r) => (
        <div key={r.key} className="text-[11px]" style={{ color: T.muted }}>
          <b style={{ color: T.ink }}>{r.label}:</b> {r.value}
        </div>
      ))}
    </>
  );
}

/** «هل هذه المادّة آمنة؟ وماذا أزرع وأخزّن؟»: فحص السلامة الكيميائيّة (حكم الخادم
 *  حرفيّاً — سلامة حرجة، لا إعادة حكم في الواجهة) + قائمة المحظورات + تقويم
 *  الزراعة (محاصيل/نافذة) + آفات ما بعد الحصاد + تفصيل المحاصيل عالية القيمة/
 *  المتخصّصة ومرشّحي الإدخال. 404 ⇒ «غير مُفعَّلة» صادقة، وأخطاء الشبكة ⇒ إعادة محاولة. */
export default function CropSafetyKnowledgeCard({ cropLabel, enabled = true }: Props) {
  const [open, setOpen] = useState<SectionKey>('chemical');

  // — فحص المادّة: زرّ تأكيد لا كتابة حيّة — سلامة حرجة، لا فحص لاسم منقوص
  //   (الاسم الجزئي يعيد «غير معروفة» فيضلّل). الجرعة اختياريّة (kg/ha). —
  const [chemInput, setChemInput] = useState('');
  const [doseInput, setDoseInput] = useState('');
  const [checkReq, setCheckReq] = useState<ChemicalCheckInput | null>(null);
  const submitCheck = () => {
    const chemical = chemInput.trim();
    if (!chemical) return;
    const dose = parseMeasure(doseInput);
    setCheckReq({ chemical, ...(dose != null ? { dose_kg_ha: dose } : {}) });
  };
  const checkQ = useChemicalSafetyCheck(enabled && open === 'chemical' ? checkReq : null);

  // — قائمة المحظورات: مرجع شفافيّة يُجلَب عند طلبه فقط —
  const [showBanned, setShowBanned] = useState(false);
  const bannedQ = useBannedChemicals(enabled && open === 'chemical' && showBanned);

  // — تقويم الزراعة: قائمة الخادم ثمّ نافذة المحصول الذي يختاره المستخدم —
  const cropsQ = usePlantingCrops(enabled && open === 'planting');
  const [pickedCrop, setPickedCrop] = useState<string | null>(null);
  const windowQ = usePlantingWindow(pickedCrop, enabled && open === 'planting');

  // — آفات ما بعد الحصاد: مرجع ثابت يُجلَب عند فتح قسمه —
  const pestsQ = usePostharvestPests(enabled && open === 'postharvest');

  // — تفصيل عالي القيمة/متخصّص: اسم عربي يؤكّده المستخدم (مطابقة جزئيّة عند الخادم) —
  const [hvInput, setHvInput] = useState('');
  const [hvName, setHvName] = useState<string | null>(null);
  const hvQ = useHighValueCropDetail(hvName, enabled && open === 'valueCrops');
  const [nicheInput, setNicheInput] = useState('');
  const [nicheName, setNicheName] = useState<string | null>(null);
  const nicheQ = useNicheCropDetail(nicheName, enabled && open === 'valueCrops');

  // — مرشّحو الإدخال: ترشيح الخادم حسب منطقة يختارها المستخدم —
  const [zone, setZone] = useState('all');
  const candidatesQ = useIntroductionCandidates(zone, enabled && open === 'valueCrops');

  const limitFacts = useMemo(() => chemicalLimitFacts(checkQ.data), [checkQ.data]);
  const banned = useMemo(() => bannedRows(bannedQ.data), [bannedQ.data]);
  const plantingCrops = useMemo(() => plantingCropRows(cropsQ.data), [cropsQ.data]);
  const windowFacts = useMemo(() => plantingWindowFacts(windowQ.data), [windowQ.data]);
  const pests = useMemo(() => pestRows(pestsQ.data), [pestsQ.data]);
  const hvRows = useMemo(() => highValueDetailRows(hvQ.data), [hvQ.data]);
  const nicheRows = useMemo(() => nicheDetailRows(nicheQ.data), [nicheQ.data]);
  const candidates = useMemo(() => introductionCandidates(candidatesQ.data), [candidatesQ.data]);

  if (!enabled) return null;

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="crop-safety-knowledge" aria-label="سلامة المدخلات ومعرفة المحاصيل">
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <ShieldAlert className="w-4 h-4 text-emerald-300" aria-hidden="true" /> سلامة المدخلات ومعرفة المحاصيل
          {cropLabel && <span className="text-[11px]" style={{ color: T.faint }}>· {cropLabel}</span>}
        </span>
      </div>

      {/* أقسام قابلة للطيّ — استعلام كلّ قسم لا يُطلق إلّا عند فتحه (لا استدعاء ميّت). */}
      <div className="flex flex-wrap items-center gap-1.5 mb-2">
        {SECTIONS.map((s) => (
          <button
            key={s.key}
            type="button"
            onClick={() => setOpen(s.key)}
            className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
            style={{
              border: `1px solid ${open === s.key ? '#0c4a6e' : T.line}`,
              color: open === s.key ? '#7dd3fc' : T.muted,
              background: open === s.key ? 'rgba(12,74,110,.25)' : 'rgba(15,23,42,.45)',
            }}
          >
            {s.label_ar}
          </button>
        ))}
      </div>

      {/* ── سلامة كيميائيّة: فحص المادّة (حكم الخادم حرفيّاً) + مرجع المحظورات ── */}
      {open === 'chemical' && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
              <ShieldAlert className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-hidden="true" />
              <label htmlFor="csk-chem" className="font-bold" style={{ color: T.ink }}>اسم المادّة (إنجليزي):</label>
              <input id="csk-chem" type="text" dir="ltr" value={chemInput} onChange={(e) => setChemInput(e.target.value)} placeholder="glyphosate" className="w-32 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <label htmlFor="csk-dose" className="font-bold" style={{ color: T.ink }}>الجرعة (كجم/هكتار، اختياري):</label>
              <input id="csk-dose" type="number" min="0" step="0.1" value={doseInput} onChange={(e) => setDoseInput(e.target.value)} placeholder="المقترحة" className="w-20 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <button
                type="button"
                onClick={submitCheck}
                disabled={chemInput.trim() === ''}
                className="text-[10px] px-2 py-0.5 rounded-full font-semibold disabled:opacity-50"
                style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(20,83,45,.25)' }}
              >
                افحص
              </button>
            </div>

            {checkReq == null ? (
              <div className="text-[10px]" style={{ color: T.faint }}>أدخِل اسم المادّة (كما على العبوة، إنجليزيّاً) ثمّ «افحص» — الحكم من الخادم لا من الواجهة.</div>
            ) : checkQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ فحص المادّة…</div>
            ) : checkQ.isError ? (
              <RetryNote q={checkQ} label="فحص السلامة الكيميائيّة" />
            ) : checkQ.data?.disabled ? (
              <DisabledNote />
            ) : checkQ.data ? (
              <>
                {/* حكم الخادم حرفيّاً — status_ar/message_ar كما جاءا (سلامة حرجة، لا إعادة حكم). */}
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] px-2 py-0.5 rounded-full font-bold" style={{ border: `1px solid ${T.line}`, color: chemicalStatusColor(checkQ.data.status) }}>
                    {textOrDash(checkQ.data.status_ar)}
                  </span>
                  <span className="text-[11px]" dir="ltr" style={{ color: T.faint }}>{textOrDash(checkQ.data.chemical)}</span>
                  {checkQ.data.severity && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: severityColor(checkQ.data.severity) }}>
                      الشدّة: {checkQ.data.severity}
                    </span>
                  )}
                </div>
                {checkQ.data.message_ar && <div className="text-[11px]" style={{ color: T.muted }}>{checkQ.data.message_ar}</div>}
                {limitFacts.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {limitFacts.map((f) => (
                      <span key={f.label} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                        <span style={{ color: T.faint }}>{f.label}:</span> {f.value}
                      </span>
                    ))}
                  </div>
                )}
              </>
            ) : null}
          </div>

          {/* مرجع المحظورات — شفافيّة قائمة الخادم عند الطلب فقط */}
          <button
            type="button"
            onClick={() => setShowBanned((v) => !v)}
            className="self-start text-[10px] px-2 py-0.5 rounded-full font-semibold"
            style={{ border: `1px solid ${showBanned ? '#7f1d1d' : T.line}`, color: showBanned ? '#fca5a5' : T.muted, background: showBanned ? 'rgba(127,29,29,.2)' : 'rgba(15,23,42,.45)' }}
          >
            قائمة المواد المحظورة/المقيّدة
          </button>
          {showBanned && (
            bannedQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة قائمة المحظورات…</div>
            ) : bannedQ.isError ? (
              <RetryNote q={bannedQ} label="قائمة المحظورات" />
            ) : bannedQ.data?.disabled ? (
              <DisabledNote />
            ) : banned.length > 0 ? (
              <div className="flex flex-col gap-1 rounded-xl border p-2" style={boxStyle}>
                {bannedQ.data?.source_ar && <div className="text-[10px]" style={{ color: T.faint }}>المصدر: {bannedQ.data.source_ar}</div>}
                {banned.map((b) => (
                  <div key={b.name ?? b.reason_ar} className="text-[11px]" style={{ color: T.muted }}>
                    <b dir="ltr" style={{ color: severityColor(b.severity) }}>{textOrDash(b.name)}</b>
                    {' — '}{textOrDash(b.reason_ar)}
                  </div>
                ))}
                {bannedQ.data?.disclaimer_ar && <div className="text-[10px]" style={{ color: '#fdba74' }}>⚠ {bannedQ.data.disclaimer_ar}</div>}
              </div>
            ) : (
              <div className="text-[11px]" style={{ color: T.muted }}>لا قائمة محظورات من الخادم بعد.</div>
            )
          )}
        </div>
      )}

      {/* ── «ماذا أزرع؟»: محاصيل التقويم ثمّ نافذة المحصول المختار — أحكام الخادم ── */}
      {open === 'planting' && (
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
          {cropsQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة محاصيل التقويم…</div>
          ) : cropsQ.isError ? (
            <RetryNote q={cropsQ} label="محاصيل تقويم الزراعة" />
          ) : cropsQ.data?.disabled ? (
            <DisabledNote />
          ) : plantingCrops.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
                <CalendarDays className="w-3.5 h-3.5 text-emerald-300" aria-hidden="true" /> المحاصيل:
              </span>
              {plantingCrops.map((c) => (
                <button
                  key={c.crop}
                  type="button"
                  onClick={() => setPickedCrop(pickedCrop === c.crop ? null : c.crop)}
                  className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                  style={{
                    border: `1px solid ${pickedCrop === c.crop ? '#14532d' : T.line}`,
                    color: pickedCrop === c.crop ? '#86efac' : T.muted,
                    background: pickedCrop === c.crop ? 'rgba(20,83,45,.25)' : 'rgba(15,23,42,.45)',
                  }}
                >
                  {c.name_ar ?? c.crop}
                </button>
              ))}
            </div>
          ) : (
            <div className="text-[11px]" style={{ color: T.muted }}>لا محاصيل مدعومة من الخادم بعد.</div>
          )}

          {pickedCrop && (
            windowQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة نافذة الزراعة…</div>
            ) : windowQ.isError ? (
              <RetryNote q={windowQ} label="نافذة الزراعة" />
            ) : windowQ.data?.disabled ? (
              <DisabledNote />
            ) : serverUnsupportedMessage(windowQ.data) ? (
              <div className="text-[11px]" style={{ color: '#fdba74' }}>{serverUnsupportedMessage(windowQ.data)}</div>
            ) : windowQ.data?.supported ? (
              <>
                <div className="text-[11px] font-bold" style={{ color: T.ink }}>{textOrDash(windowQ.data.crop_ar)}</div>
                {windowFacts.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {windowFacts.map((f) => (
                      <span key={f.label} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                        <span style={{ color: T.faint }}>{f.label}:</span> {f.value}
                      </span>
                    ))}
                  </div>
                )}
                {windowQ.data.early_risk_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>⚠ تبكير: {windowQ.data.early_risk_ar}</div>}
                {windowQ.data.late_risk_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>⚠ تأخير: {windowQ.data.late_risk_ar}</div>}
                {windowQ.data.yemen_note_ar && <div className="text-[11px]" style={{ color: T.muted }}>{windowQ.data.yemen_note_ar}</div>}
                {windowQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{windowQ.data.disclaimer_ar}</div>}
              </>
            ) : null
          )}
        </div>
      )}

      {/* ── آفات ما بعد الحصاد — مرجع الخادم كما هو ── */}
      {open === 'postharvest' && (
        pestsQ.isLoading ? (
          <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة آفات التخزين…</div>
        ) : pestsQ.isError ? (
          <RetryNote q={pestsQ} label="آفات التخزين" />
        ) : pestsQ.data?.disabled ? (
          <DisabledNote />
        ) : pests.length > 0 ? (
          <div className="flex flex-col gap-1 rounded-xl border p-2" style={boxStyle}>
            <div className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
              <Bug className="w-3.5 h-3.5 text-amber-300" aria-hidden="true" /> الآفات المخزنيّة الرئيسيّة:
            </div>
            {pests.map((p) => (
              <div key={p.scientific ?? p.name_ar} className="text-[11px]" style={{ color: T.muted }}>
                <b style={{ color: T.ink }}>{textOrDash(p.name_ar)}</b>
                {p.scientific && <span dir="ltr" style={{ color: T.faint }}> ({p.scientific})</span>}
                {p.note_ar && <> — {p.note_ar}</>}
              </div>
            ))}
            {pestsQ.data?.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{pestsQ.data.note_ar}</div>}
          </div>
        ) : (
          <div className="text-[11px]" style={{ color: T.muted }}>لا آفات مخزنيّة من الخادم بعد.</div>
        )
      )}

      {/* ── محاصيل عالية القيمة/متخصّصة + مرشّحو الإدخال — نصوص الخادم حرفيّاً ── */}
      {open === 'valueCrops' && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
              <Gem className="w-3.5 h-3.5 shrink-0 text-sky-300" aria-hidden="true" />
              <label htmlFor="csk-hv" className="font-bold" style={{ color: T.ink }}>محصول عالي القيمة (بالعربيّة):</label>
              <input id="csk-hv" type="text" value={hvInput} onChange={(e) => setHvInput(e.target.value)} placeholder="جوجوبا" className="w-28 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <button
                type="button"
                onClick={() => setHvName(hvInput.trim() || null)}
                disabled={hvInput.trim() === ''}
                className="text-[10px] px-2 py-0.5 rounded-full font-semibold disabled:opacity-50"
                style={{ border: '1px solid #0c4a6e', color: '#7dd3fc', background: 'rgba(12,74,110,.25)' }}
              >
                التفصيل
              </button>
            </div>
            {hvName == null ? (
              <div className="text-[10px]" style={{ color: T.faint }}>أدخِل اسم المحصول — والخادم يجيب بالتفصيل أو بالمتاح لديه.</div>
            ) : hvQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة التفصيل…</div>
            ) : hvQ.isError ? (
              <RetryNote q={hvQ} label="تفصيل المحصول عالي القيمة" />
            ) : hvQ.data?.disabled ? (
              <DisabledNote />
            ) : serverUnsupportedMessage(hvQ.data) ? (
              <div className="text-[11px]" style={{ color: T.muted }}>{serverUnsupportedMessage(hvQ.data)}</div>
            ) : hvQ.data?.supported ? (
              <>
                <div className="text-[11px] font-bold" style={{ color: T.ink }}>
                  {textOrDash(hvQ.data.name_ar)}
                  {hvQ.data.tier_ar && <span className="font-normal" style={{ color: T.faint }}> · {hvQ.data.tier_ar}</span>}
                </div>
                <DetailRows rows={hvRows} />
                {hvQ.data.caution_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>⚠ {hvQ.data.caution_ar}</div>}
              </>
            ) : null}
          </div>

          <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
              <Gem className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-hidden="true" />
              <label htmlFor="csk-niche" className="font-bold" style={{ color: T.ink }}>منتج تصديري متخصّص (بالعربيّة):</label>
              <input id="csk-niche" type="text" value={nicheInput} onChange={(e) => setNicheInput(e.target.value)} placeholder="الصمغ العربي" className="w-28 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <button
                type="button"
                onClick={() => setNicheName(nicheInput.trim() || null)}
                disabled={nicheInput.trim() === ''}
                className="text-[10px] px-2 py-0.5 rounded-full font-semibold disabled:opacity-50"
                style={{ border: '1px solid #0c4a6e', color: '#7dd3fc', background: 'rgba(12,74,110,.25)' }}
              >
                التفصيل
              </button>
            </div>
            {nicheName == null ? (
              <div className="text-[10px]" style={{ color: T.faint }}>أدخِل اسم المنتج — والخادم يجيب بالتفصيل أو بالمتاح لديه.</div>
            ) : nicheQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة التفصيل…</div>
            ) : nicheQ.isError ? (
              <RetryNote q={nicheQ} label="تفصيل المنتج المتخصّص" />
            ) : nicheQ.data?.disabled ? (
              <DisabledNote />
            ) : serverUnsupportedMessage(nicheQ.data) ? (
              <div className="text-[11px]" style={{ color: T.muted }}>{serverUnsupportedMessage(nicheQ.data)}</div>
            ) : nicheQ.data?.supported ? (
              <>
                <div className="text-[11px] font-bold" style={{ color: T.ink }}>{textOrDash(nicheQ.data.name_ar)}</div>
                <DetailRows rows={nicheRows} />
                {nicheQ.data.caution_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>⚠ {nicheQ.data.caution_ar}</div>}
              </>
            ) : null}
          </div>

          {/* مرشّحو الإدخال — ترشيح الخادم حسب المنطقة (المرتفعات لا تُخلَط بالسهول) */}
          <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
              <Sprout className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-hidden="true" />
              <label htmlFor="csk-zone" className="font-bold" style={{ color: T.ink }}>مرشّحو الإدخال — المنطقة:</label>
              <select id="csk-zone" value={zone} onChange={(e) => setZone(e.target.value)} className="px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle}>
                {INTRODUCTION_ZONE_OPTIONS.map((z) => (
                  <option key={z.key} value={z.key}>{z.label_ar}</option>
                ))}
              </select>
            </div>
            {candidatesQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة مرشّحي الإدخال…</div>
            ) : candidatesQ.isError ? (
              <RetryNote q={candidatesQ} label="مرشّحي الإدخال" />
            ) : candidatesQ.data?.disabled ? (
              <DisabledNote />
            ) : candidates.length > 0 ? (
              <>
                {candidates.map((c) => (
                  <div key={c.crop} className="text-[11px]" style={{ color: T.muted }}>
                    <b style={{ color: T.ink }}>{c.name_ar ?? c.crop}</b>
                    {c.type_ar && <> · {c.type_ar}</>}
                    {c.product_ar && <> · المنتج: {c.product_ar}</>}
                  </div>
                ))}
                {candidatesQ.data?.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{candidatesQ.data.note_ar}</div>}
              </>
            ) : (
              <div className="text-[11px]" style={{ color: T.muted }}>لا مرشّحين من الخادم لهذه المنطقة.</div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
