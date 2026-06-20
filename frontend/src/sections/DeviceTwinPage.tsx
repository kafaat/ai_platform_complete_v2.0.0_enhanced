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
import { Cpu, AlertTriangle, ShieldAlert, Lock, Clock, CircleHelp } from 'lucide-react';
import { useDeviceTwin } from '../hooks/useApi';
import { asApiError } from '../services/api';
import type { DeviceTwin, DeviceTwinLevel, DeviceTwinResult } from '../services/api';
import { ErrorState, LoadingState } from '../components/StateViews';

// ربط مستوى الجهاز (level) بألوان CSS محدّدة في الواجهة — لا فئات إضافيّة.
// مستوى مجهول ⇒ رماديّ محايد (fail-safe، لا حالة إيجابيّة مُختلَقة).
const LEVEL_HEX: Record<DeviceTwinLevel, string> = {
  healthy:  '#16a34a', // أخضر
  degraded: '#d97706', // كهرمانيّ
  stale:    '#ea580c', // برتقاليّ
  offline:  '#dc2626', // أحمر
  poor:     '#dc2626', // أحمر
  unknown:  '#9ca3af', // رماديّ (يحتاج بيانات — لا حالة إيجابيّة)
};
function levelHex(level: string): string {
  return LEVEL_HEX[level as DeviceTwinLevel] ?? LEVEL_HEX.unknown;
}
// خلفيّة شارة خفيفة مشتقّة (تباين مقروء على سطح داكن).
const LEVEL_BG: Record<DeviceTwinLevel, string> = {
  healthy:  '#0c2a1a',
  degraded: '#2a1a00',
  stale:    '#2a1400',
  offline:  '#2a0d0d',
  poor:     '#2a0d0d',
  unknown:  '#1e293b',
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
      className="flex items-center gap-2 rounded-lg px-3 py-1.5 border"
      style={{ background: '#1e293b', borderColor: '#334155' }}
    >
      <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: hex }} aria-hidden="true" />
      <span className="text-[12px] text-slate-200">{label}</span>
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
  const pct = Math.max(0, Math.min(1, value)) * 100;
  // لون الشريط متدرّج بالقيمة (لا حكم قاطع): منخفض كهرمانيّ، مرتفع أخضر.
  const hex = value >= 0.8 ? '#16a34a' : value >= 0.5 ? '#d97706' : '#dc2626';
  return (
    <div className="flex items-center gap-2" title={`${name}: ${pctText(value)}`}>
      <span className="text-[11px] text-slate-400 w-20 truncate">{name}</span>
      <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: '#0d1117' }}>
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: hex }} />
      </div>
      <span className="text-[11px] text-slate-300 w-9 text-left">{pctText(value)}</span>
    </div>
  );
}

// بطاقة توأم جهاز واحد.
function DeviceTwinCard({ device }: { device: DeviceTwin }) {
  const hex = levelHex(device.level);
  const factorEntries = Object.entries(device.factors ?? {});
  return (
    <article
      className="rounded-xl border p-4 space-y-3"
      style={{ background: '#1e293b', borderColor: '#334155', borderRight: `3px solid ${hex}` }}
    >
      {/* الهويّة + المستوى + الحالة */}
      <header className="flex items-start justify-between gap-2 flex-wrap">
        <div className="min-w-0">
          <div className="font-bold text-slate-100 truncate">{device.name}</div>
          <div className="text-[11px] text-slate-400">
            {device.type}
            {device.field_id ? <> · حقل: <span className="text-slate-300">{device.field_id}</span></> : null}
          </div>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span
            className="text-[11px] px-2 py-0.5 rounded-full"
            style={{ background: '#0d1117', color: '#94a3b8', border: '1px solid #334155' }}
          >
            {device.status}
          </span>
          <LevelBadge device={device} />
        </div>
      </header>

      {/* درجة الصحّة/الثقة — null ⇒ «غير محسوبة» (رماديّ) لا 0/أخضر */}
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-extrabold leading-none" style={{ color: device.health_score != null ? hex : '#9ca3af' }}>
          {pctText(device.health_score)}
        </span>
        <span className="text-[11px] text-slate-400">
          {device.health_score != null ? 'درجة الصحّة' : 'غير محسوبة'}
        </span>
      </div>

      {/* تفصيل العوامل المتوفّرة (factors) — كلّ عامل شريط مصغّر */}
      {factorEntries.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[11px] font-semibold text-slate-300">العوامل المتوفّرة</div>
          {factorEntries.map(([name, value]) => (
            <FactorBar key={name} name={name} value={value} />
          ))}
        </div>
      )}

      {/* الإشارات الغائبة المُعلَنة (missing_signals) — رقائق خافتة «غائب: …» */}
      {device.missing_signals.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-slate-500">غائب:</span>
          {device.missing_signals.map((sig) => (
            <span
              key={sig}
              className="text-[10px] px-1.5 py-0.5 rounded-full"
              style={{ background: '#0d1117', color: '#94a3b8', border: '1px dashed #475569' }}
            >
              {sig}
            </span>
          ))}
        </div>
      )}

      {/* ملاحظة الجهاز (note_ar) إن وُجدت */}
      {device.note_ar && <div className="text-[11px] text-slate-500">{device.note_ar}</div>}

      {/* آخر إرسال + البرمجيّة الثابتة */}
      <footer className="flex items-center gap-3 text-[11px] text-slate-500 pt-1 border-t" style={{ borderColor: '#25303f' }}>
        <span className="inline-flex items-center gap-1">
          <Clock className="w-3 h-3" aria-hidden="true" />
          آخر إرسال {relativeAge(device.age_sec)}
        </span>
        {device.firmware && <span>· إصدار: {device.firmware}</span>}
      </footer>
    </article>
  );
}

export default function DeviceTwinPage() {
  const query = useDeviceTwin();
  const data: DeviceTwinResult | undefined = query.data;

  // كشف 404 (العلم مُطفأ) عبر شكل خطأ أكسيوس الموحّد — رسالة ودودة لا حالة خطأ.
  const featureOff = query.isError && asApiError(query.error).response?.status === 404;

  return (
    <div className="space-y-6 max-w-6xl mx-auto" dir="rtl">
      {/* ── الترويسة ── */}
      <div className="flex items-center gap-2">
        <Cpu className="w-5 h-5 text-emerald-400" aria-hidden="true" />
        <h2 className="text-xl font-bold text-slate-100">توائم الأجهزة وثقة الحسّاس</h2>
      </div>
      <p className="text-sm text-slate-400">
        لكلّ جهاز IoT <span className="text-emerald-300">توأم رقميّ</span>: هويّة + حالة + درجة صحّة/ثقة
        شفّافة محسوبة على الإشارات المتوفّرة فقط، مع <span className="text-emerald-300">الإشارات الغائبة</span> مُعلَنةً
        (لا مُفترَضة). الدرجة الغائبة تُعرَض «غير محسوبة» لا صفراً.
      </p>

      {/* ── الحالات ── */}
      {query.isLoading && <LoadingState message="جارٍ جلب توائم الأجهزة…" />}

      {/* الميزة غير مُفعَّلة (404 — العلم مُطفأ) */}
      {featureOff && (
        <div
          className="rounded-xl border p-4 flex items-start gap-3"
          style={{ background: '#1e293b', borderColor: '#334155' }}
          role="status"
        >
          <ShieldAlert className="w-5 h-5 text-slate-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
          <div className="space-y-1">
            <div className="text-sm font-semibold text-slate-200">الميزة غير مُفعَّلة (FEATURE_DEVICE_TWIN)</div>
            <div className="text-[12px] text-slate-400">
              توائم الأجهزة خلف علم تشغيل (FEATURE_DEVICE_TWIN) لم يُفعَّل بعد على الخادم. تواصل مع المسؤول لتفعيله.
            </div>
          </div>
        </div>
      )}

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
        <div
          className="rounded-xl border p-4 text-sm text-slate-400"
          style={{ background: '#1e293b', borderColor: '#334155' }}
          role="status"
        >
          لا أجهزة مُسجَّلة لهذا المستأجِر — لا تتوفّر بيانات توائم.
        </div>
      )}

      {data && data.devices.length > 0 && (
        <div className="space-y-6">
          {/* ── ترويسة تلخيص الأسطول ── */}
          <section
            className="rounded-xl border p-4 space-y-3"
            style={{ background: '#10151f', borderColor: '#25303f' }}
          >
            <div className="flex items-end gap-6 flex-wrap">
              <div>
                <div
                  className="text-4xl font-extrabold leading-none"
                  style={{ color: data.fleet_confidence != null ? '#34d399' : '#9ca3af' }}
                >
                  {data.fleet_confidence != null ? pctText(data.fleet_confidence) : 'غير محسوبة'}
                </div>
                <div className="text-[11px] text-slate-400 mt-1">ثقة الأسطول (متوسّط المُسجَّلين)</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-slate-100 leading-none">{data.device_count}</div>
                <div className="text-[11px] text-slate-400 mt-1">إجماليّ الأجهزة</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-slate-100 leading-none">{data.scored_count}</div>
                <div className="text-[11px] text-slate-400 mt-1">مُسجَّلة (مُحتسَبة)</div>
              </div>
              <div className="text-[11px] text-slate-500 mr-auto self-center">
                آخر تحديث: <span className="text-slate-400">{data.generated_at}</span>
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
          </section>

          {/* ── بانر الصدق/المصدر (provenance) — كهرمانيّ ── */}
          <div
            className="rounded-xl border p-4 flex items-start gap-3"
            style={{ background: '#1a1400', borderColor: '#f59e0b33' }}
          >
            <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
            <div className="space-y-1">
              <div className="text-sm font-semibold text-amber-200">
                🟡 ثقة الحسّاس معادلة موزونة شفّافة على الإشارات المتوفّرة فقط — الغائبة مُعلَنة لا مُفترَضة
              </div>
              <div className="text-[12px] text-amber-300/80">{data.provenance.note_ar}</div>
              <div className="text-[11px] text-slate-400">
                «يحتاج بيانات» (unknown) لا يُحتسَب في ثقة الأسطول — حالة صادقة لا إيجابيّة.
              </div>
            </div>
          </div>

          {/* ── ملاحظة قراءة فقط (لا أوامر) ── */}
          <div className="flex items-center gap-2 text-[12px] text-slate-500">
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
