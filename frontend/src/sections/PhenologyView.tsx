// ═══════════════════════════════════════════════════════════════
// SAHOOL — عرض الأطوار الفينولوجيّة (Phenology / Growth Stages)
// ───────────────────────────────────────────────────────────────
// شاشة قراءة فقط تعرض مراحل نموّ الموسم الزراعيّ (BBCH/مواسم) لحقلٍ مُختار،
// مع تتبّع GDD المُخزَّن من المحاكاة عند توفّره. كلّ البيانات حقيقيّة من
// نقطة kong المُثبَتة GET /api/v1/fields/{id}/seasons (SeasonSummary[]):
//   • stages: مصفوفة مراحل المستخدم {name, date, notes} — التايم‑لاين منها حرفيّاً.
//   • sowing_date / season_end: مرساة الموسم (التقدّم الزمنيّ).
//   • sim_gdd_total: درجات حرارة تراكميّة (GDD) — تُملأ فقط بعد /simulate، وإلّا null.
//
// صدق البيانات: لا مرحلة مُلفَّقة — التايم‑لاين هو مصفوفة stages كما خُزِّنت. المرحلة
// «الحاليّة» تُشتقّ بمقارنة تاريخ اليوم بتواريخ المراحل المُرتَّبة (آخر مرحلة بلغ
// تاريخُها ≤ اليوم). إن غابت التواريخ ⇒ لا تمييز زمنيّ (تُعرَض قائمةً محايدة).
// GDD يُعرَض «—» إن لم يُشغَّل /simulate. الحالات (تحميل/خطأ/فراغ) صريحة.
// ═══════════════════════════════════════════════════════════════
import { useMemo } from 'react';
import { Sprout, Leaf, Calendar, Thermometer, Flag, MapPin, CircleDot } from 'lucide-react';
import { useSeasons } from '../hooks/useApi';
import { type SeasonSummary } from '../services/api';
import { useSelectedField } from '../hooks/useSelectedField';
import { fmtDateAr } from '../lib/dates';
import { T, Card, Pill, Badge, SectionLabel, ProgressBar, FieldCabin } from '../components/ds';

// مرحلة نموّ واحدة كما تُخزَّن في stages (JSONB): {name, date, notes}.
// قراءة متسامحة (الحقول Record<string, unknown>) — نُطبّع إلى نصوص بأمان.
interface Stage {
  name: string;
  date: string;   // ISO أو '' (قد تغيب)
  notes: string;
}

function toStage(raw: Record<string, unknown>): Stage {
  const s = (v: unknown) => (typeof v === 'string' ? v : '');
  return { name: s(raw.name), date: s(raw.date), notes: s(raw.notes) };
}

// زمن المرحلة (ms) أو null إن غاب/تعذّر تحليلُه — لا نُرتّب على قيمة مُخمَّنة.
function stageTime(date: string): number | null {
  if (!date) return null;
  const t = new Date(date).getTime();
  return Number.isNaN(t) ? null : t;
}

// يختار الموسم النشط إن وُجد، وإلّا الأحدث (المصفوفة مُرتَّبة الأحدث أولاً خلفيّاً).
function pickSeason(seasons: SeasonSummary[]): SeasonSummary | null {
  if (!seasons.length) return null;
  return seasons.find((s) => s.status === 'active') ?? seasons[0];
}

// حالة الموسم بالعربيّة (للوسم) — لا تخمين، نعرض القيمة الخام إن لم تُعرَف.
function seasonStatusAr(status: string): string {
  if (status === 'active') return 'نشط';
  if (status === 'closed') return 'مُغلَق';
  if (status === 'planned') return 'مُخطَّط';
  return status || '—';
}

export default function PhenologyView() {
  // «الحقل النشط» المشترك (useSelectedField) — يتبع المستخدم عبر الشاشات.
  const { options: fields, isLoading: fieldsLoading, isError: fieldsError, refetch, fieldId, setFieldId } = useSelectedField();

  const seasonsQ = useSeasons(fieldId || undefined);
  const seasons = useMemo<SeasonSummary[]>(
    () => (Array.isArray(seasonsQ.data) ? seasonsQ.data : []),
    [seasonsQ.data],
  );
  const season = useMemo(() => pickSeason(seasons), [seasons]);

  // مراحل الموسم مُطبَّعة ومُرتَّبة زمنيّاً (المراحل بلا تاريخ تبقى في آخر القائمة
  // محافظةً على ترتيب الإدخال) — لا قيم مُلفَّقة، فقط ترتيب آمن للعرض.
  const stages = useMemo<Stage[]>(() => {
    if (!season) return [];
    const list = (Array.isArray(season.stages) ? season.stages : []).map(toStage);
    return [...list].sort((a, b) => {
      const ta = stageTime(a.date);
      const tb = stageTime(b.date);
      if (ta == null && tb == null) return 0;
      if (ta == null) return 1;
      if (tb == null) return -1;
      return ta - tb;
    });
  }, [season]);

  // المرحلة «الحاليّة»: آخر مرحلة بلغ تاريخُها ≤ اليوم (تُشتقّ فقط حين تتوفّر تواريخ).
  // -1 ⇒ لا تمييز زمنيّ (مراحل بلا تواريخ، أو كلّها مستقبليّة).
  const currentIdx = useMemo(() => {
    const now = Date.now();
    let idx = -1;
    stages.forEach((s, i) => {
      const t = stageTime(s.date);
      if (t != null && t <= now) idx = i;
    });
    return idx;
  }, [stages]);

  const hasDates = useMemo(() => stages.some((s) => stageTime(s.date) != null), [stages]);

  // GDD المُخزَّن من المحاكاة (تقديريّ) — null إن لم يُشغَّل /simulate.
  const gdd = season?.sim_gdd_total ?? null;

  const fieldName = fields.find((f) => f.id === fieldId)?.name ?? '—';
  const cropAr = season && season.crops.length ? season.crops.join('، ') : '—';

  // وسم الترويسة: عدد المراحل الحقيقيّ أو حالة فارغة.
  const headerPill = (
    <Pill
      tone={stages.length ? 'info' : 'ok'}
      icon={<Leaf style={{ width: 12, height: 12 }} />}
    >
      {stages.length ? `${stages.length} مرحلة` : 'بلا مراحل'}
    </Pill>
  );

  return (
    <FieldCabin
      eyebrow="كابينة الميدان"
      title="الأطوار الفينولوجيّة"
      subtitle="مراحل نموّ الموسم وتتبّع GDD — kong /seasons"
      headerRight={headerPill}
      note={
        <>
          الأطوار الفينولوجيّة من <code>/seasons</code> الحقيقيّة (مصفوفة المراحل كما سُجِّلت).
          المرحلة الحاليّة مشتقّة من تاريخ اليوم. GDD تقديريّ يُملأ بعد المحاكاة — «—» إن غاب.
          لا مرحلة مُلفَّقة.
        </>
      }
    >
      {/* اختيار الحقل (حقول حقيقيّة) */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={
            <Badge tone={fieldsLoading ? 'neutral' : fieldsError ? 'danger' : 'ok'}>
              {fieldsLoading ? 'تحميل…' : fieldsError ? 'خطأ' : 'مباشر'}
            </Badge>
          }
        >
          الحقل
        </SectionLabel>

        {fieldsLoading ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '12px 0', textAlign: 'center' }}>
            جارٍ تحميل الحقول…
          </div>
        ) : fieldsError ? (
          <div className="flex flex-col items-center" style={{ gap: 8, padding: '12px 0' }}>
            <span style={{ color: T.danger, fontSize: 13 }}>تعذّر تحميل الحقول من الخادم.</span>
            <button
              onClick={() => refetch()}
              style={{
                background: T.gold, color: '#fff', border: 'none', borderRadius: 10,
                padding: '6px 14px', fontSize: 12, fontWeight: 700, cursor: 'pointer',
              }}
            >
              إعادة المحاولة
            </button>
          </div>
        ) : fields.length === 0 ? (
          <div className="flex flex-col items-center" style={{ color: T.muted, fontSize: 13, padding: '16px 0', gap: 8 }}>
            <Sprout style={{ width: 26, height: 26, color: T.faint }} />
            لا توجد حقول بعد — أضِف حقلاً من «إدارة الحقول».
          </div>
        ) : (
          <select
            value={fieldId}
            onChange={(e) => setFieldId(e.target.value)}
            style={{
              width: '100%', padding: '10px 12px', borderRadius: 12,
              border: `1px solid ${T.line}`, background: T.card, color: T.ink,
              fontSize: 14, fontWeight: 600,
            }}
          >
            {fields.map((f) => (
              <option key={f.id} value={f.id}>{f.name}</option>
            ))}
          </select>
        )}
      </Card>

      {/* جسم الفينولوجيا — يظهر فقط بعد اختيار حقل */}
      {fieldId && (
        <>
          {/* بطاقة الموسم + GDD */}
          <Card pad={14} style={{ marginBottom: 10 }}>
            <SectionLabel
              action={
                <Badge tone={seasonsQ.isLoading ? 'neutral' : seasonsQ.isError ? 'danger' : 'ok'}>
                  {seasonsQ.isLoading ? 'تحميل…' : seasonsQ.isError ? 'خطأ' : 'مباشر'}
                </Badge>
              }
            >
              الموسم الحاليّ
            </SectionLabel>

            {seasonsQ.isLoading ? (
              <div style={{ color: T.muted, fontSize: 13, padding: '16px 0', textAlign: 'center' }}>
                جارٍ تحميل المواسم…
              </div>
            ) : seasonsQ.isError ? (
              <div style={{ color: T.danger, fontSize: 13, padding: '16px 0', textAlign: 'center' }}>
                تعذّر تحميل مواسم الحقل.
              </div>
            ) : !season ? (
              <div className="flex flex-col items-center" style={{ color: T.muted, fontSize: 13, padding: '20px 0', gap: 8 }}>
                <Sprout style={{ width: 26, height: 26, color: T.faint }} />
                لا موسم مُسجَّل لهذا الحقل بعد.
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
                  <div className="flex items-center gap-2" style={{ fontSize: 14, fontWeight: 800, color: T.ink }}>
                    <Sprout style={{ width: 16, height: 16, color: T.green }} /> {cropAr}
                  </div>
                  <Badge tone={season.status === 'active' ? 'ok' : 'neutral'}>
                    {seasonStatusAr(season.status)}
                  </Badge>
                </div>

                <div className="flex items-center gap-1" style={{ fontSize: 12, color: T.muted, marginBottom: 10 }}>
                  <MapPin style={{ width: 12, height: 12 }} /> {fieldName}
                  {season.cultivar ? <span> · {season.cultivar}</span> : null}
                </div>

                <div className="flex items-center gap-2" style={{ flexWrap: 'wrap', marginBottom: 12 }}>
                  <Pill tone="neutral" icon={<Calendar style={{ width: 11, height: 11 }} />}>
                    زراعة: {fmtDateAr(season.sowing_date)}
                  </Pill>
                  <Pill tone="neutral" icon={<Flag style={{ width: 11, height: 11 }} />}>
                    نهاية: {fmtDateAr(season.season_end)}
                  </Pill>
                </div>

                {/* تتبّع GDD المُخزَّن — تقديريّ، يُعرَض «—» إن لم يُشغَّل /simulate */}
                <div
                  style={{
                    background: T.card2, borderRadius: 12, padding: '10px 12px',
                    border: `1px solid ${T.line}`,
                  }}
                >
                  <div className="flex items-center justify-between" style={{ marginBottom: 6 }}>
                    <div className="flex items-center gap-1.5" style={{ fontSize: 12, fontWeight: 700, color: T.brownSoft }}>
                      <Thermometer style={{ width: 13, height: 13, color: T.warn }} /> GDD المتراكم (تقديريّ)
                    </div>
                    <span style={{ fontSize: 14, fontWeight: 800, color: gdd != null ? T.ink : T.faint }}>
                      {gdd != null ? `${Math.round(gdd)} °م·يوم` : '—'}
                    </span>
                  </div>
                  {gdd != null ? (
                    <ProgressBar value={1} color={T.warn} height={6} />
                  ) : (
                    <div style={{ fontSize: 11, color: T.faint }}>
                      شغّل محاكاة الموسم لحساب GDD التراكميّ.
                    </div>
                  )}
                </div>
              </>
            )}
          </Card>

          {/* التايم‑لاين — مصفوفة المراحل الحقيقيّة بتمييز المرحلة الحاليّة */}
          {season && (
            <Card pad={14}>
              <SectionLabel
                action={
                  <Badge tone={stages.length ? 'info' : 'neutral'}>
                    {stages.length ? `${stages.length} مرحلة` : 'فارغ'}
                  </Badge>
                }
              >
                مراحل النموّ
              </SectionLabel>

              {stages.length === 0 ? (
                <div className="flex flex-col items-center" style={{ color: T.muted, fontSize: 13, padding: '20px 0', gap: 8 }}>
                  <Leaf style={{ width: 26, height: 26, color: T.faint }} />
                  لا مراحل نموّ مُسجَّلة لهذا الموسم.
                </div>
              ) : (
                <div style={{ marginTop: 6 }}>
                  {!hasDates && (
                    <div style={{ fontSize: 11, color: T.faint, marginBottom: 10 }}>
                      المراحل بلا تواريخ — تُعرَض بترتيب الإدخال دون تمييز للمرحلة الحاليّة.
                    </div>
                  )}
                  {stages.map((s, i) => {
                    const isCurrent = i === currentIdx;
                    const isPast = currentIdx >= 0 && i < currentIdx;
                    const dotColor = isCurrent ? T.green : isPast ? T.gold : T.faint;
                    return (
                      <div
                        key={`${s.name}-${i}`}
                        className="flex gap-3"
                        style={{ paddingBottom: i === stages.length - 1 ? 0 : 14, position: 'relative' }}
                      >
                        {/* عمود الخطّ الزمنيّ (نقطة + موصِّل) */}
                        <div className="flex flex-col items-center" style={{ flexShrink: 0 }}>
                          {isCurrent ? (
                            <CircleDot style={{ width: 18, height: 18, color: dotColor }} />
                          ) : (
                            <div
                              style={{
                                width: 14, height: 14, borderRadius: '50%',
                                background: isPast ? dotColor : T.card2,
                                border: `2px solid ${dotColor}`, marginTop: 2,
                              }}
                            />
                          )}
                          {i < stages.length - 1 && (
                            <div style={{ width: 2, flex: 1, background: T.line, marginTop: 2, minHeight: 18 }} />
                          )}
                        </div>

                        {/* محتوى المرحلة */}
                        <div style={{ flex: 1, paddingBottom: 2 }}>
                          <div className="flex items-center justify-between" style={{ gap: 8 }}>
                            <span
                              style={{
                                fontSize: 14,
                                fontWeight: isCurrent ? 800 : 600,
                                color: isCurrent ? T.green : T.ink,
                              }}
                            >
                              {s.name || `مرحلة ${i + 1}`}
                            </span>
                            {isCurrent && <Badge tone="ok">الحاليّة</Badge>}
                          </div>
                          <div style={{ fontSize: 12, color: T.muted, marginTop: 2 }}>
                            {fmtDateAr(s.date)}
                          </div>
                          {s.notes ? (
                            <div style={{ fontSize: 12, color: T.brownSoft, marginTop: 4, lineHeight: 1.6 }}>
                              {s.notes}
                            </div>
                          ) : null}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </Card>
          )}
        </>
      )}
    </FieldCabin>
  );
}
