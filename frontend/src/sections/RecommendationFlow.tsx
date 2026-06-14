// ═══════════════════════════════════════════════════════════════
// SAHOOL — توصية ← تنفيذ (Recommendation → Execution) · شاشة دمج رابعة
// ───────────────────────────────────────────────────────────────
// تصهر «التوصية الزراعيّة» (FieldView) مع «معالج خطّة العمل» (Operations Center):
// معالج أربع خطوات (Stepper) يحوّل توصية المحرّك الحقيقيّة إلى عمليّة زراعيّة
// مخطّطة مُسجَّلة فعليّاً عبر API سهول. تجسيد UI_DESIGN_SPEC_UNIFIED.md §2 (الوحدة
// الثالثة) و§6 (الخطوة 4). يستهلك Stepper في صورته الكاملة (معالج مركّب).
//
// صدق البيانات: التوصيات من useFieldRecommendations الحقيقيّة (محرّك سهول)؛
// التسجيل طفرة حقيقيّة (useCreateActivity → POST /fields/{id}/activities). لا
// «إرسال للكابينة» (ISOBUS) — فجوة ⛔ موثّقة (§5): التنفيذ هنا = تسجيل عمليّة
// مخطّطة لا دفعٌ لشاشة الآلة. الحالات (تحميل/فراغ/خطأ/طفرة) صريحة.
// ═══════════════════════════════════════════════════════════════
import { useMemo, useState } from 'react';
import {
  Sprout, Droplets, FlaskConical, Bug, TrendingUp, Calendar, CheckCircle2, AlertTriangle, RotateCcw,
} from 'lucide-react';
import { useFields, useFieldRecommendations, useCreateActivity } from '../hooks/useApi';
import type { ActivityType, FieldRecommendation } from '../services/api';
import {
  T, Card, Pill, Badge, SectionLabel, Stepper, FieldCabin,
} from '../components/ds';

const STEPS = ['الحقل', 'التوصية', 'العمليّة', 'التسجيل'];

// تصنيف التوصية → نوع العمليّة المقترَح (يُمكن للمستخدم تغييره).
const CATEGORY_ACTIVITY: Record<string, ActivityType> = {
  irrigation: 'irrigation', fertilizer: 'fertilization', disease: 'spraying', yield: 'scouting',
};
const CATEGORY_AR: Record<string, string> = {
  irrigation: 'ريّ', fertilizer: 'تسميد', disease: 'مرض/آفة', yield: 'إنتاجيّة',
};
const ACTIVITY_AR: Record<ActivityType, string> = {
  planting: 'زراعة', fertilization: 'تسميد', irrigation: 'ريّ', spraying: 'رشّ',
  pruning: 'تقليم', harvest: 'حصاد', scouting: 'استكشاف',
};
const ACTIVITY_TYPES = Object.keys(ACTIVITY_AR) as ActivityType[];

const PRIORITY_AR: Record<string, string> = { high: 'عالية', medium: 'متوسّطة', low: 'منخفضة' };
const priorityTone = (p?: string) =>
  p === 'high' ? 'danger' : p === 'medium' ? 'warn' : 'info';

function categoryIcon(cat?: string) {
  const s = (cat ?? '').toLowerCase();
  if (s === 'irrigation') return <Droplets style={{ width: 16, height: 16, color: T.info }} />;
  if (s === 'fertilizer') return <FlaskConical style={{ width: 16, height: 16, color: T.green }} />;
  if (s === 'disease') return <Bug style={{ width: 16, height: 16, color: T.danger }} />;
  if (s === 'yield') return <TrendingUp style={{ width: 16, height: 16, color: T.gold }} />;
  return <Sprout style={{ width: 16, height: 16, color: T.muted }} />;
}

// زرّ إجراء أساسيّ (CTA) — نمط متّسق مع شاشات الكابينة (لا Button atom بعد).
function CTA({
  children, onClick, disabled, tone = 'green',
}: { children: React.ReactNode; onClick?: () => void; disabled?: boolean; tone?: 'green' | 'gold' }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        width: '100%', padding: '11px 14px', borderRadius: 12, border: 'none',
        background: disabled ? T.line : tone === 'gold' ? T.gold : T.green,
        color: disabled ? T.muted : '#fff', fontSize: 14, fontWeight: 800,
        cursor: disabled ? 'not-allowed' : 'pointer', marginTop: 10,
      }}
    >
      {children}
    </button>
  );
}

interface FlowField { id: string; name: string }

export default function RecommendationFlow() {
  const [step, setStep] = useState(1);
  const [fieldId, setFieldId] = useState('');
  const [recIdx, setRecIdx] = useState<number | null>(null);
  const [activityType, setActivityType] = useState<ActivityType>('scouting');
  const [scheduledFor, setScheduledFor] = useState('');

  const fieldsQ = useFields();
  const fields: FlowField[] = useMemo(() => {
    const raw = Array.isArray(fieldsQ.data?.fields) ? fieldsQ.data.fields : [];
    return raw.map((f: any) => ({ id: String(f.field_id ?? f.id), name: f.name ?? f.field_id ?? 'حقل' }));
  }, [fieldsQ.data]);

  const recsQ = useFieldRecommendations(fieldId || undefined);
  const recs: FieldRecommendation[] = Array.isArray(recsQ.data?.recommendations) ? recsQ.data.recommendations : [];
  const chosen = recIdx != null ? recs[recIdx] : undefined;

  const createQ = useCreateActivity(fieldId);

  const fieldName = fields.find((f) => f.id === fieldId)?.name ?? fieldId;

  function pickField(id: string) {
    setFieldId(id);
    setRecIdx(null);
    createQ.reset();
    setStep(2);
  }
  function pickRec(i: number) {
    setRecIdx(i);
    const cat = (recs[i]?.category ?? '').toLowerCase();
    setActivityType(CATEGORY_ACTIVITY[cat] ?? 'scouting');
    setStep(3);
  }
  function submit() {
    if (!chosen) return;
    createQ.mutate({
      activity_type: activityType,
      title_ar: chosen.title_ar,
      ...(scheduledFor ? { scheduled_for: scheduledFor } : {}),
      details: { from_recommendation: true, source: chosen.source, category: chosen.category },
    });
  }
  function reset() {
    createQ.reset();
    setStep(1); setFieldId(''); setRecIdx(null); setActivityType('scouting'); setScheduledFor('');
  }

  return (
    <FieldCabin
      eyebrow="توصية ← تنفيذ"
      title="خطّة العمل"
      subtitle="حوّل توصية المحرّك إلى عمليّة مخطّطة — معالج أربع خطوات"
      headerRight={<Badge tone="info">الخطوة {step}/4</Badge>}
      note={
        <>
          توصية←تنفيذ الموحّد — توصيات <code>/fields/&#123;id&#125;/recommendations</code> الحقيقيّة،
          والتسجيل عبر <code>POST /activities</code>. «الإرسال للكابينة» (ISOBUS) فجوة موثّقة ⛔ —
          التنفيذ هنا تسجيل عمليّة مخطّطة لا دفعٌ لشاشة الآلة.
        </>
      }
    >
      <Card pad={14} style={{ marginBottom: 10 }}>
        <Stepper steps={STEPS} active={step} onStep={(n) => { if (n < step) setStep(n); }} />
      </Card>

      {/* ── الخطوة 1: اختيار الحقل ── */}
      {step === 1 && (
        <Card pad={14}>
          <SectionLabel>اختر الحقل</SectionLabel>
          {fieldsQ.isLoading ? (
            <div style={{ color: T.muted, fontSize: 13, padding: '8px 0' }}>جارٍ تحميل الحقول…</div>
          ) : fieldsQ.isError ? (
            <div style={{ color: T.danger, fontSize: 13, padding: '8px 0' }}>تعذّر تحميل الحقول.</div>
          ) : fields.length === 0 ? (
            <div style={{ color: T.muted, fontSize: 13, padding: '8px 0' }}>لا حقول مُسجّلة.</div>
          ) : (
            fields.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => pickField(f.id)}
                style={{
                  width: '100%', textAlign: 'start', padding: '11px 12px', marginBottom: 6,
                  borderRadius: 10, border: `1px solid ${T.line}`, background: T.card,
                  color: T.ink, fontSize: 14, fontWeight: 600, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 8,
                }}
              >
                <Sprout style={{ width: 16, height: 16, color: T.green }} /> {f.name}
              </button>
            ))
          )}
        </Card>
      )}

      {/* ── الخطوة 2: اختيار التوصية ── */}
      {step === 2 && (
        <Card pad={14}>
          <SectionLabel action={<Badge tone="neutral">{fieldName}</Badge>}>توصيات المحرّك</SectionLabel>
          {recsQ.isLoading ? (
            <div style={{ color: T.muted, fontSize: 13, padding: '8px 0' }}>جارٍ تحميل التوصيات…</div>
          ) : recsQ.isError ? (
            <div style={{ color: T.danger, fontSize: 13, padding: '8px 0' }}>تعذّر تحميل التوصيات لهذا الحقل.</div>
          ) : recs.length === 0 ? (
            <div style={{ color: T.muted, fontSize: 13, padding: '8px 0' }}>لا توصيات حاليّة لهذا الحقل.</div>
          ) : (
            recs.map((r, i) => (
              <button
                key={i}
                type="button"
                onClick={() => pickRec(i)}
                style={{
                  width: '100%', textAlign: 'start', padding: '11px 12px', marginBottom: 8,
                  borderRadius: 10, border: `1px solid ${T.line}`, background: T.card, cursor: 'pointer',
                }}
              >
                <div className="flex items-center justify-between" style={{ marginBottom: 4 }}>
                  <span className="inline-flex items-center gap-2" style={{ fontWeight: 700, fontSize: 14, color: T.ink }}>
                    {categoryIcon(r.category)} {r.title_ar}
                  </span>
                  <Badge tone={priorityTone(r.priority)}>{PRIORITY_AR[(r.priority ?? '').toLowerCase()] ?? r.priority}</Badge>
                </div>
                <div style={{ fontSize: 12, color: T.muted, lineHeight: 1.6 }}>{r.detail_ar}</div>
                <div style={{ fontSize: 10, color: T.faint, marginTop: 4 }}>
                  {CATEGORY_AR[(r.category ?? '').toLowerCase()] ?? r.category} · المصدر: {r.source}
                </div>
              </button>
            ))
          )}
        </Card>
      )}

      {/* ── الخطوة 3: تحديد العمليّة ── */}
      {step === 3 && chosen && (
        <Card pad={14}>
          <SectionLabel>حدّد العمليّة</SectionLabel>
          <div style={{ background: T.card2, borderRadius: 10, padding: 10, marginBottom: 12 }}>
            <div className="inline-flex items-center gap-2" style={{ fontWeight: 700, fontSize: 13, color: T.ink }}>
              {categoryIcon(chosen.category)} {chosen.title_ar}
            </div>
          </div>

          <div style={{ fontSize: 12, color: T.muted, marginBottom: 6 }}>نوع العمليّة</div>
          <div className="flex" style={{ flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
            {ACTIVITY_TYPES.map((a) => {
              const on = activityType === a;
              return (
                <button
                  key={a}
                  type="button"
                  onClick={() => setActivityType(a)}
                  style={{
                    padding: '6px 12px', borderRadius: 999, border: 'none', cursor: 'pointer',
                    fontSize: 12, fontWeight: on ? 700 : 500,
                    background: on ? T.green : T.card2, color: on ? '#fff' : T.ink,
                  }}
                >
                  {ACTIVITY_AR[a]}
                </button>
              );
            })}
          </div>

          <div style={{ fontSize: 12, color: T.muted, marginBottom: 6 }}>
            <span className="inline-flex items-center gap-1"><Calendar style={{ width: 12, height: 12 }} /> موعد مقترَح (اختياريّ)</span>
          </div>
          <input
            type="date"
            value={scheduledFor}
            onChange={(e) => setScheduledFor(e.target.value)}
            style={{
              width: '100%', padding: '9px 10px', borderRadius: 10,
              border: `1px solid ${T.line}`, background: T.card, color: T.ink, fontSize: 14,
            }}
          />

          <CTA onClick={() => setStep(4)}>المتابعة للمراجعة ←</CTA>
        </Card>
      )}

      {/* ── الخطوة 4: المراجعة والتسجيل ── */}
      {step === 4 && chosen && (
        <Card pad={14}>
          <SectionLabel>مراجعة وتسجيل</SectionLabel>

          {createQ.isSuccess ? (
            <>
              <div className="flex flex-col items-center" style={{ gap: 8, padding: '16px 0', color: T.ok }}>
                <CheckCircle2 style={{ width: 32, height: 32 }} />
                <div style={{ fontWeight: 800, fontSize: 15 }}>سُجِّلت العمليّة المخطّطة</div>
                <div style={{ fontSize: 12, color: T.muted, textAlign: 'center' }}>
                  {ACTIVITY_AR[activityType]} · {fieldName}{scheduledFor ? ` · ${scheduledFor}` : ''}
                </div>
              </div>
              <CTA tone="gold" onClick={reset}>
                <span className="inline-flex items-center gap-2"><RotateCcw style={{ width: 14, height: 14 }} /> خطّة جديدة</span>
              </CTA>
            </>
          ) : (
            <>
              <div style={{ background: T.card2, borderRadius: 10, padding: 12, fontSize: 13, lineHeight: 2 }}>
                <div className="flex items-center justify-between">
                  <span style={{ color: T.muted }}>الحقل</span><b style={{ color: T.ink }}>{fieldName}</b>
                </div>
                <div className="flex items-center justify-between">
                  <span style={{ color: T.muted }}>التوصية</span><b style={{ color: T.ink }}>{chosen.title_ar}</b>
                </div>
                <div className="flex items-center justify-between">
                  <span style={{ color: T.muted }}>العمليّة</span>
                  <Pill tone="ok">{ACTIVITY_AR[activityType]}</Pill>
                </div>
                <div className="flex items-center justify-between">
                  <span style={{ color: T.muted }}>الموعد</span><b style={{ color: T.ink }}>{scheduledFor || '—'}</b>
                </div>
              </div>

              {createQ.isError && (
                <div className="flex items-center gap-2" style={{ color: T.danger, fontSize: 12, marginTop: 10 }}>
                  <AlertTriangle style={{ width: 14, height: 14 }} /> تعذّر التسجيل: {createQ.error?.message || 'خطأ غير معروف'}
                </div>
              )}

              <CTA onClick={submit} disabled={createQ.isPending}>
                {createQ.isPending ? 'جارٍ التسجيل…' : 'تسجيل العمليّة المخطّطة'}
              </CTA>
              <div style={{ fontSize: 10, color: T.faint, textAlign: 'center', marginTop: 6 }}>
                يُسجَّل كعمليّة مخطّطة (planned) — لا إرسال لشاشة الآلة (فجوة موثّقة).
              </div>
            </>
          )}
        </Card>
      )}
    </FieldCabin>
  );
}
