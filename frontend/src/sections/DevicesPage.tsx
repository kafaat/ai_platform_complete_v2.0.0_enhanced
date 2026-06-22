// ═══════════════════════════════════════════════════════════════
// SAHOOL — DevicesPage (أجهزة IoT — مربوطة ببيانات حيّة)
// قائمة أجهزة حيّة من useDevices (/api/v1/devices) مع مؤشّر صحّة online/offline،
// قياسات الجهاز المحدّد من useDeviceTelemetry، وتسجيل جهاز عبر useRegisterDevice
// (محكوم بالدور — RBAC: المُشاهِد لا يُسجّل). حالات موحّدة (StateViews). لا تلفيق:
// لا قراءات مُخترعة — عند الخطأ/الفراغ تُعرض حالة صادقة. 503 عند تعطيل قاعدة البيانات.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  Cpu, Wifi, WifiOff, Plus, RefreshCw, Loader2, Activity,
  Droplets, CloudSun, Gauge, Camera, ToggleRight, HardDrive,
} from 'lucide-react';
import { useDevices, useDeviceTelemetry, useRegisterDevice, useFieldSoilMoisture } from '../hooks/useApi';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';
import { toastStore } from '../services/websocket';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import type { Device, DeviceType, TelemetryPoint } from '../services/api';
import { asApiError } from '../services/api';
import { Card, Button, Pill, SectionLabel } from '../components/ds/atoms';
import { Input, Select } from '../components/ds/forms';
import { DataTable, type Column } from '../components/ds/table';
import { T } from '../components/ds/tokens';

// تكوين الأنواع: تسمية عربيّة + أيقونة + لون لكل نوع جهاز مدعوم.
const TYPE_CONFIG: Record<DeviceType, { label: string; icon: typeof Cpu; color: string }> = {
  soil_moisture:   { label: 'رطوبة التربة', icon: Droplets,    color: '#3b82f6' },
  weather_station: { label: 'محطّة طقس',     icon: CloudSun,    color: '#f59e0b' },
  water_meter:     { label: 'عدّاد مياه',    icon: Gauge,       color: '#0ea5e9' },
  camera:          { label: 'كاميرا',        icon: Camera,      color: '#a855f7' },
  actuator:        { label: 'مُشغِّل',        icon: ToggleRight, color: '#16a34a' },
  other:           { label: 'أخرى',          icon: HardDrive,   color: '#6b7280' },
};

const TYPE_ORDER: DeviceType[] = [
  'soil_moisture', 'weather_station', 'water_meter', 'camera', 'actuator', 'other',
];

function typeOf(t: string) {
  return TYPE_CONFIG[(t as DeviceType)] ?? TYPE_CONFIG.other;
}

// "آخر ظهور" بصياغة عربيّة نسبيّة صادقة (لا قيمة مُختلقة عند الغياب).
function lastSeenAr(iso: string | null): string {
  if (!iso) return 'لم يُسجَّل بعد';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '—';
  const diffMin = Math.round((Date.now() - t) / 60_000);
  if (diffMin < 1) return 'الآن';
  if (diffMin < 60) return `قبل ${diffMin} دقيقة`;
  const h = Math.round(diffMin / 60);
  if (h < 24) return `قبل ${h} ساعة`;
  const d = Math.round(h / 24);
  return `قبل ${d} يوم`;
}

function fmtTime(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  return new Date(t).toLocaleString('en-GB', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

// ── مؤشّر الصحّة: نقطة خضراء (متصل) / محايدة (غير متصل) ──────────────
function HealthDot({ online }: { online: boolean }) {
  return (
    <Pill tone={online ? 'ok' : 'neutral'}>
      <span className="inline-flex items-center gap-1">
        {online
          ? <span className="inline-flex items-center gap-1"><Wifi className="w-3 h-3" /> متصل</span>
          : <span className="inline-flex items-center gap-1"><WifiOff className="w-3 h-3" /> غير متصل</span>}
      </span>
    </Pill>
  );
}

// ── بطاقة رطوبة التربة للحقل (أحدث قراءة حيّة من أجهزة الحقل) ──────────
// تستهلك /api/v1/fields/{id}/soil-moisture — القراءة هي ما يُغذّي محرّك التنبيهات
// وتوصية الريّ فعليّاً (لا تلفيق: reading=null ⇒ حالة صادقة «لا قراءة بعد»).
function FieldSoilMoistureCard({ fieldId }: { fieldId: string }) {
  const { data, isLoading, isError } = useFieldSoilMoisture(fieldId);

  const wrap = (body: React.ReactNode) => (
    <Card pad={12} style={{ background: T.card2 }}>
      <div className="flex items-center gap-1.5 mb-1.5">
        <Droplets className="w-3.5 h-3.5" style={{ color: T.info }} />
        <span className="text-[11px]" style={{ color: T.muted }}>رطوبة تربة الحقل (تُغذّي التنبيهات والريّ)</span>
        <span className="text-[10px] mr-auto" style={{ color: T.faint }}>{fieldId}</span>
      </div>
      {body}
    </Card>
  );

  if (isLoading) {
    return wrap(<span className="text-xs" style={{ color: T.muted }}>جارٍ التحميل…</span>);
  }
  if (isError) {
    return wrap(<span className="text-xs" style={{ color: T.warn }}>تعذّر جلب رطوبة التربة.</span>);
  }
  const reading = data?.reading ?? null;
  if (!reading) {
    return wrap(
      <span className="text-xs" style={{ color: T.muted }}>لا قراءة رطوبة تربة بعد لهذا الحقل.</span>,
    );
  }
  return wrap(
    <div className="flex items-baseline gap-2">
      <span className="text-2xl font-bold" style={{ color: T.info }}>
        {reading.soil_moisture_pct.toFixed(0)}
        <span className="text-sm font-normal" style={{ color: T.muted }}> {reading.unit ?? '٪'}</span>
      </span>
      <span className="text-[11px] mr-auto" style={{ color: T.muted }}>آخر قراءة: {fmtTime(reading.recorded_at)}</span>
    </div>,
  );
}

// ── قياسات الجهاز المحدّد ────────────────────────────────────────
function DeviceTelemetry({ device }: { device: Device }) {
  const { data, isLoading, isError, error, refetch } = useDeviceTelemetry(device.device_id, 20);

  if (isLoading) return <LoadingState message="جارٍ تحميل القياسات…" />;
  if (isError) {
    const status = asApiError(error).response?.status;
    const detail = status === 503
      ? 'خدمة الأجهزة غير متاحة حاليّاً (قاعدة البيانات معطّلة).'
      : status === 403
        ? 'لا تملك صلاحية عرض القياسات (device:view).'
        : 'تعذّر الاتصال بخدمة الأجهزة.';
    return <ErrorState title="تعذّر تحميل القياسات" detail={detail} onRetry={() => refetch()} />;
  }

  const points: TelemetryPoint[] = data ?? [];
  if (points.length === 0) {
    return (
      <EmptyState
        icon={<Activity className="w-8 h-8" />}
        title="لا توجد قياسات بعد"
        hint="لم يُسجِّل هذا الجهاز أي قراءات حتى الآن."
      />
    );
  }

  // سلسلة بسيطة شبيهة بالـsparkline لأحدث نوع استشعار (بيانات حقيقيّة فقط).
  const latestType = points[0]?.sensor_type;
  const series = points.filter(p => p.sensor_type === latestType).slice(0, 24).reverse();
  const vals = series.map(p => p.value);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;

  type TelemetryRow = TelemetryPoint & Record<string, unknown>;
  const columns: Column<TelemetryRow>[] = [
    { key: 'sensor_type', label: 'المستشعر', render: (p) => <span style={{ color: T.brownSoft }}>{p.sensor_type}</span> },
    {
      key: 'value', label: 'القيمة',
      render: (p) => (
        <span className="font-semibold" style={{ color: T.green }}>
          {p.value}{p.unit ? <span className="font-normal" style={{ color: T.muted }}> {p.unit}</span> : null}
        </span>
      ),
    },
    {
      key: 'recorded_at', label: 'الوقت',
      render: (p) => <span className="text-xs" style={{ color: T.muted }}>{fmtTime(p.recorded_at)}</span>,
    },
  ];

  return (
    <div className="space-y-3">
      {/* sparkline-ish bars لأحدث نوع استشعار */}
      {series.length > 1 && (
        <Card pad={12} style={{ background: T.card2 }}>
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px]" style={{ color: T.muted }}>{latestType}</span>
            <span className="text-[11px]" style={{ color: T.muted }}>
              {series[series.length - 1].value}
              {series[series.length - 1].unit ? ` ${series[series.length - 1].unit}` : ''}
            </span>
          </div>
          <div className="flex items-end gap-0.5 h-12" aria-hidden="true">
            {series.map((p, i) => (
              <div
                key={i}
                className="flex-1 rounded-sm"
                style={{ height: `${8 + ((p.value - min) / span) * 92}%`, background: T.green, opacity: 0.7 }}
                title={`${p.value}${p.unit ? ' ' + p.unit : ''} · ${fmtTime(p.recorded_at)}`}
              />
            ))}
          </div>
        </Card>
      )}

      {/* جدول القياسات الحديثة */}
      <DataTable<TelemetryRow>
        columns={columns}
        rows={points as TelemetryRow[]}
        rowKey={(_p, i) => String(i)}
      />
    </div>
  );
}

// ── نموذج تسجيل جهاز (يظهر فقط لمن يملك صلاحيّة التعديل) ───────────
function RegisterDeviceForm() {
  const reg = useRegisterDevice();
  const [name, setName] = useState('');
  const [type, setType] = useState<DeviceType>('soil_moisture');
  const [fieldId, setFieldId] = useState('');
  const [firmware, setFirmware] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await reg.mutateAsync({
        name: name.trim(),
        type,
        ...(fieldId.trim() ? { field_id: fieldId.trim() } : {}),
        ...(firmware.trim() ? { firmware_version: firmware.trim() } : {}),
      });
      toastStore.add('success', '✅ تم تسجيل الجهاز', '');
      setName(''); setFieldId(''); setFirmware('');
    } catch (err) {
      const status = asApiError(err).response?.status;
      const detail = status === 503
        ? 'خدمة الأجهزة غير متاحة حاليّاً (قاعدة البيانات معطّلة).'
        : status === 403
          ? 'لا تملك صلاحية تسجيل الأجهزة (device:manage).'
          : 'فشل الاتصال بالخادم — لم يُسجَّل الجهاز.';
      toastStore.add('error', '⚠️ تعذّر تسجيل الجهاز', detail);
    }
  };

  return (
    <Card>
      <form onSubmit={submit} className="space-y-3">
        <SectionLabel>
          <span className="inline-flex items-center gap-2">
            <Plus className="w-4 h-4" style={{ color: T.green }} />
            تسجيل جهاز جديد
          </span>
        </SectionLabel>

        <Input
          label="اسم الجهاز" required
          value={name} onChange={v => setName(v)}
          placeholder="مثال: مستشعر رطوبة وادي سبأ"
        />

        <div className="grid grid-cols-2 gap-3">
          <Select<DeviceType>
            label="النوع"
            value={type} onChange={v => setType(v)}
            options={TYPE_ORDER.map(t => ({ value: t, label: TYPE_CONFIG[t].label }))}
          />
          <Input
            label="معرّف الحقل (اختياري)"
            value={fieldId} onChange={v => setFieldId(v)}
            placeholder="field_01"
          />
        </div>

        <Input
          label="إصدار البرنامج (اختياري)"
          value={firmware} onChange={v => setFirmware(v)}
          placeholder="v1.0.0"
        />

        <Button
          disabled={reg.isPending || !name.trim()}
          onClick={() => { void submit({ preventDefault: () => {} } as React.FormEvent); }}
        >
          {reg.isPending
            ? <span className="inline-flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> جارٍ التسجيل…</span>
            : <span className="inline-flex items-center justify-center gap-2"><Plus className="w-4 h-4" /> تسجيل الجهاز</span>}
        </Button>
      </form>
    </Card>
  );
}

export default function DevicesPage() {
  const { user } = useAuthStore();
  const mutateAllowed = canMutate(user?.role);
  const { data, isLoading, isError, error, refetch, isFetching } = useDevices();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const devices: Device[] = data ?? [];
  const selected = devices.find(d => d.device_id === selectedId) ?? null;
  const onlineCount = devices.filter(d => d.online).length;

  return (
    <div className="space-y-4 max-w-7xl mx-auto" dir="rtl">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold" style={{ color: T.ink }}>أجهزة IoT</h2>
          <p className="text-sm" style={{ color: T.muted }}>أجهزة الاستشعار الميدانيّة وقياساتها الحيّة</p>
        </div>
        <div className="flex items-center gap-2">
          {!isLoading && !isError && (
            <Pill tone="ok" icon={<Wifi className="w-3 h-3" />}>
              {onlineCount}/{devices.length} متصل
            </Pill>
          )}
          <Button
            tone="gold" full={false}
            disabled={isFetching}
            onClick={() => refetch()}
            style={{ padding: '7px 12px', fontSize: 13 }}
          >
            <span className="inline-flex items-center gap-1.5">
              <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} /> تحديث
            </span>
          </Button>
        </div>
      </div>

      {isLoading ? (
        <LoadingState message="جارٍ تحميل الأجهزة…" />
      ) : isError ? (
        (() => {
          const status = asApiError(error).response?.status;
          const detail = status === 503
            ? 'خدمة الأجهزة غير متاحة حاليّاً (قاعدة البيانات معطّلة).'
            : status === 403
              ? 'لا تملك صلاحية عرض الأجهزة (device:view).'
              : 'تعذّر الاتصال بخدمة الأجهزة.';
          return <ErrorState title="تعذّر تحميل الأجهزة" detail={detail} onRetry={() => refetch()} />;
        })()
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* قائمة/شبكة الأجهزة */}
          <div className="lg:col-span-2 space-y-3">
            {devices.length === 0 ? (
              <EmptyState
                icon={<Cpu className="w-8 h-8" />}
                title="لا توجد أجهزة مُسجّلة"
                hint={mutateAllowed ? 'سجّل أوّل جهاز من النموذج جانباً.' : 'لم يُسجَّل أي جهاز بعد.'}
              />
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {devices.map(d => {
                  const cfg = typeOf(d.type);
                  const Icon = cfg.icon;
                  const active = d.device_id === selectedId;
                  return (
                    <Card
                      key={d.device_id}
                      pad={12}
                      onClick={() => setSelectedId(d.device_id)}
                      style={{
                        textAlign: 'right',
                        background: active ? T.card2 : T.card,
                        border: `1px solid ${active ? T.green : T.line}`,
                      }}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                            style={{ background: `${cfg.color}22` }}>
                            <Icon className="w-4 h-4" style={{ color: cfg.color }} />
                          </span>
                          <div className="min-w-0">
                            <div className="text-sm font-semibold truncate" style={{ color: T.ink }}>{d.name}</div>
                            <div className="text-[11px]" style={{ color: T.muted }}>{cfg.label}</div>
                          </div>
                        </div>
                        <HealthDot online={d.online} />
                      </div>
                      <div className="mt-2 flex items-center justify-between text-[11px]" style={{ color: T.muted }}>
                        <span>آخر ظهور: {lastSeenAr(d.last_seen_at)}</span>
                        {d.field_id && <span style={{ color: T.faint }}>{d.field_id}</span>}
                      </div>
                    </Card>
                  );
                })}
              </div>
            )}

            {/* قياسات الجهاز المحدّد */}
            {selected && (
              <Card>
                <div className="flex items-center gap-2 mb-3">
                  <Activity className="w-4 h-4" style={{ color: T.green }} />
                  <span className="text-sm font-semibold" style={{ color: T.ink }}>قياسات {selected.name}</span>
                  <span className="text-[10px] mr-auto" style={{ color: T.muted }}>
                    {selected.firmware_version ? `إصدار ${selected.firmware_version}` : ''}
                  </span>
                </div>
                {selected.field_id && (
                  <div className="mb-3">
                    <FieldSoilMoistureCard fieldId={selected.field_id} />
                  </div>
                )}
                <DeviceTelemetry device={selected} />
              </Card>
            )}
          </div>

          {/* الجانب: تسجيل جهاز (محكوم بالدور) */}
          <div className="space-y-3">
            {mutateAllowed ? (
              <RegisterDeviceForm />
            ) : (
              <Card>
                <div className="text-center text-xs" style={{ color: T.muted }}>
                  دورك الحاليّ للقراءة فقط — لا يمكن تسجيل الأجهزة.
                </div>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
