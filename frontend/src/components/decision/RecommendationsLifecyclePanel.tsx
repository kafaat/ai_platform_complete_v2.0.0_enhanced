import { useState } from 'react';
import { ClipboardCheck, Coins, Cpu, Layers, Plus, Sprout, Trash2 } from 'lucide-react';
import {
  isRecommendationsDisabled, useCapacityProfiles, useEconomicAdaptation,
  useGenerateCandidates, useRecommendationEngines, useRecordRecommendationOutcome,
} from '../../hooks/useRecommendationsLifecycle';
import {
  buildCandidateBodies, buildOutcomeInput, dash, emptyCandidateDraft, emptyOutcomeDraft,
  engineCategoryColor, engineCategoryLabel, engineStatusColor, engineStatusLabel,
  FARMER_GOALS, isEngineEffective, levelLabel, LEVELS, scoreLabel, suitedColor, suitedLabel,
  validateCandidateDrafts, validateOutcomeDraft,
  type CandidateDraft,
} from '../../lib/recommendationsLifecycle';
import { T } from '../ds';

// أنماط مدخلات موحّدة — نفس لغة DecisionInsightPanel (حدود شعريّة + سطح داكن).
const inputStyle = { border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink } as const;
const inputCls = 'px-2 py-1 rounded-lg text-[11px]';

/** نصّ خطأ طفرة للعرض: detail العربيّ من الخادم إن وُجد (422 الموثّقة)، وإلّا
 *  رسالة النقل — لا ابتلاع صامت للخطأ. */
function mutationErrorText(e: unknown): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  return (e as Error)?.message ?? 'خطأ غير معروف';
}

/** رسالة «غير مُفعَّل» الصادقة — 404 يعني المسار غير منشور في هذه البيئة، لا عطلاً. */
function DisabledNote({ what }: { what: string }) {
  return (
    <div className="text-[11px]" style={{ color: T.muted }}>
      {what} غير مُفعَّل في هذه البيئة (المسار يردّ 404) — لا بيانات تُختلَق.
    </div>
  );
}

/** لوحة دورة حياة التوصية: محرّكات التوصيات + طبقات القدرة + بدائل مُقيَّمة حسب
 *  الهدف + تكييف اقتصاديّ + تسجيل النتيجة — نقاط P0 كانت بلا قارئ في الواجهة.
 *  صدق: نصوص الخادم (agency/honesty/disclaimer) تُعرَض حرفيّاً؛ الدرجة كما أُرسلت؛
 *  الصفة المجهولة تُعلَن لا تُخفى؛ النتيجة مجهولة حتى تُقاس (تسجيل المُرسَل فقط)؛
 *  404 ⇒ «غير مُفعَّل» صادقة. كلّ الخيارات تبقى مرئيّة — اقتراح لا فرض. */
export default function RecommendationsLifecyclePanel() {
  const enginesQ = useRecommendationEngines();
  const profilesQ = useCapacityProfiles();
  const candM = useGenerateCandidates();
  const econM = useEconomicAdaptation();
  const outcomeM = useRecordRecommendationOutcome();

  // خيارات المحاصيل (مدخلات مشتركة): يقيّمها /candidates ويرتّبها /economic-adaptation.
  const [drafts, setDrafts] = useState<CandidateDraft[]>([emptyCandidateDraft()]);
  const [goal, setGoal] = useState('max_profit');
  const [draftErr, setDraftErr] = useState<string | null>(null);

  // مدخلات التكييف الاقتصاديّ — اختياريّة (غيابها ⇒ استدلال حذر على الخادم).
  const [areaHa, setAreaHa] = useState('');
  const [revenueUsd, setRevenueUsd] = useState('');

  // مسوّدة تسجيل النتيجة — التحقّق مرآة قواعد الخادم قبل الإرسال (422 مبكّر صادق).
  const [outDraft, setOutDraft] = useState(emptyOutcomeDraft());
  const [outErr, setOutErr] = useState<string | null>(null);

  const setDraft = (i: number, patch: Partial<CandidateDraft>) =>
    setDrafts((ds) => ds.map((d, j) => (j === i ? { ...d, ...patch } : d)));

  const runCandidates = () => {
    const err = validateCandidateDrafts(drafts);
    setDraftErr(err);
    if (err) return;
    candM.mutate({ candidates: buildCandidateBodies(drafts), goal, topN: 3 });
  };

  const runAdaptation = () => {
    const err = validateCandidateDrafts(drafts);
    setDraftErr(err);
    if (err) return;
    const a = Number(areaHa.trim());
    const r = Number(revenueUsd.trim());
    econM.mutate({
      cropOptions: buildCandidateBodies(drafts) as unknown as Record<string, unknown>[],
      areaHa: areaHa.trim() !== '' && Number.isFinite(a) ? a : null,
      annualRevenueUsd: revenueUsd.trim() !== '' && Number.isFinite(r) ? r : null,
    });
  };

  const runOutcome = () => {
    const err = validateOutcomeDraft(outDraft);
    setOutErr(err);
    if (err) return;
    outcomeM.mutate(buildOutcomeInput(outDraft), { onSuccess: () => setOutErr(null) });
  };

  const cand = candM.data;
  const econ = econM.data;

  return (
    <div className="grid gap-3 md:grid-cols-2" data-testid="recommendations-lifecycle">
      {/* محرّكات التوصيات — الكتالوج + السياسة الفعليّة (قراءة فقط) */}
      <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
        <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
          <Cpu className="w-4 h-4 text-emerald-300" aria-hidden="true" /> محرّكات التوصيات
          <span className="text-[11px] font-normal" style={{ color: T.faint }}>
            · فعّال {enginesQ.data?.effective_enabled?.length ?? '—'} من {enginesQ.data?.engines?.length ?? '—'}
          </span>
        </div>
        {enginesQ.isLoading ? (
          <div className="text-[11px]" style={{ color: T.faint }}>جارٍ القراءة…</div>
        ) : enginesQ.isError ? (
          <div className="text-[11px]" role="status" style={{ color: '#fdba74' }}>تعذّرت القراءة — {mutationErrorText(enginesQ.error)}</div>
        ) : enginesQ.data?.disabled ? (
          <DisabledNote what="كتالوج المحرّكات" />
        ) : (enginesQ.data?.engines ?? []).length === 0 ? (
          <div className="text-[11px]" style={{ color: T.muted }}>لا محرّكات في السجلّ.</div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {(enginesQ.data?.engines ?? []).map((e) => {
              const eff = isEngineEffective(e.id, enginesQ.data?.effective_enabled);
              return (
                <div key={e.id} className="text-[11px] flex flex-wrap items-center gap-1.5" style={{ color: T.muted }}>
                  <span className="px-2 py-0.5 rounded-full font-semibold" style={{ border: `1px solid ${T.line}`, color: engineStatusColor(eff) }}>
                    {engineStatusLabel(eff)}
                  </span>
                  <span style={{ color: T.ink }}>{e.name_ar}</span>
                  <span className="px-1.5 rounded" style={{ border: `1px solid ${T.line}`, color: engineCategoryColor(e.category) }}>
                    {engineCategoryLabel(e.category)}
                  </span>
                  <span className="font-mono" style={{ color: T.faint }}>{e.id}</span>
                  {e.required_inputs.length > 0 && (
                    <span style={{ color: T.faint }}>مدخلات: {e.required_inputs.join('، ')}</span>
                  )}
                </div>
              );
            })}
            <div className="text-[10px]" style={{ color: T.faint }}>
              {enginesQ.data?.policy == null
                ? 'لا سياسة مخصَّصة — يسري default_enabled لكلّ محرّك.'
                : 'سياسة مستأجِر مخصَّصة سارية (scope=platform · key=recommendation_engines).'}
            </div>
          </div>
        )}
      </section>

      {/* طبقات القدرة الاقتصاديّة — مرجع شفّاف (قراءة فقط) */}
      <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
        <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
          <Layers className="w-4 h-4 text-sky-300" aria-hidden="true" /> طبقات القدرة الاقتصاديّة
        </div>
        {profilesQ.isLoading ? (
          <div className="text-[11px]" style={{ color: T.faint }}>جارٍ القراءة…</div>
        ) : profilesQ.isError ? (
          <div className="text-[11px]" role="status" style={{ color: '#fdba74' }}>تعذّرت القراءة — {mutationErrorText(profilesQ.error)}</div>
        ) : profilesQ.data?.disabled ? (
          <DisabledNote what="مرجع طبقات القدرة" />
        ) : (
          <div className="flex flex-col gap-1.5 text-[11px]" style={{ color: T.muted }}>
            {(profilesQ.data?.tiers ?? []).map((p) => (
              <div key={p.tier}>
                <span className="font-semibold" style={{ color: T.ink }}>{p.label_ar}</span>
                <span style={{ color: T.faint }}> · {dash(p.typical_area_ha)} · </span>
                {p.investment_posture_ar}
                <span style={{ color: T.faint }}> — الأولويّة: {p.priority_ar}</span>
              </div>
            ))}
            {profilesQ.data?.principle_ar && (
              <div className="text-[10px]" style={{ color: T.faint }}>{profilesQ.data.principle_ar}</div>
            )}
          </div>
        )}
      </section>

      {/* بدائل زراعيّة مُقيَّمة حسب الهدف — كلّ الخيارات مرئيّة (الوكالة) */}
      <section className="rounded-2xl border p-3 md:col-span-2" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
        <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
          <Sprout className="w-4 h-4 text-emerald-300" aria-hidden="true" /> بدائل زراعيّة حسب هدفك
          <span className="text-[11px] font-normal px-1.5 rounded" style={{ border: `1px solid ${T.line}`, color: T.faint }}>
            اقتراح لا فرض — الترتيب توجيه والقرار للمزارع
          </span>
        </div>

        {/* محرّر الخيارات — صفاته الموثّقة هي مدخلات الخادم (لا اختراع قيَم) */}
        <div className="flex flex-col gap-1.5 mb-2">
          {drafts.map((d, i) => (
            <div key={i} className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
              <input value={d.crop_id} onChange={(e) => setDraft(i, { crop_id: e.target.value })}
                placeholder="crop_id" className={`w-24 font-mono ${inputCls}`} style={inputStyle} />
              <input value={d.name_ar} onChange={(e) => setDraft(i, { name_ar: e.target.value })}
                placeholder="الاسم العربيّ" className={`w-28 ${inputCls}`} style={inputStyle} />
              <label className="inline-flex items-center gap-1">
                <input type="checkbox" checked={d.is_suited} onChange={(e) => setDraft(i, { is_suited: e.target.checked })} />
                مناسب إقليميّاً
              </label>
              <label className="inline-flex items-center gap-1">
                حاجة الماء
                <select value={d.water_need_level} onChange={(e) => setDraft(i, { water_need_level: e.target.value })} className={inputCls} style={inputStyle}>
                  {LEVELS.map((l) => <option key={l} value={l}>{levelLabel(l)}</option>)}
                </select>
              </label>
              <label className="inline-flex items-center gap-1">
                التكلفة المسبقة
                <select value={d.upfront_cost_level} onChange={(e) => setDraft(i, { upfront_cost_level: e.target.value })} className={inputCls} style={inputStyle}>
                  {LEVELS.map((l) => <option key={l} value={l}>{levelLabel(l)}</option>)}
                </select>
              </label>
              <label className="inline-flex items-center gap-1">
                إمكان الربح
                {/* «مجهول» خيار صادق — الخادم يعامله محايداً ويُعلِنه في flags_ar */}
                <select value={d.profit_potential_level} onChange={(e) => setDraft(i, { profit_potential_level: e.target.value })} className={inputCls} style={inputStyle}>
                  {['unknown', ...LEVELS].map((l) => <option key={l} value={l}>{levelLabel(l)}</option>)}
                </select>
              </label>
              <label className="inline-flex items-center gap-1">
                <input type="checkbox" checked={d.is_staple} onChange={(e) => setDraft(i, { is_staple: e.target.checked })} />
                محصول أساسي
              </label>
              <input value={d.drought_score} onChange={(e) => setDraft(i, { drought_score: e.target.value })}
                placeholder="تحمّل الجفاف [0–1]" className={`w-28 ${inputCls}`} style={inputStyle} />
              {drafts.length > 1 && (
                <button type="button" onClick={() => setDrafts((ds) => ds.filter((_, j) => j !== i))}
                  title="أزل هذا الخيار" className="p-1 rounded-lg" style={{ border: `1px solid ${T.line}`, color: T.muted }}>
                  <Trash2 className="w-3 h-3" aria-hidden="true" />
                </button>
              )}
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-2 text-[11px]">
            <button type="button" onClick={() => setDrafts((ds) => [...ds, emptyCandidateDraft()])}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-lg" style={{ border: `1px solid ${T.line}`, color: T.muted }}>
              <Plus className="w-3 h-3" aria-hidden="true" /> خيار آخر
            </button>
            <label className="inline-flex items-center gap-1" style={{ color: T.muted }}>
              الهدف
              <select value={goal} onChange={(e) => setGoal(e.target.value)} className={inputCls} style={inputStyle}>
                {FARMER_GOALS.map((g) => <option key={g.id} value={g.id}>{g.label_ar}</option>)}
              </select>
            </label>
            <button type="button" onClick={runCandidates} disabled={candM.isPending}
              className="px-3 py-1 rounded-lg font-semibold" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
              {candM.isPending ? 'جارٍ التقييم…' : 'قيّم البدائل'}
            </button>
            {draftErr && <span role="status" style={{ color: '#fdba74' }}>{draftErr}</span>}
          </div>
        </div>

        {candM.isError && (
          <div className="text-[11px]" role="status" style={{ color: '#fdba74' }}>
            {isRecommendationsDisabled(candM.error)
              ? 'توليد البدائل غير مُفعَّل في هذه البيئة (404) — لا نتيجة تُختلَق.'
              : `تعذّر التقييم — ${mutationErrorText(candM.error)}`}
          </div>
        )}
        {cand && (
          <div className="flex flex-col gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <div style={{ color: T.ink }}>
              الهدف: {cand.goal_ar} <span style={{ color: T.faint }}>· {cand.total_candidates} خياراً — كلّها معروضة، لا حذف</span>
            </div>
            {cand.candidates.map((c) => (
              <div key={c.crop_id} className="flex flex-wrap items-center gap-1.5">
                <span className="font-semibold" style={{ color: T.ink }}>#{c.rank} {c.name_ar}</span>
                {/* الدرجة كما أرسلها الخادم — لا إعادة تقريب تُغيّر القيمة */}
                <span style={{ color: T.faint }}>درجة {scoreLabel(c.score)}</span>
                <span className="px-1.5 rounded" style={{ border: `1px solid ${T.line}`, color: suitedColor(c.is_suited) }}>
                  {suitedLabel(c.is_suited)}
                </span>
                {c.highlighted && <span className="px-1.5 rounded" style={{ border: `1px solid ${T.line}`, color: '#86efac' }}>ضمن المُقترَح</span>}
                {c.flags_ar.map((f) => <span key={f} style={{ color: '#fdba74' }}>⚠ {f}</span>)}
              </div>
            ))}
            {/* نصّا الوكالة والصدق من الخادم — حرفيّاً، لا إعادة صياغة */}
            <div className="text-[10px]" style={{ color: T.faint }}>{cand.agency_note_ar}</div>
            <div className="text-[10px]" style={{ color: T.faint }}>{cand.honesty_note_ar}</div>
          </div>
        )}

        {/* التكييف الاقتصاديّ — يرتّب الخيارات نفسها حسب القدرة (لا حذف) */}
        <div className="mt-3 pt-2" style={{ borderTop: `1px solid ${T.line}` }}>
          <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
            <Coins className="w-4 h-4 text-amber-300" aria-hidden="true" /> التكييف حسب القدرة الاقتصاديّة
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px] mb-2" style={{ color: T.muted }}>
            <input value={areaHa} onChange={(e) => setAreaHa(e.target.value)} placeholder="المساحة (هكتار) — اختياريّ"
              className={`w-44 ${inputCls}`} style={inputStyle} />
            <input value={revenueUsd} onChange={(e) => setRevenueUsd(e.target.value)} placeholder="الدخل السنويّ ($) — اختياريّ"
              className={`w-44 ${inputCls}`} style={inputStyle} />
            <button type="button" onClick={runAdaptation} disabled={econM.isPending}
              className="px-3 py-1 rounded-lg font-semibold" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
              {econM.isPending ? 'جارٍ التكييف…' : 'كيّف الخيارات'}
            </button>
          </div>
          {econM.isError && (
            <div className="text-[11px]" role="status" style={{ color: '#fdba74' }}>
              {isRecommendationsDisabled(econM.error)
                ? 'التكييف الاقتصاديّ غير مُفعَّل في هذه البيئة (404).'
                : `تعذّر التكييف — ${mutationErrorText(econM.error)}`}
            </div>
          )}
          {econ && (
            <div className="flex flex-col gap-1 text-[11px]" style={{ color: T.muted }}>
              <div style={{ color: T.ink }}>
                الطبقة المستنتَجة: {econ.capacity_label_ar}
                <span style={{ color: T.faint }}> · {econ.fit_note_ar}</span>
              </div>
              <div>{econ.investment_posture_ar} <span style={{ color: T.faint }}>— الأولويّة: {econ.economic_priority_ar}</span></div>
              <div className="flex flex-wrap items-center gap-1.5">
                {econ.adapted_options.map((o, i) => (
                  <span key={i} className="px-1.5 rounded" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                    #{i + 1} {dash((o.name_ar ?? o.crop_id) as string)}
                    <span style={{ color: T.faint }}> · تكلفة {levelLabel(o.upfront_cost_level as string | undefined)}</span>
                  </span>
                ))}
              </div>
              {/* نصّا الوكالة والإخلاء من الخادم — حرفيّاً */}
              <div className="text-[10px]" style={{ color: T.faint }}>{econ.agency_note_ar}</div>
              <div className="text-[10px]" style={{ color: T.faint }}>{econ.disclaimer_ar}</div>
            </div>
          )}
        </div>
      </section>

      {/* تسجيل نتيجة توصية — مسار الكتابة لحلقة التعلّم (النتيجة مجهولة حتى تُقاس) */}
      <section className="rounded-2xl border p-3 md:col-span-2" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
        <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
          <ClipboardCheck className="w-4 h-4 text-violet-300" aria-hidden="true" /> تسجيل نتيجة توصية
          <span className="text-[11px] font-normal px-1.5 rounded" style={{ border: `1px solid ${T.line}`, color: T.faint }}>
            يُسجَّل المُرسَل فقط — لا اختراع؛ النتيجة مجهولة حتى تُقاس
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] mb-2" style={{ color: T.muted }}>
          <input value={outDraft.crop} onChange={(e) => setOutDraft({ ...outDraft, crop: e.target.value })}
            placeholder="المحصول (إلزاميّ)" className={`w-32 ${inputCls}`} style={inputStyle} />
          <input value={outDraft.field_id} onChange={(e) => setOutDraft({ ...outDraft, field_id: e.target.value })}
            placeholder="مُعرّف الحقل (إلزاميّ)" className={`w-36 font-mono ${inputCls}`} style={inputStyle} />
          <input value={outDraft.recommendation_id} onChange={(e) => setOutDraft({ ...outDraft, recommendation_id: e.target.value })}
            placeholder="مُعرّف التوصية — اختياريّ" className={`w-40 font-mono ${inputCls}`} style={inputStyle} />
          <input value={outDraft.season_id} onChange={(e) => setOutDraft({ ...outDraft, season_id: e.target.value })}
            placeholder="الموسم — اختياريّ" className={`w-32 ${inputCls}`} style={inputStyle} />
          <input value={outDraft.predicted_yield} onChange={(e) => setOutDraft({ ...outDraft, predicted_yield: e.target.value })}
            placeholder="غلّة متوقَّعة (طن/هـ)" className={`w-36 ${inputCls}`} style={inputStyle} />
          <input value={outDraft.actual_yield} onChange={(e) => setOutDraft({ ...outDraft, actual_yield: e.target.value })}
            placeholder="غلّة فعليّة مقيسة (طن/هـ)" className={`w-40 ${inputCls}`} style={inputStyle} />
          <label className="inline-flex items-center gap-1">
            <input type="checkbox" checked={outDraft.accepted} onChange={(e) => setOutDraft({ ...outDraft, accepted: e.target.checked })} />
            قُبلت التوصية
          </label>
          <label className="inline-flex items-center gap-1" title="يستلزم غلّة فعليّة مقيسة — لا نتيجة بلا قياس">
            <input type="checkbox" checked={outDraft.matured_within_lag} onChange={(e) => setOutDraft({ ...outDraft, matured_within_lag: e.target.checked })} />
            نضجت ضمن المهلة
          </label>
          <button type="button" onClick={runOutcome} disabled={outcomeM.isPending}
            className="px-3 py-1 rounded-lg font-semibold" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
            {outcomeM.isPending ? 'جارٍ التسجيل…' : 'سجّل النتيجة'}
          </button>
        </div>
        {outErr && <div className="text-[11px]" role="status" style={{ color: '#fdba74' }}>{outErr}</div>}
        {outcomeM.isError && (
          <div className="text-[11px]" role="status" style={{ color: '#fdba74' }}>
            {isRecommendationsDisabled(outcomeM.error)
              ? 'تسجيل النتائج غير مُفعَّل في هذه البيئة (404).'
              : `تعذّر التسجيل — ${mutationErrorText(outcomeM.error)}`}
          </div>
        )}
        {outcomeM.isSuccess && (
          <div className="text-[11px]" role="status" style={{ color: '#86efac' }}>
            سُجّلت النتيجة — outcome_id: <span className="font-mono">{String(outcomeM.data.outcome_id)}</span>
            <span style={{ color: T.faint }}> · تقرؤها نقطتا التعلّم والمعايرة حيّاً.</span>
          </div>
        )}
        <div className="mt-1 text-[10px]" style={{ color: T.faint }}>
          «نضجت ضمن المهلة» تستلزم غلّة فعليّة مقيسة (يرفضها الخادم 422 بدونها) — لا حكم نجاح/فشل يُشتقّ هنا.
        </div>
      </section>
    </div>
  );
}
