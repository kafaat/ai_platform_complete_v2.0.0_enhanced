// ═══════════════════════════════════════════════════════════════
// SAHOOL — حقول المشكلات (Problem Fields) · ترتيب الحقول حسب شدّة المشكلة
// ───────────────────────────────────────────────────────────────
// مستوحاة من «فرز الحقول لإظهار أشدّ الحقول مشكلةً» (Agtrinsic). شاشة جديدة
// ترتّب الحقول حسب درجة مشكلة مركّبة شفّافة، تدمج إشارتين حقيقيّتين متاحتين
// جملةً (bulk) فقط:
//   (أ) إشارة NDVI المنخفض: من useAllFieldsNdvi (/v1/all_fields). كلّما انخفض
//       NDVI زادت المشكلة.
//   (ب) التنبيهات المفتوحة لكلّ حقل: من useAlerts، مُجمّعة حسب field_id ومُوزّنة
//       بالشدّة (حرِج > تحذير > معلومة).
//
// صدق البيانات: إشارات حقيقيّة فقط. حقل بلا NDVI صالح وبلا تنبيهات ليس مشكلة —
// يُستبعَد (لا تلفيق درجة). لا نُلفّق «درجة مرض»: مخاطر الأمراض هوك لكلّ حقل
// (useDiseaseRisk) لا يمكن تجميعه عبر كلّ الحقول دون N هوكات — فلا نُكرّره في
// حلقة. نجلبه فقط للحقل المُحدَّد (الأشدّ افتراضيّاً أو المُختار) كتفصيل، والترتيب
// يبقى على NDVI + التنبيهات حصراً. الحالات (تحميل/خطأ/فراغ) صريحة. قراءة فقط.
//
// ── صيغة الدرجة (شفّافة، تنازليّاً: الأشدّ مشكلةً أوّلاً) ──────────────
//   ndviGap  = ndvi صالح في [0,1] ? (1 - clamp(ndvi,0,1)) : 0   // [0,1]
//   alertW   = Σ على التنبيهات المفتوحة للحقل من وزن الشدّة:
//                حرِج (critical/high) = 1.0 · تحذير (warning/medium) = 0.6 · معلومة = 0.3
//   score    = NDVI_WEIGHT·ndviGap + alertW            // NDVI_WEIGHT = 1
// الحقل «مشكلة» إن score > 0 (أي عنده NDVI منخفض حقيقيّ أو تنبيه مفتوح واحد
// على الأقلّ). ndviGap محدود في [0,1]؛ alertW غير محدود (يعكس عدد/شدّة التنبيهات).
// ═══════════════════════════════════════════════════════════════
import { useMemo, useState } from 'react';
import { AlertTriangle, Layers, Flame, TrendingDown, Bell, Activity } from 'lucide-react';
import { useAllFieldsNdvi, useAlerts, useDiseaseRisk } from '../hooks/useApi';
import type { AlertRecord } from '../services/api';
import {
  T, Card, Pill, Badge, SectionLabel, StatGrid, ProgressBar, FieldCabin, ndviColor, severityTone,
} from '../components/ds';

// ── أوزان شدّة التنبيه (حرِج > تحذير > معلومة) ──────────────────
function severityWeight(severity?: string | null): number {
  const s = (severity ?? '').toLowerCase();
  if (s === 'critical' || s === 'high') return 1.0;
  if (s === 'warning' || s === 'medium') return 0.6;
  if (s === 'info' || s === 'low') return 0.3;
  return 0.3; // شدّة مجهولة → أدنى وزن (لا نُضخّم بلا دليل)
}

// وزن إشارة NDVI المنخفض في المجموع المركّب (ndviGap في [0,1]).
const NDVI_WEIGHT = 1;

// تنبيه «مفتوح» = لم يُحَلّ (active/acknowledged). المُحلّ (resolved) لا يُحتسَب.
function isOpenAlert(a: AlertRecord): boolean {
  return (a.status ?? '').toLowerCase() !== 'resolved';
}

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

// شكل سجلّ الحقل من /v1/all_fields (vegetation-service): { field_id, field_name,
// name, crop, ndvi, … }. ndvi قد يكون عدداً أو null — نُطبّع ونُصفّي.
interface RawField {
  field_id?: string;
  field_name?: string;
  name?: string;
  crop?: string;
  ndvi?: number | null;
}

interface ProblemField {
  id: string;
  name: string;
  crop?: string;
  ndvi: number | null;   // صالح [0,1] أو null (لا قراءة)
  ndviGap: number;       // [0,1] (0 إن لا NDVI صالح)
  alertCount: number;    // عدد التنبيهات المفتوحة للحقل
  alertWeight: number;   // مجموع أوزان الشدّة
  score: number;         // الدرجة المركّبة
}

const fmtNdvi = (v: number) => v.toFixed(2);

export default function ProblemFields() {
  const ndviQ = useAllFieldsNdvi();
  const alertsQ = useAlerts();

  // تجميع التنبيهات المفتوحة حسب field_id (null لا يُنسَب لحقل) → {count, weight}.
  const alertsByField = useMemo(() => {
    const list: AlertRecord[] = Array.isArray(alertsQ.data) ? alertsQ.data : [];
    const m = new Map<string, { count: number; weight: number }>();
    for (const a of list) {
      if (a.field_id == null || !isOpenAlert(a)) continue;
      const k = String(a.field_id);
      const prev = m.get(k) ?? { count: 0, weight: 0 };
      prev.count += 1;
      prev.weight += severityWeight(a.severity);
      m.set(k, prev);
    }
    return m;
  }, [alertsQ.data]);

  // بناء كلّ الحقول مع درجتها، ثمّ إبقاء «المشكلات» فقط (score > 0) مرتّبة تنازليّاً.
  const problems = useMemo<ProblemField[]>(() => {
    const data = ndviQ.data as { fields?: RawField[] } | undefined;
    const raw: RawField[] = Array.isArray(data?.fields) ? data.fields : [];
    return raw
      .map((f): ProblemField => {
        const id = String(f.field_id ?? '');
        const ndviRaw = f.ndvi;
        const ndviValid =
          typeof ndviRaw === 'number' && Number.isFinite(ndviRaw) && ndviRaw >= 0 && ndviRaw <= 1;
        const ndvi = ndviValid ? (ndviRaw as number) : null;
        const ndviGap = ndvi != null ? clamp01(1 - ndvi) : 0;
        const al = alertsByField.get(id) ?? { count: 0, weight: 0 };
        const score = NDVI_WEIGHT * ndviGap + al.weight;
        return {
          id,
          name: f.field_name || f.name || 'حقل',
          crop: f.crop,
          ndvi,
          ndviGap,
          alertCount: al.count,
          alertWeight: al.weight,
          score,
        };
      })
      // صدق المصدر: حقل بلا NDVI منخفض حقيقيّ وبلا تنبيه مفتوح ليس مشكلة.
      .filter((f) => f.score > 0)
      .sort((a, b) => b.score - a.score);
  }, [ndviQ.data, alertsByField]);

  const summary = useMemo(() => {
    if (problems.length === 0) return null;
    return { count: problems.length, worst: problems[0] };
  }, [problems]);

  // الحقل المُحدَّد لتفصيل مخاطر الأمراض (هوك مفرد — لا حلقة). الأشدّ افتراضيّاً.
  const [selectedId, setSelectedId] = useState<string>('');
  const selected = problems.find((f) => f.id === selectedId) ?? problems[0];
  const diseaseQ = useDiseaseRisk(selected?.id || undefined);

  const loading = ndviQ.isLoading || alertsQ.isLoading;
  const error = ndviQ.isError || alertsQ.isError;

  // نغمة شدّة الحقل من درجته (للوسم): الأشدّ danger، المتوسّط warn.
  const fieldTone = (score: number): 'danger' | 'warn' => (score >= 0.5 ? 'danger' : 'warn');

  return (
    <FieldCabin
      eyebrow="حقول المشكلات"
      title="أشدّ الحقول مشكلةً"
      subtitle="ترتيب مركّب: NDVI منخفض + التنبيهات المفتوحة — الأشدّ أوّلاً"
      headerRight={
        <Pill tone="danger" icon={<AlertTriangle style={{ width: 12, height: 12 }} />}>
          {problems.length} حقل
        </Pill>
      }
      note={
        <>
          الدرجة المركّبة الشفّافة = إشارة NDVI المنخفض <code>(1 - ndvi)</code> +
          التنبيهات المفتوحة المُوزّنة بالشدّة (من <code>/v1/all_fields</code> و<code>/api/v1/alerts</code>
          الحيّة). إشارات حقيقيّة فقط — لا تلفيق درجة مرض. الحالات صادقة.
        </>
      }
    >
      {/* ── الملخّص ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={
            <Badge tone={loading ? 'neutral' : error ? 'danger' : problems.length ? 'warn' : 'ok'}>
              {loading ? 'تحميل…' : error ? 'خطأ' : `${problems.length} حقل`}
            </Badge>
          }
        >
          الملخّص
        </SectionLabel>

        {loading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل حقول المشكلات…</div>
        ) : error ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل بيانات الحقول/التنبيهات.</div>
        ) : !summary ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا حقول بمشكلات.</div>
        ) : (
          <StatGrid
            cols={2}
            items={[
              {
                label: 'عدد حقول المشكلات',
                value: summary.count,
                color: T.warn,
                icon: <Layers style={{ width: 16, height: 16, color: T.warn }} />,
              },
              {
                label: 'الأشدّ',
                value: summary.worst.name,
                color: T.danger,
                icon: <Flame style={{ width: 16, height: 16, color: T.danger }} />,
              },
            ]}
          />
        )}
      </Card>

      {/* ── قائمة حقول المشكلات (تنازليّاً) ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={
            <span className="inline-flex items-center gap-1" style={{ color: T.muted, fontSize: 11 }}>
              <TrendingDown style={{ width: 12, height: 12 }} /> الأشدّ ← الأخفّ
            </span>
          }
        >
          الترتيب حسب شدّة المشكلة
        </SectionLabel>

        {loading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>—</div>
        ) : error ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل الترتيب.</div>
        ) : problems.length === 0 ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا حقول بمشكلات.</div>
        ) : (
          <div>
            {problems.map((f, i) => {
              const isSelected = selected?.id === f.id;
              const ndviCol = f.ndvi != null ? ndviColor(f.ndvi) : T.faint;
              return (
                <div
                  key={f.id || i}
                  onClick={() => setSelectedId(f.id)}
                  style={{
                    padding: '10px 8px',
                    borderBottom: `1px solid ${T.line}`,
                    borderRadius: 8,
                    cursor: 'pointer',
                    background: isSelected ? T.card2 : 'transparent',
                  }}
                >
                  <div className="flex items-center gap-2" style={{ marginBottom: 6 }}>
                    <span
                      style={{
                        width: 22, height: 22, borderRadius: 999, background: T.card2,
                        color: T.muted, fontSize: 11, fontWeight: 800, flexShrink: 0,
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                      }}
                    >
                      {i + 1}
                    </span>
                    <span style={{ color: T.ink, fontSize: 13, fontWeight: 700, flex: 1 }}>
                      {f.name}
                      {f.crop && (
                        <span style={{ color: T.faint, fontSize: 11, fontWeight: 500, marginInlineStart: 6 }}>{f.crop}</span>
                      )}
                    </span>
                    <Pill
                      tone={fieldTone(f.score)}
                      icon={<AlertTriangle style={{ width: 11, height: 11 }} />}
                    >
                      شدّة {f.score.toFixed(2)}
                    </Pill>
                  </div>

                  {/* ── شرائح العوامل المساهِمة (الإشارات الحقيقيّة فقط) ── */}
                  <div className="flex items-center gap-2" style={{ flexWrap: 'wrap', marginBottom: 6 }}>
                    {f.ndviGap > 0 && (
                      <Pill tone="warn" icon={<TrendingDown style={{ width: 11, height: 11 }} />}>
                        NDVI منخفض
                      </Pill>
                    )}
                    {f.alertCount > 0 && (
                      <Pill tone="danger" icon={<Bell style={{ width: 11, height: 11 }} />}>
                        {f.alertCount} تنبيهات
                      </Pill>
                    )}
                  </div>

                  {/* ── شريط NDVI (إن وُجدت قراءة صالحة) ── */}
                  {f.ndvi != null ? (
                    <div className="flex items-center gap-2">
                      <ProgressBar value={f.ndvi} color={ndviCol} />
                      <span style={{ color: ndviCol, fontSize: 11, fontWeight: 800, minWidth: 32, textAlign: 'left' }}>
                        {fmtNdvi(f.ndvi)}
                      </span>
                    </div>
                  ) : (
                    <div style={{ color: T.faint, fontSize: 10 }}>لا قراءة NDVI لهذا الحقل</div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* ── تفصيل مخاطر الأمراض للحقل المُحدَّد (هوك مفرد — لا تجميع) ── */}
      {selected && (
        <Card pad={14}>
          <SectionLabel
            action={
              <span className="inline-flex items-center gap-1" style={{ color: T.muted, fontSize: 11 }}>
                <Activity style={{ width: 12, height: 12 }} /> الحقل المُحدَّد
              </span>
            }
          >
            مخاطر الأمراض · {selected.name}
          </SectionLabel>

          {diseaseQ.isLoading ? (
            <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل مخاطر الأمراض…</div>
          ) : diseaseQ.isError ? (
            <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل مخاطر الأمراض لهذا الحقل.</div>
          ) : !diseaseQ.data ? (
            <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا بيانات مخاطر أمراض.</div>
          ) : (
            <div>
              <div className="flex items-center gap-2" style={{ marginBottom: 8 }}>
                <Pill tone={severityTone(diseaseQ.data.risk_level)}>
                  مستوى الخطر: {diseaseQ.data.risk_level}
                </Pill>
                {Array.isArray(diseaseQ.data.diseases_ar) && diseaseQ.data.diseases_ar.length > 0 && (
                  <span style={{ color: T.muted, fontSize: 11 }}>
                    {diseaseQ.data.diseases_ar.join('، ')}
                  </span>
                )}
              </div>
              {diseaseQ.data.advice_ar && (
                <div style={{ color: T.ink, fontSize: 12, lineHeight: 1.6 }}>{diseaseQ.data.advice_ar}</div>
              )}
              <div style={{ color: T.faint, fontSize: 10, marginTop: 8 }}>
                مخاطر الأمراض تفصيل للحقل المُحدَّد فقط — لا تدخل في ترتيب المشكلات (يرتكز على NDVI + التنبيهات).
              </div>
            </div>
          )}
        </Card>
      )}
    </FieldCabin>
  );
}
