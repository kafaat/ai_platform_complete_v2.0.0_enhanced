import { useMemo, useState } from 'react';
import { CalendarDays, Gem, Sprout, Stars, TreePine } from 'lucide-react';
import {
  useAromaticCropsList,
  useAstronomicalCrossCheck,
  useCalendarStars,
  useCulturalCalendar,
  useFodderAlternativesList,
  useHighValueCropsList,
  useIntroductionCard,
  useIntroductionFieldFit,
  useNicheCropsList,
  useOrchardEconomics,
  useOrchardPlan,
  useRegionalCalendar,
} from '../../hooks/useSpecialtyCrops';
import {
  ASTRONOMICAL_ANCHOR_OPTIONS,
  INTRODUCTION_ZONE_OPTIONS,
  REGIONAL_GOVERNORATE_OPTIONS,
  aromaticEntries,
  calendarStars,
  culturalNotes,
  economicsStages,
  fieldFitFacts,
  fodderEntries,
  highValueTiers,
  introductionRequirementRows,
  nicheEntries,
  orchardBlocks,
  orchardTimeline,
  ratingColor,
  regionalEntries,
  riskColorAr,
  serverUnsupportedMessage,
  textOrDash,
  usdRange,
  type CropEntry,
  type DetailRow,
  type FieldFitInput,
} from '../../lib/specialtyCrops';
import { parseMeasure } from '../../lib/irrigationDecisionAids';
import { T } from '../ds';

interface Props {
  /** تسمية محصول الحقل النشط — سياق عرض فقط (نقاط المعرفة كلّها محايدة الحقل). */
  cropLabel?: string;
  enabled?: boolean;
}

type SectionKey = 'crops' | 'introduction' | 'orchard' | 'timing' | 'calendars';
type CropTab = 'highValue' | 'niche' | 'aromatic' | 'fodder';

const SECTIONS: { key: SectionKey; label_ar: string }[] = [
  { key: 'crops', label_ar: 'محاصيل متخصّصة' },
  { key: 'introduction', label_ar: 'الإدخال والملاءمة' },
  { key: 'orchard', label_ar: 'البستان المختلط' },
  { key: 'timing', label_ar: 'التوقيت الفلكي' },
  { key: 'calendars', label_ar: 'تقاويم تراثيّة' },
];

const CROP_TABS: { key: CropTab; label_ar: string }[] = [
  { key: 'highValue', label_ar: 'عالية القيمة' },
  { key: 'niche', label_ar: 'تصديريّة متخصّصة' },
  { key: 'aromatic', label_ar: 'عطريّة' },
  { key: 'fodder', label_ar: 'أعلاف بديلة' },
];

const inputStyle = { border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink } as const;
const boxStyle = { borderColor: T.line, background: 'rgba(15,23,42,.35)' } as const;
const pill = (on: boolean) => ({
  border: `1px solid ${on ? '#0c4a6e' : T.line}`,
  color: on ? '#7dd3fc' : T.muted,
  background: on ? 'rgba(12,74,110,.25)' : 'rgba(15,23,42,.45)',
});

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
  return <div className="text-[11px]" style={{ color: T.muted }}>غير مُفعَّلة على هذا الخادم.</div>;
}

function DetailRows({ rows }: { rows: DetailRow[] }) {
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

/** بطاقة محصول مُطبَّع من قائمة الخادم — الاسم + صفوفه، والتحذير/السبب من الخادم حرفيّاً. */
function CropEntryCard({ e }: { e: CropEntry }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg border p-1.5" style={boxStyle}>
      <div className="text-[11px] font-bold" style={{ color: T.ink }}>{e.name}</div>
      <DetailRows rows={e.rows} />
      {e.reason_ar && <div className="text-[11px]" style={{ color: T.muted }}>{e.reason_ar}</div>}
      {e.caution_ar && <div className="text-[10px]" style={{ color: '#fdba74' }}>⚠ {e.caution_ar}</div>}
    </div>
  );
}

/** «المعرفة المتخصّصة والتوقيت التراثيّ»: قوائم المحاصيل عالية القيمة/المتخصّصة/
 *  العطريّة/الأعلاف البديلة + بطاقة الإدخال وفحص ملاءمة الحقل + تخطيط البستان
 *  المختلط واقتصادياته + التوقيت الفلكي الرصدي (نجوم + تحقّق متقاطع مع GDD) +
 *  التقاويم التراثيّة (الثقافي عرضاً فقط، والإقليمي حِميري/حضرمي). النصوص والأحكام
 *  كلّها من الخادم حرفيّاً — الواجهة تعرض ولا تحكم. 404 ⇒ «غير مُفعَّلة» صادقة. */
export default function SpecialtyCropsCard({ cropLabel, enabled = true }: Props) {
  const [open, setOpen] = useState<SectionKey>('crops');
  const [cropTab, setCropTab] = useState<CropTab>('highValue');

  // — قوائم المحاصيل: كلّ قائمة تُجلَب فقط عند فتح قسمها وتحديد تبويبها الفرعيّ —
  const hvQ = useHighValueCropsList(enabled && open === 'crops' && cropTab === 'highValue');
  const nicheQ = useNicheCropsList(enabled && open === 'crops' && cropTab === 'niche');
  const aromaticQ = useAromaticCropsList(enabled && open === 'crops' && cropTab === 'aromatic');
  const fodderQ = useFodderAlternativesList(enabled && open === 'crops' && cropTab === 'fodder');

  // — الإدخال: اسم محصول يؤكّده المستخدم للبطاقة، وفحص ملاءمة كمّي بمدخلات قياس —
  const [introInput, setIntroInput] = useState('');
  const [introCrop, setIntroCrop] = useState<string | null>(null);
  const introQ = useIntroductionCard(introCrop, enabled && open === 'introduction');
  const [phInput, setPhInput] = useState('');
  const [ecInput, setEcInput] = useState('');
  const [rainInput, setRainInput] = useState('');
  const [tempInput, setTempInput] = useState('');
  const [irrigated, setIrrigated] = useState(true);
  const [fitReq, setFitReq] = useState<FieldFitInput | null>(null);
  const submitFit = () => {
    const crop = introInput.trim();
    const ph = parseMeasure(phInput);
    const ec = parseMeasure(ecInput);
    if (!crop || ph == null || ec == null) return; // فحص كمّي لا يُطلَق بلا قياسات كاملة
    const rain = parseMeasure(rainInput);
    const temp = parseMeasure(tempInput);
    setFitReq({
      crop,
      ph,
      ec_dsm: ec,
      ...(rain != null ? { season_rain_mm: rain } : {}),
      ...(temp != null ? { temp_mean_c: temp } : {}),
      irrigated,
    });
  };
  const fitQ = useIntroductionFieldFit(enabled && open === 'introduction' ? fitReq : null);

  // — البستان: مساحة قياس يُدخِلها المستخدم تقود الخطّة والاقتصاد معاً —
  const [areaInput, setAreaInput] = useState('');
  const areaHa = useMemo(() => parseMeasure(areaInput), [areaInput]);
  const planQ = useOrchardPlan(areaHa, enabled && open === 'orchard');
  const [showEconomics, setShowEconomics] = useState(false);
  const econQ = useOrchardEconomics(areaHa, enabled && open === 'orchard' && showEconomics);

  // — التوقيت الفلكي: النجوم عند فتح القسم، والتحقّق المتقاطع بتاريخ من المستخدم —
  const starsQ = useCalendarStars(enabled && open === 'timing');
  const [dateInput, setDateInput] = useState('');
  const [gddInput, setGddInput] = useState('');
  const [anchor, setAnchor] = useState('suhail_rising');
  const [ccReq, setCcReq] = useState<{ current_date: string; gdd_stage?: string | null; anchor?: string } | null>(null);
  const submitCc = () => {
    const d = dateInput.trim();
    if (!d) return; // لا تحقّق بلا تاريخ (لا تخمين)
    setCcReq({ current_date: d, anchor, ...(gddInput.trim() ? { gdd_stage: gddInput.trim() } : {}) });
  };
  const ccQ = useAstronomicalCrossCheck(enabled && open === 'timing' ? ccReq : null);

  // — التقاويم: الثقافي (عرض فقط) عند فتح القسم، والإقليمي حسب محافظة يختارها المستخدم —
  const culturalQ = useCulturalCalendar(null, enabled && open === 'calendars');
  const [gov, setGov] = useState('');
  const regionalQ = useRegionalCalendar(gov || null, enabled && open === 'calendars');

  const hvTiers = useMemo(() => highValueTiers(hvQ.data), [hvQ.data]);
  const nicheList = useMemo(() => nicheEntries(nicheQ.data), [nicheQ.data]);
  const aromaticList = useMemo(() => aromaticEntries(aromaticQ.data), [aromaticQ.data]);
  const fodderList = useMemo(() => fodderEntries(fodderQ.data), [fodderQ.data]);
  const reqRows = useMemo(() => introductionRequirementRows(introQ.data), [introQ.data]);
  const fitFacts = useMemo(() => fieldFitFacts(fitQ.data), [fitQ.data]);
  const blocks = useMemo(() => orchardBlocks(planQ.data), [planQ.data]);
  const timeline = useMemo(() => orchardTimeline(planQ.data), [planQ.data]);
  const stages = useMemo(() => economicsStages(econQ.data), [econQ.data]);
  const stars = useMemo(() => calendarStars(starsQ.data), [starsQ.data]);
  const notes = useMemo(() => culturalNotes(culturalQ.data), [culturalQ.data]);
  const regEntries = useMemo(() => regionalEntries(regionalQ.data), [regionalQ.data]);

  if (!enabled) return null;

  const TIER_HEAD: Record<string, string> = {
    proven: 'مثبتة للجوف',
    conditional: 'ممكنة بحذر',
    not_suited: '⚠ غير مناسبة (صدق)',
  };

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="specialty-crops" aria-label="المعرفة المتخصّصة والتوقيت التراثيّ">
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Gem className="w-4 h-4 text-sky-300" aria-hidden="true" /> معرفة متخصّصة وتوقيت تراثيّ
          {cropLabel && <span className="text-[11px]" style={{ color: T.faint }}>· {cropLabel}</span>}
        </span>
      </div>

      {/* أقسام قابلة للطيّ — استعلام كلّ قسم لا يُطلق إلّا عند فتحه (لا استدعاء ميّت). */}
      <div className="flex flex-wrap items-center gap-1.5 mb-2">
        {SECTIONS.map((s) => (
          <button key={s.key} type="button" onClick={() => setOpen(s.key)} className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={pill(open === s.key)}>
            {s.label_ar}
          </button>
        ))}
      </div>

      {/* ── قوائم المحاصيل المتخصّصة — تبويب فرعيّ، والقائمة المختارة فقط تُجلَب ── */}
      {open === 'crops' && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {CROP_TABS.map((t) => (
              <button key={t.key} type="button" onClick={() => setCropTab(t.key)} className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={pill(cropTab === t.key)}>
                {t.label_ar}
              </button>
            ))}
          </div>

          {/* عالية القيمة — ثلاث طبقات صدق (مثبتة/بحذر/غير مناسبة) */}
          {cropTab === 'highValue' && (
            hvQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة المحاصيل عالية القيمة…</div>
            ) : hvQ.isError ? (
              <RetryNote q={hvQ} label="المحاصيل عالية القيمة" />
            ) : hvQ.data?.disabled ? (
              <DisabledNote />
            ) : hvTiers.length > 0 ? (
              <div className="flex flex-col gap-2">
                {hvTiers.map((tier) => (
                  <div key={tier.key} className="flex flex-col gap-1">
                    <div className="text-[11px] font-bold" style={{ color: T.ink }}>{TIER_HEAD[tier.key]}</div>
                    {tier.intro_ar && <div className="text-[10px]" style={{ color: T.faint }}>{tier.intro_ar}</div>}
                    {tier.entries.map((e) => <CropEntryCard key={e.name} e={e} />)}
                  </div>
                ))}
                {hvQ.data?.recommended_mix_ar && <div className="text-[11px]" style={{ color: T.muted }}>{hvQ.data.recommended_mix_ar}</div>}
                {hvQ.data?.principle_ar && <div className="text-[10px]" style={{ color: T.faint }}>{hvQ.data.principle_ar}</div>}
                {hvQ.data?.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{hvQ.data.disclaimer_ar}</div>}
              </div>
            ) : (
              <div className="text-[11px]" style={{ color: T.muted }}>لا قائمة من الخادم بعد.</div>
            )
          )}

          {/* تصديريّة متخصّصة */}
          {cropTab === 'niche' && (
            nicheQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة المنتجات المتخصّصة…</div>
            ) : nicheQ.isError ? (
              <RetryNote q={nicheQ} label="المنتجات المتخصّصة" />
            ) : nicheQ.data?.disabled ? (
              <DisabledNote />
            ) : nicheList.length > 0 ? (
              <div className="flex flex-col gap-1.5">
                {nicheList.map((e) => <CropEntryCard key={e.name} e={e} />)}
                {nicheQ.data?.yemen_heritage_edge_ar && <div className="text-[11px]" style={{ color: T.muted }}>{nicheQ.data.yemen_heritage_edge_ar}</div>}
                {nicheQ.data?.principle_ar && <div className="text-[10px]" style={{ color: T.faint }}>{nicheQ.data.principle_ar}</div>}
                {nicheQ.data?.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{nicheQ.data.disclaimer_ar}</div>}
              </div>
            ) : (
              <div className="text-[11px]" style={{ color: T.muted }}>لا قائمة من الخادم بعد.</div>
            )
          )}

          {/* عطريّة */}
          {cropTab === 'aromatic' && (
            aromaticQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة النباتات العطريّة…</div>
            ) : aromaticQ.isError ? (
              <RetryNote q={aromaticQ} label="النباتات العطريّة" />
            ) : aromaticQ.data?.disabled ? (
              <DisabledNote />
            ) : aromaticList.length > 0 ? (
              <div className="flex flex-col gap-1.5">
                {aromaticList.map((e) => <CropEntryCard key={e.name} e={e} />)}
                {aromaticQ.data?.principle_ar && <div className="text-[10px]" style={{ color: T.faint }}>{aromaticQ.data.principle_ar}</div>}
                {aromaticQ.data?.value_chain_ar && <div className="text-[10px]" style={{ color: T.faint }}>{aromaticQ.data.value_chain_ar}</div>}
                {aromaticQ.data?.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{aromaticQ.data.disclaimer_ar}</div>}
              </div>
            ) : (
              <div className="text-[11px]" style={{ color: T.muted }}>لا قائمة من الخادم بعد.</div>
            )
          )}

          {/* أعلاف بديلة */}
          {cropTab === 'fodder' && (
            fodderQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة الأعلاف البديلة…</div>
            ) : fodderQ.isError ? (
              <RetryNote q={fodderQ} label="الأعلاف البديلة" />
            ) : fodderQ.data?.disabled ? (
              <DisabledNote />
            ) : fodderList.length > 0 ? (
              <div className="flex flex-col gap-1.5">
                {fodderQ.data?.problem_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>{fodderQ.data.problem_ar}</div>}
                {fodderList.map((e) => <CropEntryCard key={e.name} e={e} />)}
                {fodderQ.data?.best_ar && <div className="text-[11px]" style={{ color: T.muted }}>{fodderQ.data.best_ar}</div>}
                {fodderQ.data?.principle_ar && <div className="text-[10px]" style={{ color: T.faint }}>{fodderQ.data.principle_ar}</div>}
                {fodderQ.data?.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{fodderQ.data.disclaimer_ar}</div>}
              </div>
            ) : (
              <div className="text-[11px]" style={{ color: T.muted }}>لا قائمة من الخادم بعد.</div>
            )
          )}
        </div>
      )}

      {/* ── الإدخال والملاءمة: بطاقة تعريفيّة + فحص ملاءمة كمّي بمحرّك الخادم ── */}
      {open === 'introduction' && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
              <Sprout className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-hidden="true" />
              <label htmlFor="sc-intro" className="font-bold" style={{ color: T.ink }}>محصول الإدخال (اسم/مفتاح):</label>
              <input id="sc-intro" type="text" value={introInput} onChange={(e) => setIntroInput(e.target.value)} placeholder="مانجو / olive" className="w-28 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <button type="button" onClick={() => setIntroCrop(introInput.trim() || null)} disabled={introInput.trim() === ''} className="text-[10px] px-2 py-0.5 rounded-full font-semibold disabled:opacity-50" style={{ border: '1px solid #0c4a6e', color: '#7dd3fc', background: 'rgba(12,74,110,.25)' }}>
                البطاقة
              </button>
            </div>
            {introCrop == null ? (
              <div className="text-[10px]" style={{ color: T.faint }}>أدخِل اسم المحصول — والخادم يجيب بالبطاقة التعريفيّة أو بالمتاح لديه.</div>
            ) : introQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة البطاقة…</div>
            ) : introQ.isError ? (
              <RetryNote q={introQ} label="بطاقة الإدخال" />
            ) : introQ.data?.disabled ? (
              <DisabledNote />
            ) : serverUnsupportedMessage(introQ.data) ? (
              <div className="text-[11px]" style={{ color: T.muted }}>{serverUnsupportedMessage(introQ.data)}</div>
            ) : introQ.data?.supported ? (
              <>
                <div className="text-[11px] font-bold" style={{ color: T.ink }}>
                  {textOrDash(introQ.data.name_ar)}
                  {introQ.data.type_ar && <span className="font-normal" style={{ color: T.faint }}> · {introQ.data.type_ar}</span>}
                </div>
                {introQ.data.suitable_zone_ar && <div className="text-[11px]" style={{ color: T.muted }}><b style={{ color: T.ink }}>المنطقة:</b> {introQ.data.suitable_zone_ar}</div>}
                <DetailRows rows={reqRows} />
                {introQ.data.season_ar && <div className="text-[11px]" style={{ color: T.muted }}><b style={{ color: T.ink }}>الموسم:</b> {introQ.data.season_ar}</div>}
                {introQ.data.product_ar && <div className="text-[11px]" style={{ color: T.muted }}><b style={{ color: T.ink }}>المنتج:</b> {introQ.data.product_ar}</div>}
                {introQ.data.inspiration_ar && <div className="text-[11px]" style={{ color: T.muted }}>{introQ.data.inspiration_ar}</div>}
                {introQ.data.yemen_fit_ar && <div className="text-[11px]" style={{ color: T.muted }}>{introQ.data.yemen_fit_ar}</div>}
                {introQ.data.caution_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>⚠ {introQ.data.caution_ar}</div>}
                {introQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{introQ.data.disclaimer_ar}</div>}
              </>
            ) : null}
          </div>

          {/* فحص ملاءمة كمّي — قياسات حقيقيّة من المستخدم، الحكم (التقييم) من الخادم */}
          <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
              <span className="font-bold" style={{ color: T.ink }}>فحص ملاءمة حقلك للمحصول أعلاه:</span>
            </div>
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
              <label htmlFor="sc-ph" className="font-bold" style={{ color: T.ink }}>الحموضة pH:</label>
              <input id="sc-ph" type="number" step="0.1" value={phInput} onChange={(e) => setPhInput(e.target.value)} placeholder="من قياس" className="w-16 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <label htmlFor="sc-ec" className="font-bold" style={{ color: T.ink }}>الملوحة EC (dS/m):</label>
              <input id="sc-ec" type="number" step="0.1" value={ecInput} onChange={(e) => setEcInput(e.target.value)} placeholder="من قياس" className="w-16 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <label htmlFor="sc-rain" className="font-bold" style={{ color: T.ink }}>المطر الموسمي (مم، اختياري):</label>
              <input id="sc-rain" type="number" step="1" value={rainInput} onChange={(e) => setRainInput(e.target.value)} placeholder="—" className="w-16 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <label htmlFor="sc-temp" className="font-bold" style={{ color: T.ink }}>متوسّط الحرارة (°م، اختياري):</label>
              <input id="sc-temp" type="number" step="0.5" value={tempInput} onChange={(e) => setTempInput(e.target.value)} placeholder="—" className="w-16 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <label className="inline-flex items-center gap-1 font-bold" style={{ color: T.ink }}>
                <input type="checkbox" checked={irrigated} onChange={(e) => setIrrigated(e.target.checked)} /> مرويّ
              </label>
              <button type="button" onClick={submitFit} disabled={introInput.trim() === '' || phInput.trim() === '' || ecInput.trim() === ''} className="text-[10px] px-2 py-0.5 rounded-full font-semibold disabled:opacity-50" style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(20,83,45,.25)' }}>
                افحص الملاءمة
              </button>
            </div>
            {fitReq == null ? (
              <div className="text-[10px]" style={{ color: T.faint }}>أدخِل المحصول + الحموضة + الملوحة (من قياس) — الحكم من محرّك الخادم لا الواجهة.</div>
            ) : fitQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ فحص الملاءمة…</div>
            ) : fitQ.isError ? (
              <RetryNote q={fitQ} label="فحص الملاءمة" />
            ) : fitQ.data?.disabled ? (
              <DisabledNote />
            ) : serverUnsupportedMessage(fitQ.data) ? (
              <div className="text-[11px]" style={{ color: T.muted }}>{serverUnsupportedMessage(fitQ.data)}</div>
            ) : fitQ.data?.scored === false ? (
              <div className="text-[11px]" style={{ color: T.muted }}>{textOrDash(fitQ.data.message_ar)}</div>
            ) : fitQ.data?.scored ? (
              <>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] font-bold" style={{ color: T.ink }}>{textOrDash(fitQ.data.name_ar)}</span>
                  {fitFacts.map((f) => (
                    <span key={f.label} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: f.label === 'التقييم' ? ratingColor(fitQ.data?.rating_ar) : T.ink }}>
                      <span style={{ color: T.faint }}>{f.label}:</span> {f.value}
                    </span>
                  ))}
                </div>
                {(fitQ.data.reasons_ar ?? []).map((r) => (
                  <div key={r} className="text-[11px]" style={{ color: T.muted }}>• {r}</div>
                ))}
                {fitQ.data.yemen_fit_ar && <div className="text-[11px]" style={{ color: T.muted }}>{fitQ.data.yemen_fit_ar}</div>}
                {fitQ.data.caution_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>⚠ {fitQ.data.caution_ar}</div>}
                {fitQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{fitQ.data.disclaimer_ar}</div>}
              </>
            ) : null}
            <div className="text-[10px]" style={{ color: T.faint }}>مناطق الإدخال: {INTRODUCTION_ZONE_OPTIONS.map((z) => z.label_ar).join('، ')}.</div>
          </div>
        </div>
      )}

      {/* ── البستان المختلط: خطّة (توزيع + كثافة + جدول عائد) + اقتصاد تقديريّ ── */}
      {open === 'orchard' && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <TreePine className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-hidden="true" />
            <label htmlFor="sc-area" className="font-bold" style={{ color: T.ink }}>المساحة (هكتار):</label>
            <input id="sc-area" type="number" min="0" step="0.1" value={areaInput} onChange={(e) => setAreaInput(e.target.value)} placeholder="من قياس" className="w-20 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
          </div>

          {areaHa == null || areaHa <= 0 ? (
            <div className="text-[10px]" style={{ color: T.faint }}>أدخِل مساحة موجبة بالهكتار لتخطيط البستان المختلط.</div>
          ) : planQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تخطيط البستان…</div>
          ) : planQ.isError ? (
            <RetryNote q={planQ} label="خطّة البستان" />
          ) : planQ.data?.disabled ? (
            <DisabledNote />
          ) : serverUnsupportedMessage(planQ.data) ? (
            <div className="text-[11px]" style={{ color: T.muted }}>{serverUnsupportedMessage(planQ.data)}</div>
          ) : planQ.data?.supported ? (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
              {planQ.data.model_ar && <div className="text-[11px] font-bold" style={{ color: T.ink }}>{planQ.data.model_ar}</div>}
              {planQ.data.philosophy_ar && <div className="text-[11px]" style={{ color: T.muted }}>{planQ.data.philosophy_ar}</div>}
              {blocks.map((b) => (
                <div key={b.crop_ar} className="flex flex-col gap-0.5 rounded-lg border p-1.5" style={boxStyle}>
                  <div className="text-[11px] font-bold" style={{ color: T.ink }}>
                    {textOrDash(b.crop_ar)}
                    {b.role_ar && <span className="font-normal" style={{ color: T.faint }}> · {b.role_ar}</span>}
                    {b.risk_ar && <span className="ms-1 text-[10px]" style={{ color: riskColorAr(b.risk_ar) }}>مخاطرة: {b.risk_ar}</span>}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {b.trees != null && <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}><span style={{ color: T.faint }}>الأشجار:</span> {b.trees}{b.males_note_ar ?? ''}</span>}
                    {b.area_ha != null && <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}><span style={{ color: T.faint }}>المساحة:</span> {b.area_ha} هـ</span>}
                    {b.spacing_m && <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}><span style={{ color: T.faint }}>المسافة:</span> {b.spacing_m}</span>}
                    {b.water_ar && <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}><span style={{ color: T.faint }}>الماء:</span> {b.water_ar}</span>}
                  </div>
                  {b.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{b.note_ar}</div>}
                </div>
              ))}
              {planQ.data.total_trees != null && <div className="text-[11px]" style={{ color: T.muted }}><b style={{ color: T.ink }}>إجمالي الأشجار:</b> {planQ.data.total_trees}</div>}
              {timeline.length > 0 && (
                <div className="flex flex-col gap-0.5">
                  <div className="text-[11px] font-bold" style={{ color: T.ink }}>جدول التدفّق النقدي:</div>
                  {timeline.map((t) => (
                    <div key={t.year} className="text-[10px]" style={{ color: T.muted }}>السنة {t.year}: {(t.events_ar ?? []).join('، ')}</div>
                  ))}
                </div>
              )}
              {planQ.data.layout_advice_ar && <div className="text-[10px]" style={{ color: T.faint }}>{planQ.data.layout_advice_ar}</div>}
              {planQ.data.irrigation_ar && <div className="text-[10px]" style={{ color: T.faint }}>{planQ.data.irrigation_ar}</div>}
              {planQ.data.arid_warning_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>{planQ.data.arid_warning_ar}</div>}
              {planQ.data.strategy_ar && <div className="text-[10px]" style={{ color: T.faint }}>{planQ.data.strategy_ar}</div>}
              {planQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{planQ.data.disclaimer_ar}</div>}
            </div>
          ) : null}

          {/* اقتصاد تقديريّ — سيناريو لا وعد (يُجلَب عند الطلب فقط) */}
          {areaHa != null && areaHa > 0 && (
            <button type="button" onClick={() => setShowEconomics((v) => !v)} className="self-start text-[10px] px-2 py-0.5 rounded-full font-semibold" style={pill(showEconomics)}>
              ملاحظات اقتصاديّة تقديريّة
            </button>
          )}
          {showEconomics && areaHa != null && areaHa > 0 && (
            econQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة الاقتصاد التقديريّ…</div>
            ) : econQ.isError ? (
              <RetryNote q={econQ} label="اقتصاد البستان" />
            ) : econQ.data?.disabled ? (
              <DisabledNote />
            ) : serverUnsupportedMessage(econQ.data) ? (
              <div className="text-[11px]" style={{ color: T.muted }}>{serverUnsupportedMessage(econQ.data)}</div>
            ) : econQ.data?.supported ? (
              <div className="flex flex-col gap-1 rounded-xl border p-2" style={boxStyle}>
                {econQ.data.establishment_usd_range && <div className="text-[11px]" style={{ color: T.muted }}><b style={{ color: T.ink }}>تكلفة التأسيس:</b> {usdRange(econQ.data.establishment_usd_range)}</div>}
                {stages.length > 0 && (
                  <div className="flex flex-col gap-0.5">
                    <div className="text-[11px] font-bold" style={{ color: T.ink }}>الدخل السنويّ التقديريّ:</div>
                    {stages.map((s) => (
                      <div key={s.years} className="text-[10px]" style={{ color: T.muted }}>سنوات {textOrDash(s.years)}: {usdRange(s.usd_range)}{s.note_ar ? ` — ${s.note_ar}` : ''}</div>
                    ))}
                  </div>
                )}
                {Array.isArray(econQ.data.high_risks_ar) && econQ.data.high_risks_ar.length > 0 && (
                  <div className="text-[10px]" style={{ color: '#fdba74' }}>مخاطر عالية: {econQ.data.high_risks_ar.join('، ')}</div>
                )}
                {econQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{econQ.data.disclaimer_ar}</div>}
              </div>
            ) : null
          )}
        </div>
      )}

      {/* ── التوقيت الفلكي الرصدي (لا تنجيم): نجوم المرساة + تحقّق متقاطع مع GDD ── */}
      {open === 'timing' && (
        <div className="flex flex-col gap-2">
          {starsQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة نجوم التقويم…</div>
          ) : starsQ.isError ? (
            <RetryNote q={starsQ} label="نجوم التقويم" />
          ) : starsQ.data?.disabled ? (
            <DisabledNote />
          ) : stars.length > 0 ? (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
              <div className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
                <Stars className="w-3.5 h-3.5 text-amber-300" aria-hidden="true" /> {textOrDash(starsQ.data?.purpose_ar)}
              </div>
              {stars.map((s) => (
                <div key={s.name_ar} className="flex flex-col gap-0.5 rounded-lg border p-1.5" style={boxStyle}>
                  <div className="text-[11px] font-bold" style={{ color: T.ink }}>{textOrDash(s.name_ar)}<span className="font-normal" style={{ color: T.faint }}> · {textOrDash(s.heliacal_rising_approx)}</span></div>
                  {s.season_marker_ar && <div className="text-[11px]" style={{ color: T.muted }}>{s.season_marker_ar}</div>}
                  {s.agricultural_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{s.agricultural_note_ar}</div>}
                </div>
              ))}
              {starsQ.data?.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{starsQ.data.disclaimer_ar}</div>}
            </div>
          ) : (
            <div className="text-[11px]" style={{ color: T.muted }}>لا نجوم من الخادم بعد.</div>
          )}

          {/* تحقّق متقاطع — تاريخ من المستخدم + مرحلة GDD اختياريّة + مرساة */}
          <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
              <label htmlFor="sc-date" className="font-bold" style={{ color: T.ink }}>التاريخ (YYYY-MM-DD):</label>
              <input id="sc-date" type="date" value={dateInput} onChange={(e) => setDateInput(e.target.value)} className="px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <label htmlFor="sc-gdd" className="font-bold" style={{ color: T.ink }}>مرحلة GDD (اختياري):</label>
              <input id="sc-gdd" type="text" value={gddInput} onChange={(e) => setGddInput(e.target.value)} placeholder="—" className="w-24 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <label htmlFor="sc-anchor" className="font-bold" style={{ color: T.ink }}>المرساة:</label>
              <select id="sc-anchor" value={anchor} onChange={(e) => setAnchor(e.target.value)} className="px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle}>
                {ASTRONOMICAL_ANCHOR_OPTIONS.map((a) => <option key={a.key} value={a.key}>{a.label_ar}</option>)}
              </select>
              <button type="button" onClick={submitCc} disabled={dateInput.trim() === ''} className="text-[10px] px-2 py-0.5 rounded-full font-semibold disabled:opacity-50" style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(20,83,45,.25)' }}>
                تحقّق
              </button>
            </div>
            {ccReq == null ? (
              <div className="text-[10px]" style={{ color: T.faint }}>أدخِل التاريخ لتحقّق متقاطع بين المرساة الفلكيّة ومرحلة GDD (اتّفاق=ثقة، اختلاف=تنبيه).</div>
            ) : ccQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ التحقّق المتقاطع…</div>
            ) : ccQ.isError ? (
              <RetryNote q={ccQ} label="التحقّق المتقاطع" />
            ) : ccQ.data?.disabled ? (
              <DisabledNote />
            ) : ccQ.data?.error_ar ? (
              <div className="text-[11px]" style={{ color: '#fdba74' }}>{ccQ.data.error_ar}</div>
            ) : ccQ.data ? (
              <>
                <div className="flex flex-wrap gap-1.5">
                  {ccQ.data.star_anchor_ar && <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}><span style={{ color: T.faint }}>المرساة:</span> {ccQ.data.star_anchor_ar}</span>}
                  {ccQ.data.days_from_anchor != null && <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}><span style={{ color: T.faint }}>الأيّام من المرساة:</span> {ccQ.data.days_from_anchor}</span>}
                  {ccQ.data.gdd_stage && <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}><span style={{ color: T.faint }}>GDD:</span> {ccQ.data.gdd_stage}</span>}
                </div>
                {ccQ.data.agreement_ar && <div className="text-[11px]" style={{ color: T.muted }}>{ccQ.data.agreement_ar}</div>}
              </>
            ) : null}
          </div>
        </div>
      )}

      {/* ── التقاويم التراثيّة: الثقافي (عرض فقط خارج القرار) + الإقليمي حِميري/حضرمي ── */}
      {open === 'calendars' && (
        <div className="flex flex-col gap-2">
          {/* التقويم الثقافي — وسم صريح أنّه لا يدخل محرّك القرار */}
          {culturalQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة التقويم الثقافي…</div>
          ) : culturalQ.isError ? (
            <RetryNote q={culturalQ} label="التقويم الثقافي" />
          ) : culturalQ.data?.disabled ? (
            <DisabledNote />
          ) : notes.length > 0 ? (
            <div className="flex flex-col gap-1 rounded-xl border p-2" style={boxStyle}>
              <div className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
                <CalendarDays className="w-3.5 h-3.5 text-sky-300" aria-hidden="true" /> تقويم ثقافي تراثيّ (عرض فقط)
              </div>
              {notes.map((n) => (
                <div key={n.name_ar} className="text-[11px]" style={{ color: T.muted }}>
                  <b style={{ color: T.ink }}>{textOrDash(n.name_ar)}</b>
                  {n.period_ar && <span style={{ color: T.faint }}> · {n.period_ar}</span>}
                  {n.traditional_practice_ar && <> — {n.traditional_practice_ar}</>}
                </div>
              ))}
              {culturalQ.data?.disclaimer_ar && <div className="text-[10px]" style={{ color: '#fdba74' }}>{culturalQ.data.disclaimer_ar}</div>}
            </div>
          ) : (
            <div className="text-[11px]" style={{ color: T.muted }}>لا تقويم ثقافي من الخادم بعد.</div>
          )}

          {/* التقويم الإقليمي — حسب محافظة يختارها المستخدم (لا تقويم موحّد) */}
          <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
              <label htmlFor="sc-gov" className="font-bold" style={{ color: T.ink }}>التقويم الإقليمي — المحافظة:</label>
              <select id="sc-gov" value={gov} onChange={(e) => setGov(e.target.value)} className="px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle}>
                <option value="">اختر محافظة…</option>
                {REGIONAL_GOVERNORATE_OPTIONS.map((g) => <option key={g.key} value={g.key}>{g.label_ar}</option>)}
              </select>
            </div>
            {gov === '' ? (
              <div className="text-[10px]" style={{ color: T.faint }}>اختر محافظة — لكلّ منطقة تقويمها (حِميري للهضبة، حضرمي للوادي).</div>
            ) : regionalQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة التقويم الإقليمي…</div>
            ) : regionalQ.isError ? (
              <RetryNote q={regionalQ} label="التقويم الإقليمي" />
            ) : regionalQ.data?.disabled ? (
              <DisabledNote />
            ) : regionalQ.data?.matched === false ? (
              <div className="text-[11px]" style={{ color: T.muted }}>{textOrDash(regionalQ.data.message_ar)}</div>
            ) : regionalQ.data?.matched ? (
              <>
                <div className="text-[11px] font-bold" style={{ color: T.ink }}>{textOrDash(regionalQ.data.name_ar)}</div>
                {regionalQ.data.structure_ar && <div className="text-[10px]" style={{ color: T.faint }}>{regionalQ.data.structure_ar}</div>}
                {regionalQ.data.region_ar && <div className="text-[10px]" style={{ color: T.faint }}>{regionalQ.data.region_ar}</div>}
                {regEntries.map((e) => (
                  <div key={e.period_name_ar} className="text-[11px]" style={{ color: T.muted }}>
                    <b style={{ color: T.ink }}>{textOrDash(e.period_name_ar)}</b>
                    {e.approx_gregorian_ar && <span style={{ color: T.faint }}> · {e.approx_gregorian_ar}</span>}
                    {e.agricultural_meaning_ar && <> — {e.agricultural_meaning_ar}</>}
                  </div>
                ))}
                {regionalQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{regionalQ.data.disclaimer_ar}</div>}
              </>
            ) : null}
          </div>
        </div>
      )}
    </section>
  );
}
