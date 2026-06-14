// ═══════════════════════════════════════════════════════════════
// SAHOOL — «تطبيق الحقل» (معاينة) · شاشة الإثبات لنظام التصميم الجديد
// ───────────────────────────────────────────────────────────────
// تُعيد كسوة لوحة الحقل بالطراز المهنيّ الدافئ (DS الجديد) موصولةً
// ببيانات حقيقيّة (useFields / useWeatherForecast / useAlerts) — لا
// بيانات وهميّة: التحميل/الفراغ/الخطأ حالاتٌ صادقة. هذه «شاشة إثبات»
// تُبنى وتُفحَص؛ التلميع البصريّ يُكرَّر لاحقاً عبر لقطات المستخدم.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  Thermometer, Droplets, Wind, Sun, Sprout, Bell, MapPin,
  Sunrise, Sunset, CloudSun, X,
} from 'lucide-react';
import { useFields, useWeatherForecast, useAlerts } from '../hooks/useApi';
import {
  T, Card, Pill, Badge, StatBox, ProgressBar, Row, SectionLabel,
  TabBar, FAB, BottomSheet, ndviColor, severityTone,
} from '../components/ds';

type FieldLike = {
  field_id?: string;
  field_name?: string;
  name?: string;
  ndvi?: number;
  area_ha?: number;
  crop?: string;
  crop_type?: string;
};

type AlertLike = {
  alert_id?: string;
  title_ar?: string | null;
  message_ar?: string | null;
  severity?: string | null;
  created_at?: string | null;
};

const TABS = [
  { id: 'fields', label: 'الحقول', icon: <Sprout style={{ width: 15, height: 15 }} /> },
  { id: 'weather', label: 'الطقس', icon: <CloudSun style={{ width: 15, height: 15 }} /> },
  { id: 'alerts', label: 'التنبيهات', icon: <Bell style={{ width: 15, height: 15 }} /> },
] as const;

type TabId = (typeof TABS)[number]['id'];

export default function FieldAppPreview() {
  const [tab, setTab] = useState<TabId>('fields');
  const [sheet, setSheet] = useState<FieldLike | null>(null);

  const fieldsQ = useFields();
  const weatherQ = useWeatherForecast();
  const alertsQ = useAlerts();

  const fields: FieldLike[] = Array.isArray(fieldsQ.data?.fields) ? fieldsQ.data.fields : [];
  const cur = (weatherQ.data as any)?.current;
  const day0 = (weatherQ.data as any)?.daily?.[0];
  const alerts: AlertLike[] = Array.isArray(alertsQ.data) ? (alertsQ.data as AlertLike[]) : [];

  const today = new Date().toLocaleDateString('ar-SA', {
    weekday: 'long', day: 'numeric', month: 'long',
  });

  return (
    // إطار «موبايل» متمركز فوق خلفيّة دافئة — يُبرز أنّ هذه شاشة تطبيق حقل
    <div dir="rtl" style={{ background: T.cream, minHeight: '100%', padding: 16 }}>
      <div
        style={{
          maxWidth: 420, margin: '0 auto', background: T.cream,
          borderRadius: 22, border: `1px solid ${T.line}`, overflow: 'hidden',
          boxShadow: '0 12px 40px rgba(44,26,14,.10)', position: 'relative',
        }}
      >
        {/* ── Header ── */}
        <div style={{ background: T.brown, color: '#fff', padding: '18px 16px 22px' }}>
          <div className="flex items-center justify-between">
            <div>
              <div style={{ fontSize: 12, color: T.goldSoft }}>مرحباً 👋</div>
              <div style={{ fontSize: 18, fontWeight: 800 }}>تطبيق الحقل</div>
            </div>
            <Pill tone="warn" icon={<Sun style={{ width: 12, height: 12 }} />}>
              {cur ? `${Math.round(cur.tmean)}°` : '—'}
            </Pill>
          </div>
          <div style={{ fontSize: 11, color: '#D8C7B3', marginTop: 6 }}>{today}</div>
        </div>

        {/* ── Tabs ── */}
        <div style={{ background: T.card, paddingInline: 8 }}>
          <TabBar tabs={[...TABS]} active={tab} onChange={setTab} />
        </div>

        {/* ── Body ── */}
        <div style={{ padding: 14 }}>
          {tab === 'fields' && (
            <FieldsTab q={fieldsQ} fields={fields} onOpen={setSheet} />
          )}
          {tab === 'weather' && <WeatherTab q={weatherQ} cur={cur} day0={day0} />}
          {tab === 'alerts' && <AlertsTab q={alertsQ} alerts={alerts} />}
        </div>

        {/* ── FAB ── */}
        <div style={{ position: 'absolute', insetInlineStart: 16, bottom: 16 }}>
          <FAB
            icon={<MapPin style={{ width: 18, height: 18 }} />}
            label="حقل جديد"
            onClick={() => setSheet({ field_name: 'حقل جديد' })}
          />
        </div>
      </div>

      <p style={{ textAlign: 'center', color: T.muted, fontSize: 11, marginTop: 14 }}>
        معاينة نظام التصميم — موصولة بـ <code>/api/v1/fields</code> و<code>/weather/forecast</code> و
        <code>/api/v1/alerts</code> الحقيقيّة. الحالات (تحميل/فراغ/خطأ) صادقة.
      </p>

      {/* ── BottomSheet ── */}
      <BottomSheet open={!!sheet} onClose={() => setSheet(null)} title={sheet?.field_name || sheet?.name || 'الحقل'}>
        <div className="flex justify-end mb-2">
          <button onClick={() => setSheet(null)} style={{ color: T.muted, background: 'none', border: 'none' }}>
            <X style={{ width: 18, height: 18 }} />
          </button>
        </div>
        {sheet && (
          <Card pad={12}>
            <Row label="المحصول" value={sheet.crop || sheet.crop_type || '—'} />
            <Row label="المساحة" value={sheet.area_ha != null ? `${sheet.area_ha} هـ` : '—'} />
            <Row
              label="NDVI"
              value={sheet.ndvi != null ? sheet.ndvi.toFixed(2) : '—'}
              tone={sheet.ndvi != null ? (sheet.ndvi >= 0.5 ? 'ok' : 'warn') : 'neutral'}
            />
          </Card>
        )}
      </BottomSheet>
    </div>
  );
}

// ── تبويب الحقول ────────────────────────────────────────────────
function FieldsTab({
  q, fields, onOpen,
}: {
  q: { isLoading: boolean; isError: boolean };
  fields: FieldLike[];
  onOpen: (f: FieldLike) => void;
}) {
  if (q.isLoading) return <Hint>جارٍ تحميل الحقول…</Hint>;
  if (q.isError) return <Hint tone="danger">تعذّر تحميل الحقول من الخادم.</Hint>;
  if (fields.length === 0)
    return <Hint>لا توجد حقول مُسجّلة بعد — أضِف حقلاً من الزرّ العائم.</Hint>;

  return (
    <div className="space-y-3">
      <SectionLabel action={<Badge tone="ok">{fields.length} حقل</Badge>}>حقولي</SectionLabel>
      {fields.map((f, i) => {
        const ndvi = typeof f.ndvi === 'number' ? f.ndvi : null;
        const c = ndvi != null ? ndviColor(ndvi) : T.faint;
        return (
          <Card key={f.field_id || i} onClick={() => onOpen(f)} pad={12}>
            <div className="flex items-center justify-between mb-2">
              <span style={{ color: T.ink, fontWeight: 700, fontSize: 14 }}>
                {f.field_name || f.name || `حقل ${i + 1}`}
              </span>
              <span style={{ color: c, fontWeight: 800, fontSize: 14 }}>
                {ndvi != null ? ndvi.toFixed(2) : '—'}
              </span>
            </div>
            <ProgressBar value={ndvi ?? 0} color={c} />
            <div className="flex items-center gap-2 mt-2">
              {(f.crop || f.crop_type) && <Pill tone="neutral">{f.crop || f.crop_type}</Pill>}
              {f.area_ha != null && <Pill tone="neutral">{f.area_ha} هـ</Pill>}
            </div>
          </Card>
        );
      })}
    </div>
  );
}

// ── تبويب الطقس ─────────────────────────────────────────────────
function WeatherTab({
  q, cur, day0,
}: {
  q: { isLoading: boolean; isError: boolean };
  cur: any;
  day0: any;
}) {
  if (q.isLoading) return <Hint>جارٍ تحميل الطقس…</Hint>;
  if (q.isError || !cur) return <Hint tone="danger">تعذّر تحميل بيانات الطقس.</Hint>;

  return (
    <div className="space-y-3">
      <SectionLabel>الطقس الآن</SectionLabel>
      <div className="grid grid-cols-4 gap-2">
        <StatBox label="الحرارة" value={Math.round(cur.tmean)} unit="°C" color={T.warn}
          icon={<Thermometer style={{ width: 16, height: 16 }} />} />
        <StatBox label="الرطوبة" value={cur.humidity_pct} unit="%" color={T.info}
          icon={<Droplets style={{ width: 16, height: 16 }} />} />
        <StatBox label="الرياح" value={cur.wind_speed_kmh} unit="كم/س" color={T.brownSoft}
          icon={<Wind style={{ width: 16, height: 16 }} />} />
        <StatBox label="ET0" value={cur.et0_mm} unit="mm" color={T.green}
          icon={<Sprout style={{ width: 16, height: 16 }} />} />
      </div>

      {/* حقول الطاقة الشمسيّة (#159) — الشروق/الغروب/مدّة النهار/الإشعاع */}
      {day0 && (
        <Card pad={12}>
          <SectionLabel>الشمس والطاقة</SectionLabel>
          {day0.sunrise && (
            <Row label="الشروق" value={fmtTime(day0.sunrise)}
              icon={<Sunrise style={{ width: 16, height: 16 }} />} />
          )}
          {day0.sunset && (
            <Row label="الغروب" value={fmtTime(day0.sunset)}
              icon={<Sunset style={{ width: 16, height: 16 }} />} />
          )}
          {day0.daylight_hours != null && (
            <Row label="مدّة النهار" value={`${day0.daylight_hours} س`}
              icon={<Sun style={{ width: 16, height: 16 }} />} />
          )}
          {day0.solar_radiation_mj_m2 != null && (
            <Row label="السطوع (طاقة شمسيّة)" value={`${day0.solar_radiation_mj_m2} MJ/m²`}
              icon={<CloudSun style={{ width: 16, height: 16 }} />} tone="warn" />
          )}
        </Card>
      )}
    </div>
  );
}

// ── تبويب التنبيهات ─────────────────────────────────────────────
function AlertsTab({
  q, alerts,
}: {
  q: { isLoading: boolean; isError: boolean };
  alerts: AlertLike[];
}) {
  if (q.isLoading) return <Hint>جارٍ تحميل التنبيهات…</Hint>;
  if (q.isError) return <Hint tone="danger">تعذّر تحميل التنبيهات.</Hint>;
  if (alerts.length === 0) return <Hint tone="ok">لا توجد تنبيهات — كلّ شيء سليم ✅</Hint>;

  return (
    <div className="space-y-2">
      <SectionLabel action={<Badge tone="warn">{alerts.length}</Badge>}>التنبيهات</SectionLabel>
      {alerts.slice(0, 8).map((a, i) => {
        const tone = severityTone(a.severity);
        return (
          <Card key={a.alert_id || i} pad={12}>
            <div className="flex items-center justify-between mb-1">
              <Pill tone={tone}>{a.severity || 'تنبيه'}</Pill>
              <span style={{ fontSize: 10, color: T.faint }}>
                {a.created_at ? new Date(a.created_at).toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit' }) : ''}
              </span>
            </div>
            <div style={{ color: T.ink, fontWeight: 700, fontSize: 13 }}>{a.title_ar || 'تنبيه'}</div>
            {a.message_ar && <div style={{ color: T.muted, fontSize: 12, marginTop: 2 }}>{a.message_ar}</div>}
          </Card>
        );
      })}
    </div>
  );
}

// ── مساعِدات ────────────────────────────────────────────────────
function Hint({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'ok' | 'danger' }) {
  const color = tone === 'ok' ? T.green : tone === 'danger' ? T.danger : T.muted;
  return (
    <div style={{ textAlign: 'center', color, fontSize: 13, padding: '28px 12px' }}>{children}</div>
  );
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
}
