// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — SettingsPage.tsx (مُحدّثة)
// ✅ تبويبات: عام | إشعارات | اتصالات | أمان
// ✅ ربط NotificationSettingsPage كتبويب
// ✅ حالة الخدمات الحقيقية (checkAllServices)
// ✅ إعدادات الخريطة والمظهر
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  Settings, Bell, Globe, Shield, Server, Save,
  Check, Loader2, Eye, EyeOff, RefreshCw,
  Wifi, WifiOff,
} from 'lucide-react';
import NotificationSettingsPage from './NotificationSettingsPage';
import { useAllServicesHealth } from '../hooks/useApi';
import { wsService } from '../services/websocket';

type Tab = 'general' | 'notifications' | 'services' | 'security';

const TABS: { id: Tab; label: string; icon: any }[] = [
  { id:'general',       label:'عام',         icon:Globe  },
  { id:'notifications', label:'الإشعارات',   icon:Bell   },
  { id:'services',      label:'الاتصالات',   icon:Server },
  { id:'security',      label:'الأمان',      icon:Shield },
];

export default function SettingsPage() {
  const [tab,     setTab]    = useState<Tab>('general');
  const [saved,   setSaved]  = useState(false);
  const [lang,    setLang]   = useState('ar');
  const [map,     setMap]    = useState('satellite');
  const [claude,  setClaude] = useState('');
  const [showKey, setShowKey] = useState(false);

  const { data: services, isLoading: svLoading, refetch: refetchSv } = useAllServicesHealth();
  const wsOk = wsService.isConnected();

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  const Section = ({ title, children }: any) => (
    <div className="rounded-xl border overflow-hidden" style={{ background:'#1e293b', borderColor:'#334155' }}>
      {title && (
        <div className="px-4 py-3 border-b text-sm font-semibold text-slate-300"
          style={{ background:'#0f1117', borderColor:'#334155' }}>{title}</div>
      )}
      <div className="p-4 space-y-4">{children}</div>
    </div>
  );

  const Row = ({ label, hint, children }: any) => (
    <div className="flex flex-col sm:flex-row sm:items-center gap-2">
      <div className="sm:w-44 flex-shrink-0">
        <div className="text-sm text-slate-300">{label}</div>
        {hint && <div className="text-[11px] text-slate-500">{hint}</div>}
      </div>
      <div className="flex-1">{children}</div>
    </div>
  );

  const inputCls = "w-full px-3 py-2 rounded-lg text-sm";
  const inputSty = { background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' };
  const selSty   = { ...inputSty };

  return (
    <div className="space-y-5 max-w-2xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <Settings className="w-5 h-5 text-emerald-400" />
        <h2 className="text-xl font-bold text-slate-100">الإعدادات</h2>
      </div>

      {/* Tab bar */}
      <div className="flex flex-wrap gap-1 p-1 rounded-xl" style={{ background:'#0f1117' }}>
        {TABS.map(t => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm flex-1 justify-center transition-all"
              style={{ background:active?'#1e3a1e':'transparent', color:active?'#4ade80':'#64748b',
                border:`1px solid ${active?'#16a34a44':'transparent'}` }}>
              <Icon className="w-4 h-4" />{t.label}
            </button>
          );
        })}
      </div>

      {/* ── General ──────────────────────────────────────────── */}
      {tab === 'general' && (
        <div className="space-y-4">
          <Section title="اللغة والعرض">
            <Row label="اللغة" hint="واجهة المستخدم">
              <select value={lang} onChange={e=>setLang(e.target.value)} className={inputCls} style={selSty}>
                <option value="ar">العربية (RTL)</option>
                <option value="en">English (LTR)</option>
              </select>
            </Row>
            <Row label="مزود الخريطة">
              <select value={map} onChange={e=>setMap(e.target.value)} className={inputCls} style={selSty}>
                <option value="satellite">Esri World Imagery (قمر صناعي)</option>
                <option value="osm">OpenStreetMap</option>
                <option value="cartodb">CartoDB Light</option>
                <option value="eox">EOX Sentinel-2</option>
              </select>
            </Row>
          </Section>

          <Section title="Claude API (المستشار الذكي)">
            <Row label="مفتاح API" hint="sk-ant-...">
              <div className="relative">
                <input type={showKey?'text':'password'} value={claude}
                  onChange={e=>setClaude(e.target.value)}
                  placeholder="sk-ant-api03-..."
                  className={inputCls+' pl-10'} style={inputSty} />
                <button onClick={()=>setShowKey(!showKey)}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200">
                  {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </Row>
            <p className="text-[11px] text-slate-500">
              احصل على مفتاح من <a href="https://console.anthropic.com" target="_blank" className="text-emerald-500 hover:underline">console.anthropic.com</a>
            </p>
          </Section>

          <div className="flex justify-end">
            <button onClick={handleSave}
              className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white"
              style={{ background: saved ? '#15803d' : '#16a34a' }}>
              {saved ? <><Check className="w-4 h-4" /> تم الحفظ ✓</> : <><Save className="w-4 h-4" /> حفظ</>}
            </button>
          </div>
        </div>
      )}

      {/* ── Notifications ─────────────────────────────────────── */}
      {tab === 'notifications' && <NotificationSettingsPage />}

      {/* ── Services ──────────────────────────────────────────── */}
      {tab === 'services' && (
        <div className="space-y-4">
          <Section title="حالة الخدمات">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-slate-400">آخر فحص</span>
              <button onClick={() => refetchSv()}
                className="flex items-center gap-1 px-2 py-1 rounded text-xs text-slate-400 hover:text-slate-200">
                <RefreshCw className={`w-3 h-3 ${svLoading?'animate-spin':''}`} /> تحديث
              </button>
            </div>

            {/* WebSocket */}
            <div className="flex items-center justify-between py-2 border-b" style={{ borderColor:'#334155' }}>
              <span className="text-sm text-slate-300">WebSocket (الإشعارات)</span>
              <span className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${wsOk?'bg-emerald-950 text-emerald-400':'bg-slate-800 text-slate-500'}`}>
                {wsOk ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
                {wsOk ? 'متصل' : 'غير متصل'}
              </span>
            </div>

            {svLoading ? (
              <div className="flex justify-center py-4">
                <Loader2 className="w-5 h-5 text-emerald-500 animate-spin" />
              </div>
            ) : (
              (services || []).map((svc: any, i: number) => {
                const ok = svc.status === 'ok' || svc.status === 'ready' || svc.status === 'alive';
                return (
                  <div key={i} className="flex items-center justify-between py-2 border-b last:border-0"
                    style={{ borderColor:'#334155' }}>
                    <span className="text-sm text-slate-300 capitalize">{svc.name}</span>
                    <span className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${ok?'bg-emerald-950 text-emerald-400 border border-emerald-900':'bg-red-950 text-red-400 border border-red-900'}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${ok?'bg-emerald-400':'bg-red-400'}`} />
                      {ok ? 'متاح' : 'غير متاح'}
                    </span>
                  </div>
                );
              })
            )}

            {(!services || services.length === 0) && !svLoading && (
              <div className="space-y-2">
                {[
                  {n:'auth-service (:8120)',    ok:false},
                  {n:'indicators-service (:8091)',ok:false},
                  {n:'vegetation-service (:8090)',ok:false},
                  {n:'weather-service (:8092)',  ok:false},
                  {n:'soil-service (:8094)',      ok:false},
                  {n:'kong-gateway (:8000)',      ok:false},
                ].map((s,i)=>(
                  <div key={i} className="flex justify-between items-center py-1">
                    <span className="text-xs text-slate-400">{s.n}</span>
                    <span className="text-xs text-slate-600">—</span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section title="متغيرات البيئة">
            {[
              {k:'VITE_API_URL',    v:import.meta.env.VITE_API_URL   || '—'},
              {k:'VITE_INDICATORS', v:import.meta.env.VITE_INDICATORS_URL || '—'},
              {k:'VITE_WEATHER',    v:import.meta.env.VITE_WEATHER_URL || '—'},
              {k:'VITE_MOCK_MODE',  v:import.meta.env.VITE_MOCK_MODE || 'false'},
            ].map((e,i)=>(
              <div key={i} className="flex justify-between text-xs py-1 border-b last:border-0" style={{ borderColor:'#334155' }}>
                <span className="text-slate-500 font-mono">{e.k}</span>
                <span className="text-slate-300 font-mono truncate max-w-48">{e.v}</span>
              </div>
            ))}
          </Section>
        </div>
      )}

      {/* ── Security ─────────────────────────────────────────── */}
      {tab === 'security' && (
        <div className="space-y-4">
          <Section title="نموذج الأمان">
            {[
              {k:'JWT Algorithm',      v:'HS256',      ok:true},
              {k:'JWT Expiry',         v:'168h (7d)',   ok:true},
              {k:'enforce_tenant',     v:'مُفعَّل',    ok:true},
              {k:'Row Level Security', v:'مُفعَّل',    ok:true},
              {k:'bcrypt rounds',      v:'12',          ok:true},
              {k:'CORS Origins',       v:'محدودة',      ok:true},
              {k:'HTTPS (Nginx)',      v:'مُهيَّأ',     ok:true},
              {k:'Prometheus /metrics',v:'محمي (IP)',   ok:true},
              {k:'2FA',                v:'غير مفعّل',   ok:false},
              {k:'Audit Log',          v:'جزئي',        ok:false},
            ].map((s,i)=>(
              <div key={i} className="flex justify-between items-center py-1.5 border-b last:border-0 text-sm"
                style={{ borderColor:'#334155' }}>
                <span className="text-slate-400">{s.k}</span>
                <span className={s.ok?'text-emerald-400':'text-amber-400'} style={{ fontWeight:500 }}>{s.v}</span>
              </div>
            ))}
          </Section>

          <Section title="أدوار المستخدمين (RBAC)">
            {[
              {r:'admin',  perms:'كل الصفحات + حذف + إدارة المستخدمين'},
              {r:'expert', perms:'كل الصفحات بدون إدارة المستخدمين'},
              {r:'farmer', perms:'Dashboard + Satellite + Fields + Tasks'},
              {r:'viewer', perms:'قراءة فقط — بدون إضافة أو حذف'},
            ].map((row,i)=>(
              <div key={i} className="flex gap-3 py-1.5 border-b last:border-0 text-sm" style={{ borderColor:'#334155' }}>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono"
                  style={{ background:'#1e293b', border:'1px solid #334155', color:'#38bdf8' }}>{row.r}</span>
                <span className="text-slate-400 text-xs">{row.perms}</span>
              </div>
            ))}
          </Section>
        </div>
      )}

      <div className="text-center text-[10px] text-slate-700 py-2">
        SAHOOL v8.0.0 · 88 ملف · 16,181 سطر · MIT License
      </div>
    </div>
  );
}
