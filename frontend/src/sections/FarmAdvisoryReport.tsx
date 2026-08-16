// ═══════════════════════════════════════════════════════════════
// SAHOOL — تقرير استشارة المزرعة (Farm Advisory Report)
// ───────────────────────────────────────────────────────────────
// تقرير واحد قابل للتمرير لحقلٍ مُختار، يصهر محرّكات قائمة (هوكات موجودة) في
// أقسام مترابطة — على غرار «التقارير / استشارة المزرعة» في Farmonaut. لا خادم
// جديد ولا بيانات جديدة: تركيب حيّ فوق ما تُرجِعه الهوكات فعليّاً فقط.
//
// الأقسام (كلّ منها بطاقة DS بحالاتها الصريحة تحميل/خطأ/فراغ — «غير متاح لهذا
// الحقل» عند غياب البيانات، بلا اختلاق):
//   ١) النموّ والعائد   — useSeasons(fieldId) → الموسم النشط/الأحدث (SeasonSummary):
//      crop · season_end · sim_yield_kg_ha / sim_biomass_kg_ha (أو «—» مع تلميح
//      إن لم تُشغَّل المحاكاة) · عدد المراحل. نفس بيانات PhenologyView.
//   ٢) الأسمدة والتربة  — useSoilParams(fieldId) (تركيب التربة pH/EC/OM/N/P/K) +
//      useSoilNRecommendation(fieldId) (توصية النيتروجين). صدق: ربط NPK الكامل
//      بمنتجات (يوريا/DAP بكمّيّات) فجوة موثّقة ⛔ غير مبنيّة — نعرض فقط ما تُعيده
//      الهوكات. شكل ردّ هذين المسارين غير مُنمَّط في الخدمة (data: unknown)، فنقرأه
//      بمتسامحات آمنة (نصّ/رقم) دون فرض شكلٍ غير مضمون.
//   ٣) الآفات والأمراض  — useDiseaseRisk(fieldId) (مستوى الخطر/العوامل/النصح) +
//      useCropScoutingIssues(crop) (مشاكل المحصول الشائعة: name_ar/category/code).
//   ٤) سرد المؤشّرات    — useCurrentNDVI(fieldId) (ndvi.current + التصنيف الصحّيّ) +
//      useFieldReport(fieldId) (ملخّص الحقل: مساحة/موسم/تنبيهات).
//
// محصول الحقل المختار (FieldOption.crop) يُغذّي هوك مشاكل الاستكشاف.
// فجوات موثّقة: تصدير PDF والتقارير الدوريّة التلقائيّة غير مبنيّة (انظر الحاشية).
// ═══════════════════════════════════════════════════════════════
import { useMemo } from 'react';
import type { ReactNode } from 'react';
import {
  Sprout, Leaf, Calendar, Flag, FlaskConical, Bug, Activity,
  TrendingUp, ShieldAlert, Droplets, MapPin, Layers,
} from 'lucide-react';
import {
  useSeasons, useSoilParams, useSoilNRecommendation,
  useDiseaseRisk, useCurrentNDVI, useFieldReport, SOIL_ENABLED,
} from '../hooks/useApi';
import { useCropScoutingIssues, type ScoutingIssue } from '../hooks/useScouting';
import { useSelectedField } from '../hooks/useSelectedField';
import type { SeasonSummary, FieldReportSummary, DiseaseRisk } from '../services/api';
import { fmtDateAr } from '../lib/dates';
import {
  T, T_DARK, Card, Pill, Badge, SectionLabel, Row, StatGrid, ProgressBar,
  FieldCabin, ndviColor, severityTone,
} from '../components/ds';
import type { Tone } from '../components/ds';

// الصفحة داكنة (نغمة ds الداكنة): أسطح/نصوص من T_DARK؛ ألوان التمييز من T.
const t = T_DARK;

// ── متسامحات قراءة آمنة (الهوكات soil/ndvi تُعيد data غير مُنمَّط) ──────────
function asNum(v: unknown): number | null {
  const n = typeof v === 'string' ? Number(v) : v;
  return typeof n === 'number' && Number.isFinite(n) ? n : null;
}
function asStr(v: unknown): string | null {
  return typeof v === 'string' && v.trim() ? v : null;
}
// يقرأ أوّل مفتاح موجود من قائمة مرادفات (الخدمة قد تسمّي الحقل بأكثر من اسم).
function pickNum(obj: unknown, keys: string[]): number | null {
  if (!obj || typeof obj !== 'object') return null;
  const rec = obj as Record<string, unknown>;
  for (const k of keys) {
    const n = asNum(rec[k]);
    if (n != null) return n;
  }
  return null;
}
function pickStr(obj: unknown, keys: string[]): string | null {
  if (!obj || typeof obj !== 'object') return null;
  const rec = obj as Record<string, unknown>;
  for (const k of keys) {
    const s = asStr(rec[k]);
    if (s != null) return s;
  }
  return null;
}

// يختار الموسم النشط إن وُجد، وإلّا الأحدث (الخادم يُرجع الأحدث أوّلاً).
function pickSeason(seasons: SeasonSummary[]): SeasonSummary | null {
  if (!seasons.length) return null;
  return seasons.find((s) => s.status === 'active') ?? seasons[0];
}

function seasonStatusAr(status: string): string {
  if (status === 'active') return 'نشط';
  if (status === 'closed') return 'مُغلَق';
  if (status === 'planned') return 'مُخطَّط';
  return status || '—';
}

// نغمة + تسمية مستوى خطر المرض (low/moderate/high — صريحة من الخادم).
function riskTone(level: string): Tone {
  const s = (level ?? '').toLowerCase();
  if (s === 'high') return 'danger';
  if (s === 'moderate') return 'warn';
  if (s === 'low') return 'ok';
  return 'neutral';
}
function riskAr(level: string): string {
  const s = (level ?? '').toLowerCase();
  if (s === 'high') return 'مرتفع';
  if (s === 'moderate') return 'متوسّط';
  if (s === 'low') return 'منخفض';
  return level || '—';
}

// تسمية عربيّة لفئة مشكلة الاستكشاف (للوسم).
const CATEGORY_AR: Record<string, string> = {
  disease: 'مرض', pest: 'آفة', weed: 'عشب', nutrient: 'نقص عنصر',
  water_stress: 'إجهاد مائيّ', abiotic: 'غير حيويّ', other: 'أخرى',
};
const categoryAr = (c?: string) => CATEGORY_AR[(c ?? '').toLowerCase()] ?? (c || 'أخرى');

// ── حالة قسم موحّدة (تحميل/خطأ/فراغ صريحة لكلّ بطاقة) ────────────────────
function SectionState({
  loading, error, empty, icon, emptyText, children,
}: {
  loading: boolean;
  error: boolean;
  empty: boolean;
  icon: ReactNode;
  emptyText: string;
  children: ReactNode;
}) {
  if (loading) {
    return (
      <div style={{ color: t.muted, fontSize: 13, padding: '16px 0', textAlign: 'center' }}>
        جارٍ التحميل…
      </div>
    );
  }
  if (error) {
    return (
      <div style={{ color: T.danger, fontSize: 13, padding: '16px 0', textAlign: 'center' }}>
        تعذّر تحميل البيانات من الخادم.
      </div>
    );
  }
  if (empty) {
    return (
      <div
        className="flex flex-col items-center"
        style={{ color: t.muted, fontSize: 13, padding: '20px 0', gap: 8 }}
      >
        <span style={{ color: t.faint }}>{icon}</span>
        {emptyText}
      </div>
    );
  }
  return <>{children}</>;
}

// شارة حالة موحّدة (مباشر/تحميل/خطأ) لرأس كلّ قسم.
function LiveBadge({ loading, error }: { loading: boolean; error: boolean }) {
  return (
    <Badge tone={loading ? 'neutral' : error ? 'danger' : 'ok'}>
      {loading ? 'تحميل…' : error ? 'خطأ' : 'مباشر'}
    </Badge>
  );
}

export default function FarmAdvisoryReport() {
  // «الحقل النشط» المشترك (useSelectedField) — يتبع المستخدم عبر الشاشات.
  const { options: fields, isLoading: fieldsLoading, isError: fieldsError, refetch, fieldId, setFieldId } = useSelectedField();

  const selectedField = useMemo(
    () => fields.find((f) => f.id === fieldId) ?? null,
    [fields, fieldId],
  );
  // محصول الحقل المختار (FieldOption.crop) يُغذّي هوك مشاكل الاستكشاف.
  // «—» في التطبيع يعني «لا محصول» ⇒ لا نُفعّل الهوك بقيمة وهميّة.
  const crop = selectedField && selectedField.crop !== '—' ? selectedField.crop : undefined;

  // ── الهوكات (مُفعَّلة على fieldId — لا طلب قبل الاختيار) ──
  const seasonsQ = useSeasons(fieldId || undefined);
  const soilQ = useSoilParams(fieldId);
  const nRecQ = useSoilNRecommendation(fieldId);
  const diseaseQ = useDiseaseRisk(fieldId || undefined);
  const issuesQ = useCropScoutingIssues(crop);
  const ndviQ = useCurrentNDVI(fieldId);
  const reportQ = useFieldReport(fieldId || undefined);

  // ١) النموّ والعائد ───────────────────────────────────────────
  const seasons = useMemo<SeasonSummary[]>(
    () => (Array.isArray(seasonsQ.data) ? seasonsQ.data : []),
    [seasonsQ.data],
  );
  const season = useMemo(() => pickSeason(seasons), [seasons]);

  // ٢) التربة والنيتروجين — قراءة متسامحة (البيانات غير مُنمَّطة في الخدمة) ──
  const soil = soilQ.data;
  const soilRows = useMemo(() => {
    // مرادفات أسماء محتملة لكلّ خاصّيّة (نقرأ أوّل موجود — لا نفترض شكلاً وحيداً).
    const ph = pickNum(soil, ['ph', 'pH', 'soil_ph']);
    const ec = pickNum(soil, ['ec', 'ec_ds_m', 'ec_dsm', 'salinity']);
    const om = pickNum(soil, ['om', 'organic_matter', 'om_pct', 'soc']);
    const n = pickNum(soil, ['n_ppm', 'nitrogen', 'n', 'nitrogen_mg_kg']);
    const p = pickNum(soil, ['p_ppm', 'phosphorus', 'p', 'phosphorus_mg_kg']);
    const k = pickNum(soil, ['k_ppm', 'potassium', 'k', 'potassium_mg_kg']);
    return [
      { label: 'الحموضة pH', value: ph, unit: '' },
      { label: 'الملوحة EC', value: ec, unit: 'dS/m' },
      { label: 'المادّة العضويّة', value: om, unit: '%' },
      { label: 'النيتروجين N', value: n, unit: 'ppm' },
      { label: 'الفوسفور P', value: p, unit: 'ppm' },
      { label: 'البوتاسيوم K', value: k, unit: 'ppm' },
    ];
  }, [soil]);
  // صدق: حين تكون التربة معطّلة (soil-service غير منشورة ولا مكافئ على المنصّة)
  // لا نعرض «تحميلاً» أبديّاً (الاستعلام معطّل ⇒ pending إلى الأبد) ولا خطأً — بل
  // حالة فراغ صريحة «بيانات التربة غير متاحة». الأعلام أدناه تُحيّد التحميل/الخطأ
  // عند التعطيل وتُجبر الفراغ، فيقرأ المستخدم سبباً صادقاً لا دوّامة تحميل.
  const soilDisabled = !SOIL_ENABLED;
  const soilLoading = !soilDisabled && soilQ.isLoading;
  const soilError = !soilDisabled && soilQ.isError;
  // التربة فارغة إن لم نتمكّن من قراءة أيّ خاصّيّة معروفة (لا نختلق صفراً)، أو معطّلة.
  const soilEmpty = soilDisabled
    || (!soilQ.isLoading && !soilQ.isError && soilRows.every((r) => r.value == null));
  const soilEmptyText = soilDisabled
    ? 'بيانات التربة غير متاحة — خدمة التربة غير منشورة بعد.'
    : 'غير متاح لهذا الحقل — لا قراءات تربة.';

  // توصية النيتروجين — رقم + نصّ سبب إن توفّرا (شكل غير مُنمَّط، قراءة متسامحة).
  const nRec = nRecQ.data;
  const nRate = pickNum(nRec, ['n_recommendation_kg_ha', 'n_kg_ha', 'recommended_n_kg_ha', 'n_rate', 'nitrogen_kg_ha']);
  const nRationale = pickStr(nRec, ['rationale_ar', 'note_ar', 'rationale', 'note', 'message']);
  const nRecLoading = !soilDisabled && nRecQ.isLoading;
  const nRecError = !soilDisabled && nRecQ.isError;
  const nRecEmpty = soilDisabled
    || (!nRecQ.isLoading && !nRecQ.isError && nRate == null && nRationale == null);
  const nRecEmptyText = soilDisabled
    ? 'توصية النيتروجين غير متاحة — خدمة التربة غير منشورة بعد.'
    : 'غير متاح لهذا الحقل — لا توصية نيتروجين.';

  // ٣) الأمراض + مشاكل المحصول ──────────────────────────────────
  const disease = diseaseQ.data as DiseaseRisk | undefined;
  const issues = useMemo<ScoutingIssue[]>(
    () => (Array.isArray(issuesQ.data?.issues) ? issuesQ.data!.issues : []),
    [issuesQ.data],
  );

  // ٤) المؤشّرات ────────────────────────────────────────────────
  const ndviData = ndviQ.data as
    | { ndvi?: { current?: number | null }; classification?: { label_ar?: string; score?: number }; acquisition_date?: string | null }
    | undefined;
  const ndviVal = asNum(ndviData?.ndvi?.current);
  const ndviLabel = asStr(ndviData?.classification?.label_ar);
  const ndviScore = asNum(ndviData?.classification?.score);
  const report = reportQ.data as FieldReportSummary | undefined;

  const headerPill = (
    <Pill tone="info" icon={<Activity style={{ width: 12, height: 12 }} />}>
      تقرير حيّ
    </Pill>
  );

  return (
    <FieldCabin
      tone="dark"
      eyebrow="كابينة الميدان"
      title="استشارة المزرعة"
      subtitle="تقرير موحّد يصهر محرّكات الحقل الحيّة — لحقلٍ واحد"
      headerRight={headerPill}
      note={
        <>
          تقرير مُركَّب حيّاً من محرّكات حقيقيّة (مواسم/تربة/طقس/استكشاف/غطاء نباتيّ).
          كلّ قسم صادق بشأن بياناته — «غير متاح لهذا الحقل» حين تغيب. تصدير PDF
          والتقارير الدوريّة التلقائيّة فجوتان موثّقتان ⛔ غير مبنيّتين بعد.
        </>
      }
    >
      {/* ── اختيار الحقل ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel action={<LiveBadge loading={fieldsLoading} error={fieldsError} />}>
          الحقل
        </SectionLabel>

        {fieldsLoading ? (
          <div style={{ color: t.muted, fontSize: 13, padding: '12px 0', textAlign: 'center' }}>
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
          <div className="flex flex-col items-center" style={{ color: t.muted, fontSize: 13, padding: '16px 0', gap: 8 }}>
            <Sprout style={{ width: 26, height: 26, color: t.faint }} />
            لا توجد حقول بعد — أضِف حقلاً من «إدارة الحقول».
          </div>
        ) : (
          <>
            <select
              value={fieldId}
              onChange={(e) => setFieldId(e.target.value)}
              style={{
                width: '100%', padding: '10px 12px', borderRadius: 12,
                border: `1px solid ${t.line}`, background: t.card, color: t.ink,
                fontSize: 14, fontWeight: 600,
              }}
            >
              {fields.map((f) => (
                <option key={f.id} value={f.id}>{f.name}</option>
              ))}
            </select>
            {selectedField && (
              <div className="flex items-center gap-2" style={{ flexWrap: 'wrap', marginTop: 10 }}>
                <Pill tone="neutral" icon={<MapPin style={{ width: 11, height: 11 }} />}>
                  {selectedField.name}
                </Pill>
                <Pill tone="neutral" icon={<Sprout style={{ width: 11, height: 11 }} />}>
                  المحصول: {crop ?? '—'}
                </Pill>
                {selectedField.area > 0 && (
                  <Pill tone="neutral" icon={<Layers style={{ width: 11, height: 11 }} />}>
                    {selectedField.area.toFixed(2)} هـ
                  </Pill>
                )}
              </div>
            )}
          </>
        )}
      </Card>

      {fieldId && (
        <>
          {/* ─────────── ١) النموّ والعائد ─────────── */}
          <Card pad={14} style={{ marginBottom: 10 }}>
            <SectionLabel action={<LiveBadge loading={seasonsQ.isLoading} error={seasonsQ.isError} />}>
              النموّ والعائد
            </SectionLabel>

            <SectionState
              loading={seasonsQ.isLoading}
              error={seasonsQ.isError}
              empty={!season}
              icon={<Sprout style={{ width: 26, height: 26 }} />}
              emptyText="غير متاح لهذا الحقل — لا موسم مُسجَّل بعد."
            >
              {season && (
                <>
                  <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
                    <div className="flex items-center gap-2" style={{ fontSize: 14, fontWeight: 800, color: t.ink }}>
                      <Sprout style={{ width: 16, height: 16, color: T.green }} />
                      {season.crops.length ? season.crops.join('، ') : '—'}
                    </div>
                    <Badge tone={season.status === 'active' ? 'ok' : 'neutral'}>
                      {seasonStatusAr(season.status)}
                    </Badge>
                  </div>

                  <div className="flex items-center gap-2" style={{ flexWrap: 'wrap', marginBottom: 10 }}>
                    <Pill tone="neutral" icon={<Calendar style={{ width: 11, height: 11 }} />}>
                      زراعة: {fmtDateAr(season.sowing_date)}
                    </Pill>
                    <Pill tone="neutral" icon={<Flag style={{ width: 11, height: 11 }} />}>
                      حصاد/نهاية: {fmtDateAr(season.season_end)}
                    </Pill>
                  </div>

                  {/* تقديرات المحاكاة المُخزَّنة sim_* — «—» مع تلميح إن لم تُشغَّل */}
                  {(season.sim_yield_kg_ha != null || season.sim_biomass_kg_ha != null) ? (
                    <StatGrid
                      cols={3}
                      items={[
                        {
                          label: 'العائد (تقديريّ)',
                          value: season.sim_yield_kg_ha != null ? Math.round(season.sim_yield_kg_ha) : '—',
                          unit: 'كغ/هـ', color: T.green,
                          icon: <TrendingUp style={{ width: 14, height: 14 }} />,
                        },
                        {
                          label: 'الكتلة الحيويّة',
                          value: season.sim_biomass_kg_ha != null ? Math.round(season.sim_biomass_kg_ha) : '—',
                          unit: 'كغ/هـ', color: T.gold,
                          icon: <Leaf style={{ width: 14, height: 14 }} />,
                        },
                        {
                          label: 'عدد المراحل',
                          value: Array.isArray(season.stages) ? season.stages.length : 0,
                          icon: <Layers style={{ width: 14, height: 14 }} />,
                        },
                      ]}
                    />
                  ) : (
                    <div
                      style={{
                        background: t.card2, borderRadius: 12, padding: '10px 12px',
                        border: `1px solid ${t.line}`,
                      }}
                    >
                      <div className="flex items-center justify-between" style={{ marginBottom: 4 }}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: t.brownSoft }}>
                          تقديرات العائد/الكتلة الحيويّة
                        </span>
                        <span style={{ fontSize: 14, fontWeight: 800, color: t.faint }}>—</span>
                      </div>
                      <div style={{ fontSize: 11, color: t.faint }}>
                        لم تُشغَّل محاكاة الموسم بعد — العائد والكتلة الحيويّة تقديريّان يُملآن
                        بعد التشغيل. عدد المراحل: {Array.isArray(season.stages) ? season.stages.length : 0}.
                      </div>
                    </div>
                  )}
                </>
              )}
            </SectionState>
          </Card>

          {/* ─────────── ٢) إدارة الأسمدة والتربة ─────────── */}
          <Card pad={14} style={{ marginBottom: 10 }}>
            <SectionLabel action={<LiveBadge loading={soilLoading} error={soilError} />}>
              إدارة الأسمدة والتربة
            </SectionLabel>

            <SectionState
              loading={soilLoading}
              error={soilError}
              empty={soilEmpty}
              icon={<FlaskConical style={{ width: 26, height: 26 }} />}
              emptyText={soilEmptyText}
            >
              <div>
                {soilRows.map((r) => (
                  <Row
                    key={r.label}
                    label={r.label}
                    value={
                      r.value != null
                        ? `${r.value}${r.unit ? ` ${r.unit}` : ''}`
                        : <span style={{ color: t.faint }}>—</span>
                    }
                  />
                ))}
              </div>
            </SectionState>

            {/* توصية النيتروجين (هوك منفصل بحالته الخاصّة) */}
            <div style={{ marginTop: 12 }}>
              <SectionLabel action={<LiveBadge loading={nRecLoading} error={nRecError} />}>
                توصية النيتروجين (N)
              </SectionLabel>
              <SectionState
                loading={nRecLoading}
                error={nRecError}
                empty={nRecEmpty}
                icon={<FlaskConical style={{ width: 24, height: 24 }} />}
                emptyText={nRecEmptyText}
              >
                {nRate != null && (
                  <div className="flex items-center justify-between" style={{ marginBottom: nRationale ? 6 : 0 }}>
                    <span style={{ fontSize: 13, color: t.brownSoft }}>النيتروجين الموصى به</span>
                    <span style={{ fontSize: 16, fontWeight: 800, color: T.green }}>
                      {Math.round(nRate)} <span style={{ fontSize: 11, fontWeight: 600 }}>كغ/هـ</span>
                    </span>
                  </div>
                )}
                {nRationale && (
                  <div style={{ fontSize: 12, color: t.brownSoft, lineHeight: 1.7 }}>{nRationale}</div>
                )}
              </SectionState>
            </div>

            {/* صدق: ربط NPK→منتجات (يوريا/DAP بكمّيّات) فجوة موثّقة، غير مبنيّة */}
            <div
              style={{
                marginTop: 12, background: t.warnBg, borderRadius: 10,
                padding: '8px 10px', fontSize: 11, color: t.brownSoft, lineHeight: 1.6,
              }}
            >
              ملاحظة: ربط NPK الكامل بمنتجات سماديّة محدّدة (كمّيّات يوريا/DAP) فجوة
              موثّقة ⛔ غير مبنيّة — يُعرَض هنا فقط ما تُعيده المحرّكات (تركيب التربة
              وتوصية النيتروجين).
            </div>
          </Card>

          {/* ─────────── ٣) مكافحة الآفات والأمراض والأعشاب ─────────── */}
          <Card pad={14} style={{ marginBottom: 10 }}>
            <SectionLabel action={<LiveBadge loading={diseaseQ.isLoading} error={diseaseQ.isError} />}>
              مكافحة الآفات والأمراض والأعشاب
            </SectionLabel>

            <SectionState
              loading={diseaseQ.isLoading}
              error={diseaseQ.isError}
              empty={!disease}
              icon={<ShieldAlert style={{ width: 26, height: 26 }} />}
              emptyText="غير متاح لهذا الحقل — لا تقدير مخاطر أمراض."
            >
              {disease && (
                <>
                  <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: t.brownSoft }}>مستوى خطر المرض</span>
                    <Pill tone={riskTone(disease.risk_level)} icon={<ShieldAlert style={{ width: 11, height: 11 }} />}>
                      {riskAr(disease.risk_level)}
                    </Pill>
                  </div>

                  <div className="flex items-center gap-2" style={{ flexWrap: 'wrap', marginBottom: 8 }}>
                    <Pill tone="neutral">الحرارة: {disease.temperature_c}°م</Pill>
                    <Pill tone="neutral">الرطوبة: {disease.humidity_pct}%</Pill>
                    <Pill tone="neutral">مطر 3 أيّام: {disease.rain_mm_3d} مم</Pill>
                  </div>

                  {disease.diseases_ar.length > 0 && (
                    <div className="flex items-center gap-1" style={{ flexWrap: 'wrap', marginBottom: 8 }}>
                      {disease.diseases_ar.map((d, i) => (
                        <Pill key={`${d}-${i}`} tone="warn" icon={<Bug style={{ width: 11, height: 11 }} />}>
                          {d}
                        </Pill>
                      ))}
                    </div>
                  )}

                  {disease.advice_ar && (
                    <div style={{ fontSize: 12, color: t.brownSoft, lineHeight: 1.7 }}>{disease.advice_ar}</div>
                  )}
                </>
              )}
            </SectionState>

            {/* مشاكل المحصول الشائعة (دليل الاستكشاف) — مفعّل فقط عند وجود محصول */}
            <div style={{ marginTop: 12 }}>
              <SectionLabel
                action={
                  crop
                    ? <LiveBadge loading={issuesQ.isLoading} error={issuesQ.isError} />
                    : <Badge tone="neutral">بلا محصول</Badge>
                }
              >
                مشاكل المحصول الشائعة
              </SectionLabel>
              {!crop ? (
                <div className="flex flex-col items-center" style={{ color: t.muted, fontSize: 13, padding: '16px 0', gap: 8 }}>
                  <Bug style={{ width: 24, height: 24, color: t.faint }} />
                  غير متاح لهذا الحقل — لا محصول مُسنَد لجلب مشاكله.
                </div>
              ) : (
                <SectionState
                  loading={issuesQ.isLoading}
                  error={issuesQ.isError}
                  empty={issues.length === 0}
                  icon={<Bug style={{ width: 24, height: 24 }} />}
                  emptyText="غير متاح لهذا المحصول — لا مشاكل مُصنَّفة."
                >
                  <div>
                    {issues.map((it) => (
                      <Row
                        key={it.code}
                        label={it.name_ar || it.code}
                        value={<Pill tone="neutral">{categoryAr(it.category)}</Pill>}
                      />
                    ))}
                  </div>
                </SectionState>
              )}
            </div>
          </Card>

          {/* ─────────── ٤) سرد المؤشّرات ─────────── */}
          <Card pad={14}>
            <SectionLabel action={<LiveBadge loading={ndviQ.isLoading} error={ndviQ.isError} />}>
              سرد المؤشّرات
            </SectionLabel>

            <SectionState
              loading={ndviQ.isLoading}
              error={ndviQ.isError}
              empty={ndviVal == null}
              icon={<Droplets style={{ width: 26, height: 26 }} />}
              emptyText="غير متاح لهذا الحقل — لا قيمة NDVI حاليّة."
            >
              {ndviVal != null && (
                <>
                  <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
                    <div className="flex items-center gap-2" style={{ fontSize: 13, fontWeight: 700, color: t.brownSoft }}>
                      <Leaf style={{ width: 14, height: 14, color: ndviColor(ndviVal) }} />
                      NDVI الحاليّ
                    </div>
                    <span style={{ fontSize: 18, fontWeight: 800, color: ndviColor(ndviVal) }}>
                      {ndviVal.toFixed(2)}
                    </span>
                  </div>
                  <ProgressBar value={ndviVal} color={ndviColor(ndviVal)} height={8} />
                  <div className="flex items-center justify-between" style={{ marginTop: 8 }}>
                    {ndviLabel && (
                      <Badge tone={severityTone(ndviLabel)}>الصحّة: {ndviLabel}</Badge>
                    )}
                    {ndviScore != null && (
                      <span style={{ fontSize: 12, color: t.muted }}>المؤشّر الصحّيّ: {Math.round(ndviScore)}٪</span>
                    )}
                  </div>
                  {ndviData?.acquisition_date && (
                    <div style={{ fontSize: 11, color: t.faint, marginTop: 6 }}>
                      تاريخ الالتقاط: {fmtDateAr(ndviData.acquisition_date)}
                    </div>
                  )}
                </>
              )}
            </SectionState>

            {/* ملخّص الحقل (تقرير الحقل) — هوك منفصل بحالته */}
            <div style={{ marginTop: 12 }}>
              <SectionLabel action={<LiveBadge loading={reportQ.isLoading} error={reportQ.isError} />}>
                ملخّص صحّة الحقل
              </SectionLabel>
              <SectionState
                loading={reportQ.isLoading}
                error={reportQ.isError}
                empty={!report}
                icon={<Activity style={{ width: 24, height: 24 }} />}
                emptyText="غير متاح لهذا الحقل — لا ملخّص."
              >
                {report && (
                  <div>
                    <Row label="المحصول" value={report.crop ?? <span style={{ color: t.faint }}>—</span>} />
                    <Row label="المساحة" value={`${report.area_ha.toFixed(2)} هـ`} />
                    <Row label="نوع التربة" value={report.soil_type ?? <span style={{ color: t.faint }}>—</span>} />
                    <Row label="إجمالي العمليّات" value={report.activities_total} />
                    <Row
                      label="تنبيهات حديثة"
                      value={report.recent_alerts.length}
                      tone={report.recent_alerts.length > 0 ? 'warn' : 'ok'}
                    />
                  </div>
                )}
              </SectionState>
            </div>
          </Card>
        </>
      )}
    </FieldCabin>
  );
}
