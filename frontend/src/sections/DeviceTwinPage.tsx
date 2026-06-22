// ═══════════════════════════════════════════════════════════════
// SAHOOL — DeviceTwinPage (توائم الأجهزة وثقة الحسّاس) — GET /api/v1/devices/twin
// قراءة فقط: لكلّ جهاز IoT توأم رقميّ — هويّة + حالة + درجة صحّة/ثقة شفّافة (موزونة
// على الإشارات المتوفّرة فقط) + تفصيل العوامل (factors) + الإشارات الغائبة المُعلَنة
// (missing_signals)، مع تلخيص ثقة الأسطول (fleet_confidence).
//
// الصدق: health_score/fleet_confidence قد تكون null ⇒ «—» / «غير محسوبة» لا 0.
// level==='unknown' حالة «يحتاج بيانات» (رماديّ) لا حالة إيجابيّة، ولا تُحتسَب في
// ثقة الأسطول. الإشارات الغائبة مُعلَنة لا مُفترَضة. لا أوامر تشغيل/إيقاف (قراءة فقط).
//
// العلم مُطفأً (FEATURE_DEVICE_TWIN) ⇒ 404 ⇒ «الميزة غير مُفعَّلة» (لا انهيار).
// 503 ⇒ القاعدة غير متاحة (ErrorState صادقة). devices:[] ⇒ «لا أجهزة مُسجَّلة».
// ═══════════════════════════════════════════════════════════════
import { Cpu, AlertTriangle, Lock, Clock, CircleHelp } from 'lucide-react';
import { useDeviceTwin } from '../hooks/useApi';
import type { DeviceTwin, DeviceTwinLevel, DeviceTwinResult } from '../services/api';
import { ErrorState, LoadingState, FeatureDisabledState, isFeatureDisabledError } from '../components/StateViews';
import { Card, StatBox, ProgressBar } from '../components/ds/atoms';
import { T } from '../components/ds/tokens';

// ربط مستوى الجهاز (level) بألوان DS دافئة — مستوى مجهول ⇒ رماديّ محايد
// (fail-safe، لا حالة إيجابيّة مُختلَقة).
const LEVEL_HEX: Record<DeviceTwinLevel, string> = {
  healthy:  T.green,   // أخضر
  degraded: T.warn,    // كهرمانيّ
  stale:    '#E67E22', // برتقاليّ
  offline:  T.danger,  // أحمر
  poor:     T.danger,  // أحمر
  unknown:  T.faint,   // رماديّ دافئ (يحتاج بيانات — لا حالة إيجابيّة)
};
function levelHex(level: string): string {
  return LEVEL_HEX[level as DeviceTwinLevel] ?? LEVEL_HEX.unknown;
}
// خلفيّة شارة خفيفة مشتقّة (تباين مقروء على سطح فاتح).
const LEVEL_BG: Record<DeviceTwinLevel, string> = {
  healthy:  T.okBg,
  degraded: T.warnBg,
  stale:    '#FBEAD9',
  offline:  T.dangerBg,
  poor:     T.dangerBg,
  unknown:  T.card2,
};
function levelBg(level: string): string {
  return LEVEL_BG[level as DeviceTwinLevel] ?? LEVEL_BG.unknown;
}

// درجة 0..1 كنسبة مئويّة — null ⇒ «—» (لا تلفيق، لا 0).
function pctText(v: number | null): string {
  return v != null ? `${(v * 100).toFixed(0)}%` : '—';
}

// age_sec ⇒ نصّ نسبيّ بشريّ «منذ …». null ⇒ «لم يُرسِل بعد» (لا افتراض).
function relativeAge(ageSec: number | null): string {
  if (ageSec == null) return 'لم يُرسِل بعد';
  const s = Math.max(0, Math.floor(ageSec));
  if (s < 60) return `منذ ${s} ث`;
  const m = Math.floor(s / 60);
  if (m < 60) return `منذ ${m} د`;
  const h = Math.floor(m / 60);
  if (h < 24) return `منذ ${h} س`;
  const d = Math.floor(h / 24);
  return `منذ ${d} ي`;
}

// شارة المستوى الملوّنة (level_ar) — لونها من level الخادم.
function LevelBadge({ device }: { device: DeviceTwin }) {
  const hex = levelHex(device.level);
  return (
    <span
      className="text-[11px] px-2 py-0.5 rounded-full font-semibold whitespace-nowrap inline-flex items-center gap-1"
      style={{ background: levelBg(device.level), color: hex }}
    >
      {device.level === 'unknown' && <CircleHelp className="w-3 h-3" aria-hidden="true" />}
      {device.level_ar}
    </span>
  );
}

// شارة عدّ مستوى (للأسطورة في الترويسة) — لونها من المستوى.
function ByLevelChip({ level, count, label }: { level: string; count: number; label: string }) {
  const hex = levelHex(level);
  return (
    <div
      className="flex items-center gap-2 rounded-lg px-3 py-1.5"
      style={{ background: T.card2, border: `1px solid ${T.line}` }}
    >
      <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: hex }} aria-hidden="true" />
      <span className="text-[12px]" style={{ color: T.ink }}>{label}</span>
      <span
        className="text-[12px] font-bold px-1.5 rounded-full"
        style={{ background: levelBg(level), color: hex }}
      >
        {count}
      </span>
    </div>
  );
}

// تسميات عربيّة لمستويات by_level (مفتاح ثابت من العقد).
const LEVEL_LABEL_AR: Record<string, string> = {
  healthy:  'سليم',
  degraded: 'متدهور',
  stale:    'بائت',
  offline:  'غير متّصل',
  poor:     'ضعيف',
  unknown:  'يحتاج بيانات',
};
const LEVEL_ORDER: DeviceTwinLevel[] = ['healthy', 'degraded', 'stale', 'offline', 'poor', 'unknown'];

// مقياس عامل مفرد (factor) كشريط مصغّر + قيمته 0..1.
function FactorBar({ name, value }: { name: string; value: number }) {
  // لون الشريط متدرّج بالقيمة (لا حكم قاطع): منخفض كهرمانيّ، مرتفع أخضر.
  const hex = value >= 0.8 ? T.green : value >= 0.5 ? T.warn : T.danger;
  return (
    <div className="flex items-center gap-2" title={`${name}: ${pctText(value)}`}>
      <span className="text-[11px] w-20 truncate" style={{ color: T.muted }}>{name}</span>
      <div className="flex-1">
        <ProgressBar value={value} color={hex} height={6} />
      </div>
      <span className="text-[11px] w-9 text-left" style={{ color: T.brownSoft }}>{pctText(value)}</span>
    </div>
  );
}

// بطاقة توأم جهاز واحد.
function DeviceTwinCard({ device }: { device: DeviceTwin }) {
  const hex = levelHex(device.level);
  const factorEntries = Object.entries(device.factors ?? {});
  return (
    <Card style={{ borderRight: `3px solid ${hex}` }}>
      <div className="space-y-3">
        {/* الهويّة + المستوى + الحالة */}
        <header className="flex items-start justify-between gap-2 flex-wrap">
          <div className="min-w-0">
            <div className="font-bold truncate" style={{ color: T.ink }}>{device.name}</div>
            <div className="text-[11px]" style={{ color: T.muted }}>
              {device.type}
              {device.field_id ? <> · حقل: <span style={{ color: T.brownSoft }}>{device.field_id}</span></> : null}
            </div>
          </div>
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <span
              className="text-[11px] px-2 py-0.5 rounded-full"
              style={{ background: T.card2, color: T.muted, border: `1px solid ${T.line}` }}
            >
              {device.status}
            </span>
            <LevelBadge device={device} />
          </div>
        </header>

        {/* درجة الصحّة/الثقة — null ⇒ «غير محسوبة» (رماديّ) لا 0/أخضر */}
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-extrabold leading-none" style={{ color: device.health_score != null ? hex : T.faint }}>
            {pctText(device.health_score)}
          </span>
          <span className="text-[11px]" style={{ color: T.muted }}>
            {device.health_score != null ? 'درجة الصحّة' : 'غير محسوبة'}
          </span>
        </div>

        {/* تفصيل العوامل المتوفّرة (factors) — كلّ عامل شريط مصغّر */}
        {factorEntries.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-[11px] font-semibold" style={{ color: T.brownSoft }}>العوامل المتوفّرة</div>
            {factorEntries.map(([name, value]) => (
              <FactorBar key={name} name={name} value={value} />
            ))}
          </div>
        )}

        {/* الإشارات الغائبة المُعلَنة (missing_signals) — رقائق خافتة «غائب: …» */}
        {device.missing_signals.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px]" style={{ color: T.muted }}>غائب:</span>
            {device.missing_signals.map((sig) => (
              <span
                key={sig}
                className="text-[10px] px-1.5 py-0.5 rounded-full"
                style={{ background: T.card2, color: T.muted, border: `1px dashed ${T.faint}` }}
              >
                {sig}
              </span>
            ))}
          </div>
        )}

        {/* ملاحظة الجهاز (note_ar) إن وُجدت */}
        {device.note_ar && <div className="text-[11px]" style={{ color: T.muted }}>{device.note_ar}</div>}

        {/* آخر إرسال + البرمجيّة الثابتة */}
        <footer className="flex items-center gap-3 text-[11px] pt-1" style={{ color: T.muted, borderTop: `1px solid ${T.line}` }}>
          <span className="inline-flex items-center gap-1">
            <Clock className="w-3 h-3" aria-hidden="true" />
            آخر إرسال {relativeAge(device.age_sec)}
          </span>
          {device.firmware && <span>· إصدار: {device.firmware}</span>}
        </footer>
      </div>
    </Card>
  );
}

export default function DeviceTwinPage() {
  const query = useDeviceTwin();
  const data: DeviceTwinResult | undefined = query.data;

  // كشف 404 (العلم مُطفأ) عبر المُساعِد الموحّد — رسالة ودودة لا حالة خطأ.
  const featureOff = query.isError && isFeatureDisabledError(query.error);

  return (
    <div className="space-y-6 max-w-6xl mx-auto" dir="rtl">
      {/* ── الترويسة ── */}
      <div className="flex items-center gap-2">
        <Cpu className="w-5 h-5" style={{ color: T.green }} aria-hidden="true" />
        <h2 className="text-xl font-bold" style={{ color: T.ink }}>توائم الأجهزة وثقة الحسّاس</h2>
      </div>
      <p className="text-sm" style={{ color: T.muted }}>
        لكلّ جهاز IoT <span style={{ color: T.green }}>توأم رقميّ</span>: هويّة + حالة + درجة صحّة/ثقة
        شفّافة محسوبة على الإشارات المتوفّرة فقط، مع <span style={{ color: T.green }}>الإشارات الغائبة</span> مُعلَنةً
        (لا مُفترَضة). الدرجة الغائبة تُعرَض «غير محسوبة» لا صفراً.
      </p>

      {/* ── الحالات ── */}
      {query.isLoading && <LoadingState message="جارٍ جلب توائم الأجهزة…" />}

      {/* الميزة غير مُفعَّلة (404 — العلم مُطفأ) · لوحة StateViews الموحّدة */}
      {featureOff && <FeatureDisabledState page="device-twin" />}

      {/* 503/أيّ خطأ آخر — حالة خطأ صادقة */}
      {query.isError && !featureOff && (
        <ErrorState
          title="تعذّر جلب توائم الأجهزة"
          detail="قد تكون قاعدة البيانات غير متاحة (503) أو حدث انقطاع."
          onRetry={() => query.refetch()}
        />
      )}

      {/* devices:[] — لا أجهزة */}
      {data && data.devices.length === 0 && (
        <Card>
          <div className="text-sm" style={{ color: T.muted }} role="status">
            لا أجهزة مُسجَّلة لهذا المستأجِر — لا تتوفّر بيانات توائم.
          </div>
        </Card>
      )}

      {data && data.devices.length > 0 && (
        <div className="space-y-6">
          {/* ── ترويسة تلخيص الأسطول ── */}
          <Card>
            <div className="space-y-3">
              <div className="flex items-end gap-4 flex-wrap">
                <div style={{ minWidth: 140 }}>
                  <StatBox
                    label="ثقة الأسطول (متوسّط المُسجَّلين)"
                    value={data.fleet_confidence != null ? pctText(data.fleet_confidence) : 'غير محسوبة'}
                    color={data.fleet_confidence != null ? T.green : T.faint}
                  />
                </div>
                <div style={{ minWidth: 110 }}>
                  <StatBox label="إجماليّ الأجهزة" value={data.device_count} />
                </div>
                <div style={{ minWidth: 110 }}>
                  <StatBox label="مُسجَّلة (مُحتسَبة)" value={data.scored_count} />
                </div>
                <div className="text-[11px] mr-auto self-center" style={{ color: T.muted }}>
                  آخر تحديث: <span style={{ color: T.brownSoft }}>{data.generated_at}</span>
                </div>
              </div>

              {/* رقائق عدّ المستويات (by_level) ملوّنة */}
              <div className="flex flex-wrap gap-2">
                {LEVEL_ORDER.map((lvl) => (
                  <ByLevelChip
                    key={lvl}
                    level={lvl}
                    count={data.by_level?.[lvl] ?? 0}
                    label={LEVEL_LABEL_AR[lvl] ?? lvl}
                  />
                ))}
              </div>
            </div>
          </Card>

          {/* ── بانر الصدق/المصدر (provenance) — كهرمانيّ ── */}
          <Card style={{ background: T.warnBg, border: `1px solid ${T.warn}33` }}>
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: T.warn }} aria-hidden="true" />
              <div className="space-y-1">
                <div className="text-sm font-semibold" style={{ color: T.ink }}>
                  🟡 ثقة الحسّاس معادلة موزونة شفّافة على الإشارات المتوفّرة فقط — الغائبة مُعلَنة لا مُفترَضة
                </div>
                <div className="text-[12px]" style={{ color: T.brownSoft }}>{data.provenance.note_ar}</div>
                <div className="text-[11px]" style={{ color: T.muted }}>
                  «يحتاج بيانات» (unknown) لا يُحتسَب في ثقة الأسطول — حالة صادقة لا إيجابيّة.
                </div>
              </div>
            </div>
          </Card>

          {/* ── ملاحظة قراءة فقط (لا أوامر) ── */}
          <div className="flex items-center gap-2 text-[12px]" style={{ color: T.muted }}>
            <Lock className="w-3.5 h-3.5" aria-hidden="true" />
            قراءة فقط — لا أوامر تشغيل/إيقاف على الأجهزة من هذه الصفحة.
          </div>

          {/* ── بطاقات التوائم ── */}
          <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {data.devices.map((d) => (
              <DeviceTwinCard key={d.device_id} device={d} />
            ))}
          </section>
        </div>
      )}
    </div>
  );
}
