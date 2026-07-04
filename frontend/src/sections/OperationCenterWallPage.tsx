// ═══════════════════════════════════════════════════════════════
// SAHOOL — OperationCenterWallPage (جدار مركز العمليّات)
// شاشة قيادة كبيرة (wall display) للشركات/الجهات: لوحة بلاطات تجمع نبض التشغيل
// في مكان واحد — خريطة الحقول، شريط تنبيهات مُجمَّع بالخطورة، صحّة الأسطول، لقطة
// طقس، حالة الريّ (صمّامات/جداول)، وآخر القرارات المُدامة.
//
// المصدر الأساسيّ: GET /api/v1/operations/summary (خلف FEATURE_OPERATIONS_WALL).
// أفضل-جهد: قد يكون العلم مُطفأً ⇒ null، فترتدّ كلّ بلاطة لنقطتها المنفصلة الحيّة.
// التلخيص — حين يتوفّر — يُثري بعض البلاطات بأرقام مُجمَّعة خادميّاً، ولا يُلغي
// مصادرها المنفصلة (تظلّ المصدر الحاسم: الخريطة من /fields، الأسطول من
// /devices/fleet-health، إلخ).
//
// الصدق: كلّ بلاطة لها loading/empty/error **مستقلّ** — فشل بلاطة لا يكسر الجدار،
// ولا أرقام مُختلَقة (البلاطة بلا بيانات تعرض «لا تتوفّر»). تحديث دوريّ معقول عبر
// react-query refetchInterval (مناسب لعرض جداريّ مستمرّ). تصميم عالي التباين.
// ═══════════════════════════════════════════════════════════════
import { useMemo } from 'react';
import { MapContainer, TileLayer, Polygon, CircleMarker, Tooltip } from 'react-leaflet';
import {
  MonitorPlay, Map as MapIcon, Bell, Cpu, CloudRain, Droplets, GitBranch,
  AlertTriangle, Loader2, Thermometer, Wind, Waves, Activity, RefreshCw,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import '../lib/leafletSetup'; // CSS + أيقونات Leaflet (side-effect حاسم للتصيير)
import { geomToPolygon, collectFieldBoundsPoints, fieldRepresentativePoint } from '../lib/geo';
import {
  useAlerts, useFleetHealth, useWeatherForecast,
  useValves, useSchedules, useDecisionRecords, useOperationsSummary,
} from '../hooks/useApi';
import { useSelectedField } from '../hooks/useSelectedField';
import type { AlertRecord, OperationsSummary } from '../services/api';

// تحديث دوريّ معقول لعرض جداريّ مستمرّ — متباعد كي لا يُثقِل البوّابة.
const REFRESH = {
  alerts:   90_000,
  fleet:    90_000,
  weather:  10 * 60_000,
  valves:   60_000,
  schedules:120_000,
  decisions:120_000,
  summary:  90_000,
} as const;

const YEMEN_CENTER: [number, number] = [15.0, 44.0];
const BASEMAP_SAT =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const FIELD_COLOR = '#34d399';

// ألوان خطورة عالية التباين (مناسبة لشاشة جدار).
const SEVERITY = {
  critical: { bg: '#2a0d0d', border: '#dc2626', color: '#fca5a5', label: 'حرِجة' },
  warning:  { bg: '#2a1a00', border: '#f59e0b', color: '#fcd34d', label: 'تحذير' },
  info:     { bg: '#0a1f2e', border: '#0ea5e9', color: '#7dd3fc', label: 'معلومة' },
} as const;
type SeverityKey = keyof typeof SEVERITY;

// ── غلاف بلاطة موحّد: عنوان + أيقونة + جسم. عالي التباين، حدّ واضح ──
function Tile({
  icon: Icon, title, hint, children, className = '',
}: {
  icon: LucideIcon; title: string; hint?: string; children: React.ReactNode; className?: string;
}) {
  return (
    <section
      className={`rounded-2xl border p-4 flex flex-col ${className}`}
      style={{ background: '#10151f', borderColor: '#25303f' }}
    >
      <header className="flex items-center gap-2 mb-3 flex-shrink-0">
        <Icon className="w-5 h-5 text-emerald-400" aria-hidden="true" />
        <h2 className="text-base font-bold text-slate-100">{title}</h2>
        {hint && <span className="text-[11px] text-slate-500 mr-auto">{hint}</span>}
      </header>
      <div className="flex-1 min-h-0">{children}</div>
    </section>
  );
}

// حالات البلاطة المستقلّة (loading/empty/error) — مدمجة عالية التباين داخل البلاطة.
function TileLoading({ message = 'جارٍ التحميل…' }: { message?: string }) {
  return (
    <div className="flex items-center justify-center h-full min-h-[80px] text-slate-500" role="status" aria-busy="true">
      <Loader2 className="w-5 h-5 animate-spin ml-2" aria-hidden="true" />
      <span className="text-sm">{message}</span>
    </div>
  );
}
function TileError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[80px] text-center" role="alert">
      <AlertTriangle className="w-6 h-6 text-red-400 mb-1" aria-hidden="true" />
      <p className="text-sm text-slate-300">{message}</p>
      {onRetry && (
        <button onClick={onRetry}
          className="mt-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs text-slate-200 hover:border-emerald-600"
          style={{ borderColor: '#334155' }}>
          <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" /> إعادة المحاولة
        </button>
      )}
    </div>
  );
}
function TileEmpty({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center h-full min-h-[80px] text-center" role="status">
      <p className="text-sm text-slate-500">{message}</p>
    </div>
  );
}

// مقياس كبير مفرد (للبلاطات العدديّة) — رقم عالي التباين + تسمية.
function BigStat({ value, label, color = '#e2e8f0' }: { value: string; label: string; color?: string }) {
  return (
    <div className="text-center px-2">
      <div className="text-3xl font-extrabold leading-none" style={{ color }}>{value}</div>
      <div className="text-[11px] text-slate-400 mt-1">{label}</div>
    </div>
  );
}

// ════════════════════ بلاطة الخريطة ════════════════════
function MapTile() {
  const { options: fields, isLoading, isError, refetch, fieldId: activeFieldId, setFieldId } = useSelectedField();
  const points = useMemo(() => collectFieldBoundsPoints(fields), [fields]);
  const center = useMemo<[number, number]>(() => {
    if (!points.length) return YEMEN_CENTER;
    const [sLat, sLng] = points.reduce(([a, b], [la, ln]) => [a + la, b + ln], [0, 0]);
    return [sLat / points.length, sLng / points.length];
  }, [points]);

  return (
    <Tile icon={MapIcon} title="خريطة الحقول" hint={fields.length ? `${fields.length} حقل` : undefined}
      className="lg:col-span-2 lg:row-span-2">
      {isLoading ? <TileLoading message="جارٍ تحميل الحقول…" />
        : isError ? <TileError message="تعذّر تحميل الحقول" onRetry={() => refetch()} />
        : !fields.length ? <TileEmpty message="لا حقول مُسجّلة — لا تتوفّر بيانات للخريطة." />
        : (
          <div style={{ height: '100%', minHeight: 320, borderRadius: 12, overflow: 'hidden' }}>
            <MapContainer center={center} zoom={11} style={{ height: '100%', width: '100%' }}>
              <TileLayer url={BASEMAP_SAT} attribution="Tiles &copy; Esri — World Imagery" />
              {fields.map((f) => {
                const poly = geomToPolygon(f.geometry);
                const label = `${f.name}${f.crop && f.crop !== '—' ? ` · ${f.crop}` : ''}`;
                const isActive = f.id === activeFieldId;
                const stroke = isActive ? '#facc15' : FIELD_COLOR;
                const fill = isActive ? '#facc15' : FIELD_COLOR;
                if (poly && poly.length >= 3) {
                  return (
                    <Polygon key={f.id} positions={poly}
                      eventHandlers={{ click: () => setFieldId(f.id) }}
                      pathOptions={{ color: stroke, weight: isActive ? 3 : 1.5, fillOpacity: isActive ? 0.28 : 0.18 }}>
                      <Tooltip>{label}</Tooltip>
                    </Polygon>
                  );
                }
                const pt = fieldRepresentativePoint(f);
                if (!pt) return null;
                return (
                  <CircleMarker key={f.id} center={pt} radius={isActive ? 8 : 6}
                    eventHandlers={{ click: () => setFieldId(f.id) }}
                    pathOptions={{ color: stroke, fillColor: fill, fillOpacity: 0.85, weight: isActive ? 2.5 : 1.5 }}>
                    <Tooltip>{label}</Tooltip>
                  </CircleMarker>
                );
              })}
            </MapContainer>
          </div>
        )}
    </Tile>
  );
}

// ════════════════════ شريط تنبيهات مُجمَّع بالخطورة ════════════════════
function normalizeSeverity(s: string): SeverityKey {
  const k = (s || '').toLowerCase();
  if (k === 'critical' || k === 'warning' || k === 'info') return k;
  return 'info';
}

function AlertsTile() {
  const { data, isLoading, isError, refetch } = useAlerts({ status: 'active' });
  const alerts: AlertRecord[] = Array.isArray(data) ? data : [];

  const counts = useMemo(() => {
    const c: Record<SeverityKey, number> = { critical: 0, warning: 0, info: 0 };
    for (const a of alerts) c[normalizeSeverity(String(a.severity))]++;
    return c;
  }, [alerts]);

  return (
    <Tile icon={Bell} title="التنبيهات النشطة" hint={alerts.length ? `${alerts.length} إجماليّ` : undefined}>
      {isLoading ? <TileLoading message="جارٍ جلب التنبيهات…" />
        : isError ? <TileError message="تعذّر جلب التنبيهات" onRetry={() => refetch()} />
        : !alerts.length ? <TileEmpty message="لا تنبيهات نشطة الآن." />
        : (
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              {(['critical', 'warning', 'info'] as SeverityKey[]).map((sev) => {
                const s = SEVERITY[sev];
                return (
                  <div key={sev} className="rounded-xl border py-2.5 text-center"
                    style={{ background: s.bg, borderColor: s.border }}>
                    <div className="text-2xl font-extrabold" style={{ color: s.color }}>{counts[sev]}</div>
                    <div className="text-[11px] mt-0.5" style={{ color: s.color }}>{s.label}</div>
                  </div>
                );
              })}
            </div>
            {/* أحدث التنبيهات الحرجة/التحذيريّة (الأهمّ أوّلاً) */}
            <ul className="space-y-1.5 max-h-40 overflow-auto">
              {alerts
                .slice()
                .sort((a, b) => {
                  const rank = { critical: 0, warning: 1, info: 2 } as const;
                  return rank[normalizeSeverity(String(a.severity))] - rank[normalizeSeverity(String(b.severity))];
                })
                .slice(0, 6)
                .map((a) => {
                  const s = SEVERITY[normalizeSeverity(String(a.severity))];
                  return (
                    <li key={a.alert_id} className="flex items-center gap-2 rounded-lg px-2 py-1.5"
                      style={{ background: '#0d1117', borderRight: `3px solid ${s.border}` }}>
                      <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: s.border }} />
                      <span className="text-sm text-slate-200 truncate">
                        {a.title_ar || a.message_ar || a.alert_type || 'تنبيه'}
                      </span>
                    </li>
                  );
                })}
            </ul>
          </div>
        )}
    </Tile>
  );
}

// ════════════════════ بلاطة المعدّات/الأسطول (صحّة الأجهزة) ════════════════════
function FleetTile() {
  const { data, isLoading, isError, refetch } = useFleetHealth({ refetchInterval: REFRESH.fleet });

  return (
    <Tile icon={Cpu} title="المعدّات والأجهزة" hint={data ? data.fleet_status_ar.slice(0, 1) : undefined}>
      {isLoading ? <TileLoading message="جارٍ فحص الأسطول…" />
        : isError ? <TileError message="تعذّر جلب صحّة الأسطول" onRetry={() => refetch()} />
        : !data || data.total_devices === 0 ? <TileEmpty message="لا أجهزة مُسجّلة — لا تتوفّر بيانات أسطول." />
        : (
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              <BigStat value={String(data.online)} label="متّصل" color="#4ade80" />
              <BigStat value={String(data.silent)} label="صامت" color={data.silent ? '#fcd34d' : '#94a3b8'} />
              <BigStat value={String(data.critical_silent)} label="حرج صامت" color={data.critical_silent ? '#fca5a5' : '#94a3b8'} />
            </div>
            <div className="text-[12px] text-slate-300 rounded-lg px-2.5 py-1.5"
              style={{ background: '#0d1117', border: '1px solid #25303f' }}>
              {data.fleet_status_ar || `${data.total_devices} جهاز`}
            </div>
            {data.silent_devices.length > 0 && (
              <ul className="space-y-1 max-h-28 overflow-auto">
                {data.silent_devices.slice(0, 5).map((d) => (
                  <li key={d.device_id} className="flex items-center gap-2 text-[12px] text-slate-300">
                    <span className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                      style={{ background: d.criticality === 'critical' ? '#dc2626' : '#f59e0b' }} />
                    <span className="truncate">{d.name}</span>
                    <span className="text-slate-500 mr-auto truncate">{d.detail_ar}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
    </Tile>
  );
}

// ════════════════════ بلاطة الطقس (لقطة) ════════════════════
// شكل ردّ /weather/forecast غير مُنمَّط في الـhook ⇒ قراءة دفاعيّة (لا any).
interface WeatherSnapshot { tmean?: number; humidity_pct?: number; wind_speed_kmh?: number }
function readWeatherCurrent(data: unknown): WeatherSnapshot | null {
  const cur = (data as { current?: unknown } | null | undefined)?.current;
  if (cur && typeof cur === 'object') return cur as WeatherSnapshot;
  return null;
}

function WeatherTile() {
  const { data, isLoading, isError, refetch } = useWeatherForecast();
  const cur = readWeatherCurrent(data);
  const hasAny = cur && (cur.tmean != null || cur.humidity_pct != null || cur.wind_speed_kmh != null);

  return (
    <Tile icon={CloudRain} title="الطقس (لقطة)">
      {isLoading ? <TileLoading message="جارٍ جلب الطقس…" />
        : isError ? <TileError message="تعذّر جلب الطقس" onRetry={() => refetch()} />
        : !hasAny ? <TileEmpty message="لا تتوفّر لقطة طقس الآن." />
        : (
          <div className="grid grid-cols-3 gap-2">
            <div className="flex flex-col items-center gap-1">
              <Thermometer className="w-5 h-5 text-orange-400" aria-hidden="true" />
              <BigStat value={cur!.tmean != null ? `${cur!.tmean}°` : '—'} label="الحرارة" color="#fb923c" />
            </div>
            <div className="flex flex-col items-center gap-1">
              <Waves className="w-5 h-5 text-sky-400" aria-hidden="true" />
              <BigStat value={cur!.humidity_pct != null ? `${cur!.humidity_pct}%` : '—'} label="الرطوبة" color="#38bdf8" />
            </div>
            <div className="flex flex-col items-center gap-1">
              <Wind className="w-5 h-5 text-slate-400" aria-hidden="true" />
              <BigStat value={cur!.wind_speed_kmh != null ? `${cur!.wind_speed_kmh}` : '—'} label="كم/س" color="#cbd5e1" />
            </div>
          </div>
        )}
    </Tile>
  );
}

// ════════════════════ بلاطة الماء/الريّ (صمّامات/جداول) ════════════════════
function IrrigationTile() {
  const valves = useValves();
  const schedules = useSchedules();

  const valveList = Array.isArray(valves.data) ? valves.data : [];
  const scheduleList = Array.isArray(schedules.data) ? schedules.data : [];
  const open = valveList.filter((v) => v.status === 'open').length;
  const enabledSchedules = scheduleList.filter((s) => s.enabled).length;

  const isLoading = valves.isLoading || schedules.isLoading;
  // الخطأ الحاجب: فشل أيّ من المصدرين (كلاهما جزء من حالة الريّ).
  const isError = valves.isError || schedules.isError;
  const isEmpty = valveList.length === 0 && scheduleList.length === 0;

  return (
    <Tile icon={Droplets} title="الماء والريّ">
      {isLoading ? <TileLoading message="جارٍ جلب حالة الريّ…" />
        : isError ? <TileError message="تعذّر جلب الصمّامات/الجداول"
            onRetry={() => { valves.refetch(); schedules.refetch(); }} />
        : isEmpty ? <TileEmpty message="لا صمّامات ولا جداول — لا تتوفّر بيانات ريّ." />
        : (
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              <BigStat value={String(valveList.length)} label="صمّام" />
              <BigStat value={String(open)} label="مفتوح" color={open ? '#4ade80' : '#94a3b8'} />
              <BigStat value={String(enabledSchedules)} label="جدول فعّال" color="#38bdf8" />
            </div>
            <div className="text-[11px] text-slate-500">
              النيّة تُسجَّل فقط؛ التشغيل الفيزيائيّ يمرّ عبر موافقة بشريّة (HIL).
            </div>
          </div>
        )}
    </Tile>
  );
}

// ════════════════════ بلاطة القرارات (آخر القرارات المُدامة) ════════════════════
function DecisionsTile() {
  const { data, isLoading, isError, refetch } = useDecisionRecords(20);
  const decisions = data?.decisions ?? [];

  return (
    <Tile icon={GitBranch} title="آخر القرارات" hint={data?.count != null ? `${data.count} مُدام` : undefined}>
      {isLoading ? <TileLoading message="جارٍ جلب القرارات…" />
        : isError ? <TileError message="تعذّر جلب القرارات المُدامة" onRetry={() => refetch()} />
        : decisions.length === 0 ? <TileEmpty message="لا قرارات مُدامة بعد." />
        : (
          <ul className="space-y-1.5 max-h-44 overflow-auto">
            {decisions.slice(0, 7).map((d) => (
              <li key={d.decision_id} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[12px]"
                style={{ background: '#0d1117', border: '1px solid #25303f' }}>
                <Activity className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" aria-hidden="true" />
                <span className="text-slate-200 truncate">{d.decision_type || 'قرار'}</span>
                <span className="text-slate-500 mr-auto truncate">{d.region || 'غير محدّد'}</span>
              </li>
            ))}
          </ul>
        )}
    </Tile>
  );
}

// ── شريط مؤشّرات الأداء (KPI) — رأس قيادة كبير الأرقام (نمط شاشة 大屏) ──
// يقرأ التلخيص الخادميّ الموحّد (totals/alerts/irrigation) ويعرضه أرقاماً بارزة
// «بلمحة». الصدق: القسم «غير المتاح» (sections[x].status='unavailable') يعرض «—» لا
// صفراً مُلفَّقاً؛ شارة «جزئيّ» حين partial؛ ووقت التوليد. غياب التلخيص كلّه (العلم
// مُطفأ) ⇒ لا شريط (الترويسة تُعلن «مصادر منفصلة») — لا أرقام مُختلَقة.
function _fmtTime(iso?: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('ar', {
    hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit',
  });
}

function KpiCard({
  icon: Icon, label, value, unavailable, tone = 'default', sub,
}: {
  icon: LucideIcon; label: string; value: number | null; unavailable?: boolean;
  tone?: 'default' | 'alert'; sub?: string;
}) {
  const critical = tone === 'alert' && (value ?? 0) > 0;
  return (
    <div
      className="rounded-2xl border px-4 py-3 flex items-center gap-3"
      style={{
        background: critical ? '#2a0d0d' : '#10151f',
        borderColor: critical ? '#dc262655' : '#25303f',
      }}
    >
      <Icon
        className={`w-6 h-6 flex-shrink-0 ${critical ? 'text-red-400' : 'text-emerald-400'}`}
        aria-hidden="true"
      />
      <div className="min-w-0">
        <div className="text-[11px] text-slate-400 truncate">{label}</div>
        <div
          className={`text-2xl font-extrabold tabular-nums ${critical ? 'text-red-300' : 'text-slate-100'}`}
        >
          {unavailable || value == null ? '—' : value.toLocaleString('en-US')}
        </div>
        {sub && <div className="text-[10px] text-slate-500 truncate">{sub}</div>}
      </div>
    </div>
  );
}

function KpiStrip({ summary }: { summary: OperationsSummary | null | undefined }) {
  if (!summary) return null; // العلم مُطفأ / التلخيص غير منشور ⇒ لا شريط (لا تلفيق)
  const t = summary.totals ?? {};
  const sec = summary.sections ?? {};
  const un = (k: string) => sec[k]?.status === 'unavailable';
  const crit = summary.alerts?.by_severity?.critical ?? 0;
  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <KpiCard icon={MapIcon} label="الحقول" value={t.fields ?? 0} unavailable={un('fields')} />
        <KpiCard
          icon={Bell} label="تنبيهات نشطة" tone="alert"
          value={summary.alerts?.active_total ?? t.active_alerts ?? 0}
          unavailable={un('alerts')}
          sub={crit > 0 ? `${crit} حرِجة` : undefined}
        />
        <KpiCard
          icon={Cpu} label="أجهزة IoT" value={t.iot_devices ?? 0} unavailable={un('iot_devices')}
        />
        <KpiCard
          icon={Activity} label="المعدّات" value={t.equipment ?? 0} unavailable={un('equipment')}
        />
        <KpiCard
          icon={GitBranch} label="قرارات مُدامة"
          value={t.decision_records ?? 0} unavailable={un('decision_records')}
        />
        <KpiCard
          icon={Droplets} label="صمّامات الريّ"
          value={summary.irrigation?.valves ?? 0} unavailable={un('irrigation')}
          sub={
            summary.irrigation?.schedules != null
              ? `${summary.irrigation.schedules} جدول ريّ`
              : undefined
          }
        />
      </div>
      <div className="flex items-center gap-2 mt-2 text-[11px] text-slate-500 flex-wrap">
        {summary.generated_at && <span>آخر تحديث: {_fmtTime(summary.generated_at)}</span>}
        {summary.partial && (
          <span
            className="px-2 py-0.5 rounded-full"
            style={{ background: '#2a1a00', color: '#fcd34d', border: '1px solid #f59e0b55' }}
          >
            بيانات جزئيّة — بعض المصادر غير متاحة
          </span>
        )}
      </div>
    </div>
  );
}

// ════════════════════ الصفحة: جدار البلاطات ════════════════════
export default function OperationCenterWallPage() {
  // المصدر الأساسيّ الموحّد — أفضل-جهد. null ⇒ كلّ بلاطة على نقطتها المنفصلة (تدهور
  // رشيق). نعرض حالة المصدر بشفافيّة في الترويسة (موحّد / منفصل) بلا أرقام مُلفَّقة.
  const summary = useOperationsSummary({ refetchInterval: REFRESH.summary });
  const unified = !summary.isLoading && summary.data != null;

  return (
    <div className="space-y-4 max-w-[1600px] mx-auto" dir="rtl">
      <header className="flex items-center gap-3 flex-wrap">
        <MonitorPlay className="w-6 h-6 text-emerald-400" aria-hidden="true" />
        <h1 className="text-xl font-extrabold text-slate-100">جدار مركز العمليّات</h1>
        <span className="text-[12px] px-2 py-0.5 rounded-full"
          style={{
            background: unified ? '#0c2a1a' : '#1e293b',
            color: unified ? '#4ade80' : '#94a3b8',
            border: `1px solid ${unified ? '#16a34a55' : '#334155'}`,
          }}>
          {summary.isLoading ? 'جارٍ فحص المصدر…'
            : unified ? 'تلخيص موحّد متاح' : 'مصادر منفصلة (التلخيص غير منشور)'}
        </span>
        <span className="text-[12px] text-slate-500 mr-auto">
          كلّ بلاطة حالتها مستقلّة — فشل بلاطة لا يكسر الجدار، ولا أرقام مُختلَقة.
        </span>
      </header>

      {/* رأس القيادة: مؤشّرات الأداء البارزة (من التلخيص الموحّد؛ يختفي إن غاب). */}
      <KpiStrip summary={summary.data} />

      {/* شبكة البلاطات: الخريطة كبيرة (عمودان × صفّان)؛ البقيّة بلاطات أصغر. */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 auto-rows-[minmax(180px,auto)]">
        <MapTile />
        <AlertsTile />
        <FleetTile />
        <WeatherTile />
        <IrrigationTile />
        <DecisionsTile />
      </div>
    </div>
  );
}
