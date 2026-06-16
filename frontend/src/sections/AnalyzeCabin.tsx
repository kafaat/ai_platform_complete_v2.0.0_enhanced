// ═══════════════════════════════════════════════════════════════
// SAHOOL — التحليل (Analyze Cabin) · وجهة «التحليل» في القشرة الموحّدة
// ───────────────────────────────────────────────────────────────
// تصهر تحليلات الحقل في لوحٍ واحد: سلسلة مؤشّر الغطاء (NDVI) الزمنيّة +
// مخاطر الأمراض المناخيّة + ملخّص الموسم/الإنتاج المُقدَّر. تملأ إحدى وجهتَي
// «قيد الإنشاء» في القشرة الموحّدة (UnifiedCabin).
//
// صدق البيانات: السلسلة من useFieldTimeseries (متوسّطات COG الحقيقيّة) مع
// سقوط رشيق إلى useVegetationTimeseries؛ لا COG/سلسلة ⇒ حالة فارغة لا رسم
// وهميّ. مخاطر الأمراض من useDiseaseRisk الحيّة. الموسم/الإنتاج المُقدَّر من
// useSeasons (حقول sim_* تكون null ما لم تُشغَّل المحاكاة ⇒ تُعرَض «—»).
// كلّ الحالات (تحميل/فراغ/خطأ) صريحة. شاشة قراءة فقط (معاينة دمج).
// ═══════════════════════════════════════════════════════════════
import { useMemo } from 'react';
import { BarChart3, TrendingUp, TrendingDown, Minus, Bug, Sprout, Leaf, Activity } from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import {
  useFieldTimeseries, useVegetationTimeseries, useDiseaseRisk, useSeasons,
  type TimeseriesPoint as VegTimeseriesPoint,
} from '../hooks/useApi';
import { useSelectedField } from '../hooks/useSelectedField';
import { fmtDateAr } from '../lib/dates';
import {
  T, Card, Pill, Badge, SectionLabel, Row, StatGrid, RadialGauge,
  FieldCabin, severityTone,
} from '../components/ds';
import type { Tone } from '../components/ds';

// نقطة الرسم الموحّدة: تاريخ (للمحور) + قيمة المؤشّر [0..1 عادةً].
interface ChartPoint { date: string; value: number }

// تسمية عربيّة + نغمة لمستوى مخاطر المرض.
const RISK_AR: Record<string, string> = { low: 'منخفضة', moderate: 'متوسّطة', high: 'مرتفعة' };
const riskAr = (r?: string) => RISK_AR[(r ?? '').toLowerCase()] ?? (r || '—');
function riskTone(r?: string): Tone {
  const k = (r ?? '').toLowerCase();
  if (k === 'high') return 'danger';
  if (k === 'moderate') return 'warn';
  if (k === 'low') return 'ok';
  return 'neutral';
}

// تاريخ مختصر للمحور (يوم/شهر) عبر المُنسّق الموحّد.
const fmtAxis = (s?: string) => fmtDateAr(s, { day: 'numeric', month: 'short' });

// تنسيق رقم مُقدَّر (إنتاج/حيويّة) أو «—» إن غاب — لا تلفيق صفر.
const fmtNum = (n?: number | null) =>
  typeof n === 'number' && Number.isFinite(n) ? Math.round(n).toLocaleString('ar') : '—';

export default function AnalyzeCabin() {
  // «الحقل النشط» المشترك (useSelectedField) — يتبع المستخدم عبر الشاشات.
  const fieldsQ = useSelectedField();
  const fields = fieldsQ.options;

  const { fieldId, setFieldId } = fieldsQ;
  const field = fields.find((f) => f.id === fieldId) ?? fields[0];
  const activeId = field?.id ?? '';

  // السلسلة الزمنيّة: متوسّطات COG الحقيقيّة (raster) أوّلاً، وإلّا سلسلة vegetation.
  const rasterTsQ = useFieldTimeseries(activeId, 'ndvi', '');
  const vegTsQ = useVegetationTimeseries(activeId, 90);
  const diseaseQ = useDiseaseRisk(activeId || undefined);
  const seasonsQ = useSeasons(activeId || undefined);

  // نقاط الرسم: نفضّل raster (available + points)، ثمّ نسقط إلى vegetation.
  // لا نخلط المصدرين — نلتزم بسلسلة واحدة صادقة المصدر.
  const { points, sourceLabel } = useMemo<{ points: ChartPoint[]; sourceLabel: string | null }>(() => {
    const rPts = rasterTsQ.data?.available ? (rasterTsQ.data.points ?? []) : [];
    if (rPts.length > 0) {
      const mapped = rPts
        .filter((p) => p.datetime && Number.isFinite(p.mean))
        .map((p) => ({ date: p.datetime, value: p.mean }));
      if (mapped.length > 0) return { points: mapped, sourceLabel: 'متوسّطات COG حقيقيّة' };
    }
    const vPts: VegTimeseriesPoint[] = Array.isArray(vegTsQ.data?.timeseries) ? vegTsQ.data.timeseries : [];
    const mappedV = vPts
      .filter((p) => p.date && Number.isFinite(p.ndvi))
      .map((p) => ({ date: p.date, value: p.ndvi }));
    if (mappedV.length > 0) return { points: mappedV, sourceLabel: 'سلسلة الغطاء النباتيّ' };
    return { points: [], sourceLabel: null };
  }, [rasterTsQ.data, vegTsQ.data]);

  // اتّجاه السلسلة من raster-service (slope/direction) إن توفّر — لا نحسبه يدويّاً.
  const trend = rasterTsQ.data?.available ? rasterTsQ.data.trend : undefined;
  const trendDir = trend?.direction;

  // آخر قيمة فعليّة في السلسلة (للعدّاد) — % إن كانت ضمن [0,1].
  const latest = points.length ? points[points.length - 1] : undefined;
  const latestPct = latest && latest.value >= 0 && latest.value <= 1
    ? Math.round(latest.value * 100) : null;

  const tsLoading = rasterTsQ.isLoading || vegTsQ.isLoading;
  const tsError = rasterTsQ.isError && vegTsQ.isError;

  const disease = diseaseQ.data;
  const seasons = Array.isArray(seasonsQ.data) ? seasonsQ.data : [];
  // أحدث موسم به نتيجة محاكاة مُخزَّنة (sim_yield) — تقديريّة بنطاق.
  const simSeason = seasons.find((s) => typeof s.sim_yield_kg_ha === 'number') ?? seasons[0];

  return (
    <FieldCabin
      eyebrow="التحليل"
      title="تحليل الحقل"
      subtitle="سلسلة المؤشّر الزمنيّة + مخاطر الأمراض + الإنتاج المُقدَّر"
      headerRight={
        <Pill tone="info" icon={<BarChart3 style={{ width: 12, height: 12 }} />}>
          {points.length} نقطة
        </Pill>
      }
      note={
        <>
          التحليل الموحّد — سلسلة <code>/fields/&#123;id&#125;/timeseries</code> (متوسّطات COG حقيقيّة)
          مع سقوط رشيق إلى سلسلة الغطاء النباتيّ، ومخاطر <code>/disease-risk</code>، وإنتاج
          الموسم المُقدَّر (محاكاة). لا COG/محاكاة ⇒ «غير متاح» صراحةً لا قيم مُختلَقة.
        </>
      }
    >
      {/* ── اختيار الحقل ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={<Badge tone={fieldsQ.isLoading ? 'neutral' : fieldsQ.isError ? 'danger' : 'ok'}>
            {fieldsQ.isLoading ? 'تحميل…' : fieldsQ.isError ? 'خطأ' : `${fields.length} حقل`}
          </Badge>}
        >
          الحقل
        </SectionLabel>
        {fieldsQ.isLoading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل الحقول…</div>
        ) : fieldsQ.isError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل الحقول.</div>
        ) : fields.length === 0 ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا حقول مُسجّلة.</div>
        ) : (
          <select
            value={field?.id ?? ''}
            onChange={(e) => setFieldId(e.target.value)}
            style={{
              width: '100%', padding: '9px 10px', borderRadius: 10,
              border: `1px solid ${T.line}`, background: T.card, color: T.ink, fontSize: 14, fontWeight: 600,
            }}
          >
            {fields.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        )}
      </Card>

      {/* ── سلسلة المؤشّر الزمنيّة (NDVI) ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={
            <span className="inline-flex items-center gap-2">
              {sourceLabel && <Badge tone="ok">{sourceLabel}</Badge>}
              {trendDir === 'increasing' || trendDir === 'up' ? (
                <span className="inline-flex items-center gap-1" style={{ color: T.ok, fontSize: 11 }}>
                  <TrendingUp style={{ width: 12, height: 12 }} /> صاعد
                </span>
              ) : trendDir === 'decreasing' || trendDir === 'down' ? (
                <span className="inline-flex items-center gap-1" style={{ color: T.danger, fontSize: 11 }}>
                  <TrendingDown style={{ width: 12, height: 12 }} /> هابط
                </span>
              ) : trendDir ? (
                <span className="inline-flex items-center gap-1" style={{ color: T.muted, fontSize: 11 }}>
                  <Minus style={{ width: 12, height: 12 }} /> مستقرّ
                </span>
              ) : null}
            </span>
          }
        >
          سلسلة الغطاء النباتيّ (NDVI)
        </SectionLabel>

        {!activeId ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '8px 0' }}>اختر حقلاً لعرض سلسلته الزمنيّة.</div>
        ) : tsLoading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل السلسلة الزمنيّة…</div>
        ) : tsError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل السلسلة الزمنيّة.</div>
        ) : points.length === 0 ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '8px 0' }}>لا بيانات سلسلة زمنيّة لهذا الحقل بعد.</div>
        ) : (
          <>
            <div className="flex items-center" style={{ gap: 14 }}>
              <RadialGauge
                pct={latestPct}
                label="أحدث NDVI"
                color={T.green}
              />
              <div style={{ flex: 1 }}>
                <ResponsiveContainer width="100%" height={130}>
                  <LineChart data={points} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={T.line} />
                    <XAxis
                      dataKey="date"
                      tickFormatter={fmtAxis}
                      tick={{ fill: T.faint, fontSize: 9 }}
                      tickLine={false}
                      interval={Math.max(0, Math.floor(points.length / 5))}
                    />
                    <YAxis domain={[0, 1]} tick={{ fill: T.faint, fontSize: 10 }} tickLine={false} width={32} />
                    <Tooltip
                      contentStyle={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: 8, fontSize: 12 }}
                      labelFormatter={(l) => fmtAxis(String(l))}
                      formatter={(v: number | string) => [Number(v).toFixed(2), 'NDVI']}
                    />
                    <Line type="monotone" dataKey="value" stroke={T.green} strokeWidth={2} dot={{ r: 2, fill: T.green }} name="NDVI" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </>
        )}
      </Card>

      {/* ── مخاطر الأمراض المناخيّة ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={
            <span className="inline-flex items-center gap-1" style={{ color: T.muted, fontSize: 11 }}>
              <Bug style={{ width: 12, height: 12 }} /> مناخيّة
            </span>
          }
        >
          مخاطر الأمراض
        </SectionLabel>

        {!activeId ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>اختر حقلاً لتقييم المخاطر.</div>
        ) : diseaseQ.isLoading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تقييم المخاطر…</div>
        ) : diseaseQ.isError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تقييم مخاطر الأمراض (قد يتعذّر الطقس).</div>
        ) : !disease ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا تقييم متاح.</div>
        ) : (
          <>
            <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
              <span style={{ fontSize: 13, color: T.ink, fontWeight: 600 }}>مستوى الخطر</span>
              <Pill tone={riskTone(disease.risk_level)}>{riskAr(disease.risk_level)}</Pill>
            </div>
            <StatGrid
              cols={3}
              items={[
                { label: 'الحرارة', value: Number.isFinite(disease.temperature_c) ? disease.temperature_c : '—', unit: '°م' },
                { label: 'الرطوبة', value: Number.isFinite(disease.humidity_pct) ? disease.humidity_pct : '—', unit: '%' },
                { label: 'مطر ٣ أيّام', value: Number.isFinite(disease.rain_mm_3d) ? disease.rain_mm_3d : '—', unit: 'مم' },
              ]}
            />
            {Array.isArray(disease.diseases_ar) && disease.diseases_ar.length > 0 && (
              <div style={{ marginTop: 8 }}>
                {disease.diseases_ar.map((d, i) => (
                  <Row key={i} icon={<Leaf style={{ width: 14, height: 14, color: T.warn }} />} label={d} value={null} />
                ))}
              </div>
            )}
            {disease.advice_ar && (
              <div style={{ fontSize: 12, color: T.muted, marginTop: 8, lineHeight: 1.7 }}>{disease.advice_ar}</div>
            )}
          </>
        )}
      </Card>

      {/* ── الموسم والإنتاج المُقدَّر (محاكاة) ── */}
      <Card pad={14}>
        <SectionLabel
          action={
            <span className="inline-flex items-center gap-1" style={{ color: T.muted, fontSize: 11 }}>
              <Activity style={{ width: 12, height: 12 }} /> {seasons.length} موسم
            </span>
          }
        >
          الموسم والإنتاج المُقدَّر
        </SectionLabel>

        {!activeId ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>اختر حقلاً لعرض مواسمه.</div>
        ) : seasonsQ.isLoading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل المواسم…</div>
        ) : seasonsQ.isError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل مواسم الحقل.</div>
        ) : !simSeason ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا مواسم مُسجّلة لهذا الحقل.</div>
        ) : (
          <>
            <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
              <span className="inline-flex items-center gap-2">
                <Sprout style={{ width: 16, height: 16, color: T.green }} />
                <span style={{ fontSize: 13, fontWeight: 700, color: T.ink }}>
                  {Array.isArray(simSeason.crops) && simSeason.crops.length ? simSeason.crops.join('، ') : 'موسم'}
                </span>
              </span>
              <Badge tone={severityTone(simSeason.status)}>{simSeason.status || '—'}</Badge>
            </div>
            <StatGrid
              cols={3}
              items={[
                {
                  label: 'الإنتاج المُقدَّر', value: fmtNum(simSeason.sim_yield_kg_ha), unit: 'كجم/هـ',
                  color: simSeason.sim_yield_kg_ha != null ? T.green : T.faint,
                },
                {
                  label: 'الحيويّة', value: fmtNum(simSeason.sim_biomass_kg_ha), unit: 'كجم/هـ',
                  color: simSeason.sim_biomass_kg_ha != null ? T.ink : T.faint,
                },
                {
                  label: 'ماء الموسم', value: fmtNum(simSeason.sim_water_mm), unit: 'مم',
                  color: simSeason.sim_water_mm != null ? T.info : T.faint,
                },
              ]}
            />
            {simSeason.sim_ran_at ? (
              <div style={{ fontSize: 10, color: T.faint, marginTop: 8 }}>
                تقديرات محاكاة (نطاق وثقة) — شُغِّلت {fmtDateAr(simSeason.sim_ran_at, { day: 'numeric', month: 'short', year: 'numeric' })}.
              </div>
            ) : (
              <div style={{ fontSize: 10, color: T.faint, marginTop: 8 }}>
                لم تُشغَّل المحاكاة لهذا الموسم بعد — قيم الإنتاج المُقدَّر غير متاحة («—»).
              </div>
            )}
          </>
        )}
      </Card>
    </FieldCabin>
  );
}
