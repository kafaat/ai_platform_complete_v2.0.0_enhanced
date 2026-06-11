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
import { useDevices, useDeviceTelemetry, useRegisterDevice } from '../hooks/useApi';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';
import { toastStore } from '../services/websocket';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import type { Device, DeviceType, TelemetryPoint } from '../services/api';

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

// ── مؤشّر الصحّة: نقطة خضراء (متصل) / رماديّة (غير متصل) ──────────────
function HealthDot({ online }: { online: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`w-2.5 h-2.5 rounded-full ${online ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'}`}
        aria-hidden="true"
      />
      <span className={`text-[11px] ${online ? 'text-emerald-400' : 'text-slate-500'}`}>
        {online
          ? <span className="inline-flex items-center gap-1"><Wifi className="w-3 h-3" /> متصل</span>
          : <span className="inline-flex items-center gap-1"><WifiOff className="w-3 h-3" /> غير متصل</span>}
      </span>
    </span>
  );
}

// ── قياسات الجهاز المحدّد ────────────────────────────────────────
function DeviceTelemetry({ device }: { device: Device }) {
  const { data, isLoading, isError, error, refetch } = useDeviceTelemetry(device.device_id, 20);

  if (isLoading) return <LoadingState message="جارٍ تحميل القياسات…" />;
  if (isError) {
    const status = (error as any)?.response?.status;
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

  return (
    <div className="space-y-3">
      {/* sparkline-ish bars لأحدث نوع استشعار */}
      {series.length > 1 && (
        <div className="rounded-lg p-3 border" style={{ background: '#0f1117', borderColor: '#334155' }}>
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] text-slate-400">{latestType}</span>
            <span className="text-[11px] text-slate-500">
              {series[series.length - 1].value}
              {series[series.length - 1].unit ? ` ${series[series.length - 1].unit}` : ''}
            </span>
          </div>
          <div className="flex items-end gap-0.5 h-12" aria-hidden="true">
            {series.map((p, i) => (
              <div
                key={i}
                className="flex-1 rounded-sm bg-emerald-500/70"
                style={{ height: `${8 + ((p.value - min) / span) * 92}%` }}
                title={`${p.value}${p.unit ? ' ' + p.unit : ''} · ${fmtTime(p.recorded_at)}`}
              />
            ))}
          </div>
        </div>
      )}

      {/* جدول القياسات الحديثة */}
      <div className="rounded-lg border overflow-hidden" style={{ borderColor: '#334155' }}>
        <table className="w-full text-sm" dir="rtl">
          <thead>
            <tr className="text-[11px] text-slate-400" style={{ background: '#1e293b' }}>
              <th className="text-right font-medium px-3 py-2">المستشعر</th>
              <th className="text-right font-medium px-3 py-2">القيمة</th>
              <th className="text-right font-medium px-3 py-2">الوقت</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p, i) => (
              <tr key={i} className="border-t" style={{ borderColor: '#1e293b' }}>
                <td className="px-3 py-2 text-slate-300">{p.sensor_type}</td>
                <td className="px-3 py-2 font-semibold text-emerald-400">
                  {p.value}{p.unit ? <span className="text-slate-500 font-normal"> {p.unit}</span> : null}
                </td>
                <td className="px-3 py-2 text-slate-500 text-xs">{fmtTime(p.recorded_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
      const status = (err as any)?.response?.status;
      const detail = status === 503
        ? 'خدمة الأجهزة غير متاحة حاليّاً (قاعدة البيانات معطّلة).'
        : status === 403
          ? 'لا تملك صلاحية تسجيل الأجهزة (device:manage).'
          : 'فشل الاتصال بالخادم — لم يُسجَّل الجهاز.';
      toastStore.add('error', '⚠️ تعذّر تسجيل الجهاز', detail);
    }
  };

  const inputCls = 'w-full px-3 py-2 rounded-lg text-sm';
  const inputStyle = { background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' } as const;

  return (
    <form onSubmit={submit} className="rounded-xl p-4 border space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
      <div className="flex items-center gap-2">
        <Plus className="w-4 h-4 text-emerald-400" />
        <span className="text-sm font-semibold text-slate-200">تسجيل جهاز جديد</span>
      </div>

      <div>
        <label className="block text-xs text-slate-400 mb-1">اسم الجهاز *</label>
        <input value={name} onChange={e => setName(e.target.value)} className={inputCls} style={inputStyle}
          placeholder="مثال: مستشعر رطوبة وادي سبأ" />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">النوع</label>
          <select value={type} onChange={e => setType(e.target.value as DeviceType)} className={inputCls} style={inputStyle}>
            {TYPE_ORDER.map(t => <option key={t} value={t}>{TYPE_CONFIG[t].label}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">معرّف الحقل (اختياري)</label>
          <input value={fieldId} onChange={e => setFieldId(e.target.value)} className={inputCls} style={inputStyle}
            placeholder="field_01" />
        </div>
      </div>

      <div>
        <label className="block text-xs text-slate-400 mb-1">إصدار البرنامج (اختياري)</label>
        <input value={firmware} onChange={e => setFirmware(e.target.value)} className={inputCls} style={inputStyle}
          placeholder="v1.0.0" />
      </div>

      <button type="submit" disabled={reg.isPending || !name.trim()}
        className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50"
        style={{ background: reg.isPending ? '#15803d' : '#16a34a' }}>
        {reg.isPending
          ? <><Loader2 className="w-4 h-4 animate-spin" /> جارٍ التسجيل…</>
          : <><Plus className="w-4 h-4" /> تسجيل الجهاز</>}
      </button>
    </form>
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
          <h2 className="text-xl font-bold text-slate-100">أجهزة IoT</h2>
          <p className="text-sm text-slate-400">أجهزة الاستشعار الميدانيّة وقياساتها الحيّة</p>
        </div>
        <div className="flex items-center gap-2">
          {!isLoading && !isError && (
            <span className="flex items-center gap-1 px-2 py-1 rounded-full text-[11px] bg-emerald-950 text-emerald-400 border border-emerald-900">
              <Wifi className="w-3 h-3" /> {onlineCount}/{devices.length} متصل
            </span>
          )}
          <button onClick={() => refetch()} disabled={isFetching}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-200 border border-slate-700 hover:border-emerald-700 disabled:opacity-50">
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} /> تحديث
          </button>
        </div>
      </div>

      {isLoading ? (
        <LoadingState message="جارٍ تحميل الأجهزة…" />
      ) : isError ? (
        (() => {
          const status = (error as any)?.response?.status;
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
                    <button key={d.device_id} onClick={() => setSelectedId(d.device_id)}
                      className="text-right rounded-xl p-3 border transition-all hover:border-emerald-700"
                      style={{
                        background: active ? '#1e3a1e' : '#1e293b',
                        borderColor: active ? '#16a34a' : '#334155',
                      }}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                            style={{ background: `${cfg.color}22` }}>
                            <Icon className="w-4 h-4" style={{ color: cfg.color }} />
                          </span>
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-slate-100 truncate">{d.name}</div>
                            <div className="text-[11px] text-slate-500">{cfg.label}</div>
                          </div>
                        </div>
                        <HealthDot online={d.online} />
                      </div>
                      <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
                        <span>آخر ظهور: {lastSeenAr(d.last_seen_at)}</span>
                        {d.field_id && <span className="text-slate-600">{d.field_id}</span>}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}

            {/* قياسات الجهاز المحدّد */}
            {selected && (
              <div className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }}>
                <div className="flex items-center gap-2 mb-3">
                  <Activity className="w-4 h-4 text-emerald-400" />
                  <span className="text-sm font-semibold text-slate-200">قياسات {selected.name}</span>
                  <span className="text-[10px] text-slate-500 mr-auto">
                    {selected.firmware_version ? `إصدار ${selected.firmware_version}` : ''}
                  </span>
                </div>
                <DeviceTelemetry device={selected} />
              </div>
            )}
          </div>

          {/* الجانب: تسجيل جهاز (محكوم بالدور) */}
          <div className="space-y-3">
            {mutateAllowed ? (
              <RegisterDeviceForm />
            ) : (
              <div className="rounded-xl p-4 border text-center text-xs text-slate-500" style={{ background: '#1e293b', borderColor: '#334155' }}>
                دورك الحاليّ للقراءة فقط — لا يمكن تسجيل الأجهزة.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
