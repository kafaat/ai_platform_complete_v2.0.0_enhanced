// ═══════════════════════════════════════════════════════════════
// SAHOOL — الاستكشاف الميدانيّ (Scouting) · تصنيف المشاهدات لكلّ حقل
// ───────────────────────────────────────────────────────────────
// مستوحاة من «Scouting Pins» (FieldView)، مُكيَّفة للسياق اليمنيّ. تُسطِّح
// المصدر الوحيد القابل للقراءة (GET) في الخادم:
//   GET /api/v1/scouting/taxonomy        → التصنيف الكامل + دليل نقص العناصر
//   GET /api/v1/scouting/taxonomy?crop=X → مشاكل محصول واحد فقط
// (api/scouting_pins.py عبر main.py:7121-7133). نقطتا pins/timeline في الخادم
// POST فقط (إنشاء/تجميع من حمولة الطلب) ولا تُرجِعان قائمة مُخزَّنة تُقرأ بـGET،
// فلا تُعرَضان هنا — صدق: لا نخترع endpoint قراءة غير موجود ولا نُلفّق مشاهدات.
//
// التدفّق: اختَر حقلاً ⇒ نقرأ محصوله (من useSelectedField) ⇒ نجلب مشاكله الشائعة
// من التصنيف الحيّ (rule-based منسَّق، لا تشخيص آلي). إن لا محصول/لا تصنيف
// للمحصول ⇒ «لا ملاحظات استكشاف». كلّ الحالات (تحميل/خطأ/فراغ) صريحة. قراءة فقط.
// ═══════════════════════════════════════════════════════════════
import { useMemo } from 'react';
import { Bug, Leaf, AlertTriangle, ListChecks, FlaskConical } from 'lucide-react';
import { useSelectedField } from '../hooks/useSelectedField';
import {
  useCropScoutingIssues,
  useScoutingTaxonomy,
  type ScoutingIssue,
} from '../hooks/useScouting';
import {
  T, Card, Pill, Badge, SectionLabel, FieldCabin,
} from '../components/ds';

const MISSING = '—';

// تسمية عربيّة لفئة المشكلة (من enum IssueCategory في scouting_pins.py).
const CATEGORY_AR: Record<string, string> = {
  disease: 'مرض',
  pest: 'آفة',
  weed: 'أعشاب ضارّة',
  nutrient: 'نقص عنصر',
  water_stress: 'إجهاد مائي',
  abiotic: 'غير حيوي',
  other: 'أخرى',
};

// نغمة لونيّة للفئة (مرض/آفة أشدّ تنبيهاً من النقص).
function categoryTone(category: string): 'danger' | 'warn' | 'neutral' {
  if (category === 'disease' || category === 'pest') return 'danger';
  if (category === 'nutrient' || category === 'water_stress' || category === 'abiotic') return 'warn';
  return 'neutral';
}

// أيقونة الفئة (ReactNode — DS يتطلّب ReactNode لا مكوّناً).
function categoryIcon(category: string) {
  const st = { width: 12, height: 12 };
  if (category === 'disease' || category === 'pest') return <Bug style={st} />;
  if (category === 'nutrient') return <FlaskConical style={st} />;
  return <Leaf style={st} />;
}

export default function ScoutingView() {
  const { options, isLoading: fieldsLoading, isError: fieldsError, fieldId, field: selected, setFieldId } = useSelectedField();

  // محصول الحقل المُختار (مصدر التصنيف). '—' يعني لا محصول مُسجَّل ⇒ لا استعلام.
  const crop = selected?.crop && selected.crop !== MISSING ? selected.crop : undefined;

  // التصنيف الخاصّ بالمحصول (مُفعَّل فقط عند وجود crop).
  const cropQ = useCropScoutingIssues(crop);
  // التصنيف الكامل (لدليل نقص العناصر — معلومة بصريّة عامّة مفيدة دائماً).
  const taxQ = useScoutingTaxonomy();

  const issues = useMemo<ScoutingIssue[]>(
    () => (Array.isArray(cropQ.data?.issues) ? cropQ.data.issues : []),
    [cropQ.data],
  );

  const nutrientGuide = useMemo(
    () => (Array.isArray(taxQ.data?.nutrient_guide) ? taxQ.data.nutrient_guide : []),
    [taxQ.data],
  );

  return (
    <FieldCabin
      eyebrow="الاستكشاف الميدانيّ"
      title="ملاحظات الاستكشاف"
      subtitle="المشاكل الشائعة لمحصول الحقل — تصنيف يمنيّ منسَّق (rule-based)"
      headerRight={
        <Pill tone="warn" icon={<ListChecks style={{ width: 12, height: 12 }} />}>
          {issues.length} ملاحظة
        </Pill>
      }
      note={
        <>
          المشاكل الشائعة من التصنيف الحيّ <code>/api/v1/scouting/taxonomy</code>
          {' '}(منسَّق لكلّ محصول يمنيّ، لا تشخيص آلي). نقاط المشاهدات (pins) تُنشَأ
          وتُحفَظ على الموبايل (POST) — لا قائمة مُخزَّنة تُقرَأ هنا. الحالات صادقة.
        </>
      }
    >
      {/* ── منتقي الحقل ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={
            <Badge tone={fieldsLoading ? 'neutral' : fieldsError ? 'danger' : options.length ? 'ok' : 'warn'}>
              {fieldsLoading ? 'تحميل…' : fieldsError ? 'خطأ' : `${options.length} حقل`}
            </Badge>
          }
        >
          الحقل
        </SectionLabel>

        {fieldsLoading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل الحقول…</div>
        ) : fieldsError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل الحقول.</div>
        ) : options.length === 0 ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا حقول مُسجَّلة.</div>
        ) : (
          <>
            <select
              value={fieldId}
              onChange={(e) => setFieldId(e.target.value)}
              dir="rtl"
              style={{
                width: '100%', padding: '10px 12px', borderRadius: 10,
                border: `1px solid ${T.line}`, background: T.card, color: T.ink,
                fontSize: 13, fontWeight: 600,
              }}
            >
              {options.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}{f.crop && f.crop !== MISSING ? ` · ${f.crop}` : ''}
                </option>
              ))}
            </select>
            {selected && (
              <div className="flex items-center gap-2" style={{ marginTop: 8, flexWrap: 'wrap' }}>
                <Pill tone="neutral" icon={<Leaf style={{ width: 11, height: 11 }} />}>
                  المحصول: {crop ?? MISSING}
                </Pill>
              </div>
            )}
          </>
        )}
      </Card>

      {/* ── المشاكل الشائعة لمحصول الحقل ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={
            <Badge tone={cropQ.isLoading ? 'neutral' : cropQ.isError ? 'danger' : issues.length ? 'warn' : 'neutral'}>
              {cropQ.isLoading ? 'تحميل…' : cropQ.isError ? 'خطأ' : `${issues.length}`}
            </Badge>
          }
        >
          المشاكل الشائعة
        </SectionLabel>

        {!crop ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>
            لا ملاحظات استكشاف — لا محصول مُسجَّل لهذا الحقل.
          </div>
        ) : cropQ.isLoading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل المشاكل الشائعة…</div>
        ) : cropQ.isError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل تصنيف المحصول.</div>
        ) : issues.length === 0 ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>
            لا ملاحظات استكشاف — لا مشاكل منسَّقة للمحصول «{crop}».
          </div>
        ) : (
          <div>
            {issues.map((it, i) => (
              <div
                key={it.code || i}
                style={{
                  padding: '10px 8px',
                  borderBottom: i < issues.length - 1 ? `1px solid ${T.line}` : 'none',
                }}
              >
                <div className="flex items-center gap-2" style={{ marginBottom: 4 }}>
                  <AlertTriangle style={{ width: 14, height: 14, color: T.warn, flexShrink: 0 }} />
                  <span style={{ color: T.ink, fontSize: 13, fontWeight: 700, flex: 1 }}>
                    {it.name_ar || MISSING}
                  </span>
                  <Pill tone={categoryTone(it.category)} icon={categoryIcon(it.category)}>
                    {CATEGORY_AR[it.category] ?? it.category ?? MISSING}
                  </Pill>
                </div>
                <div style={{ color: T.faint, fontSize: 11, marginInlineStart: 22 }}>
                  <code>{it.code || MISSING}</code>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* ── دليل نقص العناصر (علامات بصريّة rule-based — معلومة عامّة) ── */}
      <Card pad={14}>
        <SectionLabel
          action={
            <Badge tone={taxQ.isLoading ? 'neutral' : taxQ.isError ? 'danger' : nutrientGuide.length ? 'ok' : 'neutral'}>
              {taxQ.isLoading ? 'تحميل…' : taxQ.isError ? 'خطأ' : `${nutrientGuide.length}`}
            </Badge>
          }
        >
          دليل نقص العناصر
        </SectionLabel>

        {taxQ.isLoading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل الدليل…</div>
        ) : taxQ.isError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل دليل العناصر.</div>
        ) : nutrientGuide.length === 0 ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا دليل عناصر متاح.</div>
        ) : (
          <div>
            {nutrientGuide.map((n, i) => (
              <div
                key={n.code || i}
                style={{
                  padding: '8px 8px',
                  borderBottom: i < nutrientGuide.length - 1 ? `1px solid ${T.line}` : 'none',
                }}
              >
                <div className="flex items-center gap-2" style={{ marginBottom: 2 }}>
                  <FlaskConical style={{ width: 13, height: 13, color: T.warn, flexShrink: 0 }} />
                  <span style={{ color: T.ink, fontSize: 12, fontWeight: 700, flex: 1 }}>
                    {n.name_ar || MISSING}
                  </span>
                  <Badge tone="neutral">{n.code || MISSING}</Badge>
                </div>
                <div style={{ color: T.muted, fontSize: 11, lineHeight: 1.6, marginInlineStart: 21 }}>
                  {n.sign_ar || MISSING}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </FieldCabin>
  );
}
