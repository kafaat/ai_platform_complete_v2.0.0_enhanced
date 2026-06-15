// ═══════════════════════════════════════════════════════════════
// SAHOOL — المراقبة الهجينة (Hybrid Monitor) · شاشة دمج خامسة (الأخيرة)
// ───────────────────────────────────────────────────────────────
// تصهر «حسّاسات التربة/الريّ» (FieldView/سهول) مع «عدّادات الآلة» (Operations
// Center) في لوحٍ واحد: قراءات أجهزة الحقل الحيّة + حالة الأسطول. تجسيد
// UI_DESIGN_SPEC_UNIFIED.md §2 (الوحدة الرابعة). تكمّل الوحدات الخمس الجامعة.
//
// صدق البيانات: قراءات الحسّاسات من useDeviceTelemetry الحقيقيّة (لكلّ جهاز)؛
// ساعات تشغيل المعدّات من useEquipment الحقيقيّة. لا عدّادات وقود/DEF للآلة
// (فجوة ⛔ موثّقة §5) — تُعرَض «غير متاح» صراحةً لا حلقة مضلّلة. الحالات
// (تحميل/فراغ/خطأ) صريحة. شاشة قراءة فقط (معاينة دمج).
// ═══════════════════════════════════════════════════════════════
import { useMemo, useState } from 'react';
import {
  Cpu, Tractor, Droplets, Thermometer, FlaskConical, Battery, Gauge, Activity, Wrench,
} from 'lucide-react';
import { useDevices, useDeviceTelemetry, useEquipment } from '../hooks/useApi';
import { useFieldOptions } from '../hooks/useFieldOptions';
import type { TelemetryPoint } from '../services/api';
import { fmtDateAr } from '../lib/dates';
import {
  T, Card, Pill, Badge, SectionLabel, Row, StatGrid, RadialGauge, ExpandableCard,
  LayerSwitcher, FieldCabin, equipStatusAr, equipStatusTone,
} from '../components/ds';

// تسمية عربيّة لنوع الحسّاس + هل يُعرَض كعدّاد نصف-قطريّ (0–100).
const SENSOR_AR: Record<string, string> = {
  soil_moisture: 'رطوبة التربة', moisture: 'الرطوبة', humidity: 'الرطوبة الجوّيّة',
  temperature: 'الحرارة', ec: 'الملوحة (EC)', ph: 'الحموضة (pH)',
  battery: 'البطّاريّة', rainfall: 'الأمطار', water_level: 'منسوب الماء',
};
const sensorAr = (s?: string) => SENSOR_AR[(s ?? '').toLowerCase()] ?? (s || 'قياس');
const GAUGE_SENSORS = new Set(['soil_moisture', 'moisture', 'humidity', 'battery']);
// عدّاد نصف-قطريّ فقط لقياس نسبيّ صريح (الوحدة «%») وضمن [0,100] — تفادياً
// لعرض مقياس مضلّل حين يُبلَّغ الحسّاس كسراً (0–1) أو بوحدة خام. غير ذلك → صفّ.
function isPercentGauge(p: TelemetryPoint): boolean {
  return GAUGE_SENSORS.has((p.sensor_type ?? '').toLowerCase())
    && p.unit === '%'
    && Number.isFinite(p.value) && p.value >= 0 && p.value <= 100;
}

function sensorIcon(s?: string) {
  const k = (s ?? '').toLowerCase();
  if (k.includes('moisture') || k === 'humidity' || k === 'water_level') return <Droplets style={{ width: 14, height: 14, color: T.info }} />;
  if (k === 'temperature') return <Thermometer style={{ width: 14, height: 14, color: T.danger }} />;
  if (k === 'ec' || k === 'ph') return <FlaskConical style={{ width: 14, height: 14, color: T.green }} />;
  if (k === 'battery') return <Battery style={{ width: 14, height: 14, color: T.gold }} />;
  return <Gauge style={{ width: 14, height: 14, color: T.muted }} />;
}

// وقت القراءة (يعيد استخدام مُنسّق التواريخ الموحّد بخيار الساعة/الدقيقة).
const fmtTime = (s?: string) => fmtDateAr(s, { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' });

export default function HybridMonitor() {
  const fieldsQ = useFieldOptions();
  const devicesQ = useDevices();
  const equipQ = useEquipment();

  const fields = fieldsQ.options;

  const [fieldId, setFieldId] = useState('');
  const field = fields.find((f) => f.id === fieldId) ?? fields[0];

  const allDevices = Array.isArray(devicesQ.data) ? devicesQ.data : [];
  // مطابقة منسوبة بعد التطبيع (field.id مُمرَّر عبر String؛ نطبّع d.field_id كذلك
  // كي لا ينهار التطابق إن أرجع الخادم field_id رقماً) — null لا يطابق حقلاً.
  const fieldDevices = field ? allDevices.filter((d) => d.field_id != null && String(d.field_id) === field.id) : [];

  const [deviceId, setDeviceId] = useState('');
  const activeDevice = fieldDevices.find((d) => d.device_id === deviceId) ?? fieldDevices[0];

  const telemetryQ = useDeviceTelemetry(activeDevice?.device_id ?? '', 30);
  // أحدث قراءة لكلّ نوع حسّاس (التتبّع مُرتَّب تنازليّاً عادةً؛ نحفظ الأوّل لكلّ نوع).
  const latestBySensor = useMemo(() => {
    const points: TelemetryPoint[] = Array.isArray(telemetryQ.data) ? telemetryQ.data : [];
    const m = new Map<string, TelemetryPoint>();
    for (const p of points) {
      const k = (p.sensor_type ?? '').toLowerCase();
      const prev = m.get(k);
      if (!prev || new Date(p.recorded_at).getTime() > new Date(prev.recorded_at).getTime()) m.set(k, p);
    }
    return Array.from(m.values());
  }, [telemetryQ.data]);

  const equipment = Array.isArray(equipQ.data) ? equipQ.data : [];
  // «تحتاج صيانة» مشتقّ من مصدر النغمة الموحّد (status.ts) لا من قائمة محليّة.
  const needsService = equipment.filter((e) => ['warn', 'danger'].includes(equipStatusTone(e.status)));
  const [openFleet, setOpenFleet] = useState(false);

  return (
    <FieldCabin
      eyebrow="المراقبة الهجينة"
      title="حقل + آلة"
      subtitle="قراءات الحسّاسات الحيّة + حالة الأسطول — لوحٌ واحد"
      headerRight={<Pill tone="info" icon={<Activity style={{ width: 12, height: 12 }} />}>{fieldDevices.length} جهاز</Pill>}
      note={
        <>
          المراقبة الهجينة الموحّدة — قراءات <code>/devices/&#123;id&#125;/telemetry</code> الحيّة +
          ساعات <code>/equipment</code>. لا عدّادات وقود/DEF للآلة (فجوة موثّقة ⛔) — تُعرَض «غير
          متاح» لا حلقة مضلّلة. الحالات صادقة.
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
            onChange={(e) => { setFieldId(e.target.value); setDeviceId(''); }}
            style={{
              width: '100%', padding: '9px 10px', borderRadius: 10,
              border: `1px solid ${T.line}`, background: T.card, color: T.ink, fontSize: 14, fontWeight: 600,
            }}
          >
            {fields.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        )}
      </Card>

      {/* ── حسّاسات الحقل ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel action={<span className="inline-flex items-center gap-1" style={{ color: T.muted, fontSize: 11 }}><Cpu style={{ width: 12, height: 12 }} /> الحسّاسات</span>}>
          قراءات الحقل
        </SectionLabel>

        {devicesQ.isLoading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل الأجهزة…</div>
        ) : devicesQ.isError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل الأجهزة.</div>
        ) : fieldDevices.length === 0 ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا أجهزة منسوبة لهذا الحقل.</div>
        ) : (
          <>
            <div style={{ marginBottom: 10 }}>
              <LayerSwitcher
                layers={fieldDevices.map((d) => ({ id: d.device_id, label: d.name || 'جهاز', icon: <Cpu style={{ width: 12, height: 12 }} /> }))}
                active={activeDevice?.device_id ?? ''}
                onChange={setDeviceId}
              />
            </div>

            {activeDevice && (
              <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
                <span style={{ fontSize: 12, color: T.muted }}>{activeDevice.name}</span>
                <Pill tone={activeDevice.online ? 'ok' : 'neutral'}>{activeDevice.online ? 'متّصل' : 'غير متّصل'}</Pill>
              </div>
            )}

            {telemetryQ.isLoading ? (
              <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل القراءات…</div>
            ) : telemetryQ.isError ? (
              <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل قراءات هذا الجهاز.</div>
            ) : latestBySensor.length === 0 ? (
              <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا قراءات حديثة لهذا الجهاز.</div>
            ) : (
              <>
                {/* عدّادات نصف-قطريّة للحسّاسات النسبيّة الصريحة (وحدتها %) */}
                <div className="flex" style={{ gap: 12, justifyContent: 'space-around', flexWrap: 'wrap' }}>
                  {latestBySensor
                    .filter(isPercentGauge)
                    .map((p) => (
                      <RadialGauge
                        key={p.sensor_type}
                        pct={Math.round(p.value)}
                        label={sensorAr(p.sensor_type)}
                        color={T.info}
                      />
                    ))}
                </div>
                {/* بقيّة القراءات كصفوف (بوحدتها الخام — لا افتراض مقياس) */}
                {latestBySensor
                  .filter((p) => !isPercentGauge(p))
                  .map((p) => (
                    <Row
                      key={p.sensor_type}
                      icon={sensorIcon(p.sensor_type)}
                      label={sensorAr(p.sensor_type)}
                      value={
                        <span className="inline-flex items-center gap-2">
                          <b style={{ color: T.ink }}>{p.value}{p.unit ? ` ${p.unit}` : ''}</b>
                          <span style={{ fontSize: 10, color: T.faint }}>{fmtTime(p.recorded_at)}</span>
                        </span>
                      }
                    />
                  ))}
              </>
            )}
          </>
        )}
      </Card>

      {/* ── حالة الأسطول (ساعات حقيقيّة، وقود/DEF غير متاح) ── */}
      <ExpandableCard
        expanded={openFleet}
        onToggle={() => setOpenFleet((v) => !v)}
        header={
          <div className="flex items-center gap-2">
            <Tractor style={{ width: 16, height: 16, color: T.brownSoft }} />
            <span style={{ fontWeight: 700, fontSize: 14 }}>عدّادات الآلة</span>
            <Badge tone={needsService.length ? 'warn' : 'ok'}>
              {needsService.length ? `${needsService.length} تحتاج صيانة` : `${equipment.length} جاهزة`}
            </Badge>
          </div>
        }
      >
        {equipQ.isLoading ? (
          <div style={{ color: T.muted, fontSize: 12 }}>جارٍ تحميل المعدّات…</div>
        ) : equipQ.isError ? (
          <div style={{ color: T.danger, fontSize: 12 }}>تعذّر تحميل المعدّات.</div>
        ) : equipment.length === 0 ? (
          <div style={{ color: T.muted, fontSize: 13 }}>لا معدّات مُسجّلة.</div>
        ) : (
          <>
            <StatGrid
              cols={3}
              items={[
                { label: 'إجماليّ', value: equipment.length, icon: <Tractor style={{ width: 16, height: 16, color: T.brownSoft }} /> },
                { label: 'تحتاج صيانة', value: needsService.length, color: needsService.length ? T.warn : T.ok, icon: <Wrench style={{ width: 16, height: 16, color: needsService.length ? T.warn : T.ok }} /> },
                { label: 'وقود/DEF', value: '—', color: T.faint, icon: <Gauge style={{ width: 16, height: 16, color: T.faint }} /> },
              ]}
            />
            <div style={{ marginTop: 8 }}>
              {equipment.map((e, i) => (
                <Row
                  key={e.equipment_id || i}
                  icon={<Tractor style={{ width: 16, height: 16, color: T.brownSoft }} />}
                  label={e.name || 'معدّة'}
                  value={
                    <span className="inline-flex items-center gap-2">
                      <Pill tone={equipStatusTone(e.status)}>{equipStatusAr(e.status)}</Pill>
                      {typeof e.operating_hours === 'number' && (
                        <span style={{ fontSize: 11, color: T.muted }}>{e.operating_hours} س</span>
                      )}
                    </span>
                  }
                />
              ))}
            </div>
            <div style={{ fontSize: 10, color: T.faint, marginTop: 8 }}>
              عدّادات الوقود/DEF وأكواد الأعطال (DTC) غير متاحة — لا تغذية telemetry للآلة (فجوة موثّقة).
            </div>
          </>
        )}
      </ExpandableCard>
    </FieldCabin>
  );
}
