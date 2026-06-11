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
  Wifi, WifiOff, KeyRound, Lock, Copy, AlertTriangle, CheckCircle2,
} from 'lucide-react';
import NotificationSettingsPage from './NotificationSettingsPage';
import { useAllServicesHealth } from '../hooks/useApi';
import { wsService } from '../services/websocket';
import { useAuthStore } from '../hooks/useAuth';
import { normalizeRole, ROLE_LABEL_AR } from '../lib/permissions';
import {
  mfaSetup, mfaActivate, mfaDisable, changePassword, apiErrorMessage,
  type MfaSetupResponse,
} from '../services/api';

type Tab = 'general' | 'notifications' | 'services' | 'security';

// حفظ إعدادات العميل فعليّاً (كانت حالة محلّيّة تُفقَد عند التحديث).
const SETTINGS_KEY = 'sahool_settings';
function loadSettings(): { lang?: string; map?: string } {
  try {
    return JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}');
  } catch {
    return {};
  }
}

const TABS: { id: Tab; label: string; icon: any }[] = [
  { id:'general',       label:'عام',         icon:Globe  },
  { id:'notifications', label:'الإشعارات',   icon:Bell   },
  { id:'services',      label:'الاتصالات',   icon:Server },
  { id:'security',      label:'الأمان',      icon:Shield },
];

export default function SettingsPage() {
  const [tab,     setTab]    = useState<Tab>('general');
  const [saved,   setSaved]  = useState(false);
  const [lang,    setLang]   = useState(() => loadSettings().lang ?? 'ar');
  const [map,     setMap]    = useState(() => loadSettings().map ?? 'satellite');
  // المفتاح في الذاكرة فقط (لا localStorage) — تخزينه دائماً يعرّضه لسرقة عبر XSS.
  const [claude,  setClaude] = useState('');
  const [showKey, setShowKey] = useState(false);

  const { user } = useAuthStore();
  const { data: services, isLoading: svLoading, refetch: refetchSv } = useAllServicesHealth();
  const wsOk = wsService.isConnected();

  const handleSave = () => {
    // persist للتفضيلات غير الحسّاسة فقط (لغة/خريطة) — يصمد عبر تحديث الصفحة.
    // لا نحفظ المفتاح أبداً (سرّ: تخزينه في localStorage مخاطرة XSS).
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify({ lang, map }));
    } catch {
      /* تخزين المتصفّح غير متاح — نتجاهل بهدوء */
    }
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
              {' '}· لا يُخزَّن (يبقى في الذاكرة للجلسة فقط — حمايةً من XSS؛ المستشار يعمل عبر الخدمة الخلفيّة).
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
          {/* حساب المستخدم: MFA + تغيير كلمة المرور (ربط حيّ مع auth-service) */}
          <AccountSecurity Section={Section} Row={Row} inputCls={inputCls} inputSty={inputSty} />

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

          <Section title="أدوار المستخدمين (RBAC — مُطبَّق فعليّاً)">
            <p className="text-[11px] text-slate-500 mb-1">
              دورك الحاليّ:{' '}
              <span className="text-emerald-400">{ROLE_LABEL_AR[normalizeRole(user?.role)]}</span>
            </p>
            {([
              { r: 'owner',      perms: 'كل الصفحات + الإدارة' },
              { r: 'manager',    perms: 'كل الصفحات + إدارة' },
              { r: 'agronomist', perms: 'كل الصفحات (بلا إدارة مستخدمين)' },
              { r: 'worker',     perms: 'لوحة + أقمار + حقول + مهام + تنبيهات + مستشار' },
              { r: 'viewer',     perms: 'قراءة فقط — بلا إضافة/حذف/إقرار' },
            ] as const).map((row, i) => {
              const isCurrent = normalizeRole(user?.role) === row.r;
              return (
                <div key={i} className="flex gap-3 py-1.5 border-b last:border-0 text-sm items-center"
                  style={{ borderColor: '#334155' }}>
                  <span className="px-2 py-0.5 rounded text-[11px]"
                    style={{ background: isCurrent ? '#16a34a22' : '#1e293b',
                      border: `1px solid ${isCurrent ? '#16a34a' : '#334155'}`,
                      color: isCurrent ? '#4ade80' : '#38bdf8' }}>
                    {ROLE_LABEL_AR[row.r]}{isCurrent ? ' ●' : ''}
                  </span>
                  <span className="text-slate-400 text-xs">{row.perms}</span>
                </div>
              );
            })}
          </Section>
        </div>
      )}

      <div className="text-center text-[10px] text-slate-700 py-2">
        SAHOOL v8.0.0 · 88 ملف · 16,181 سطر · MIT License
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// AccountSecurity — أمان الحساب: تفعيل/تعطيل MFA + تغيير كلمة المرور
// ربط حيّ مع auth-service. لا fallback وهميّ — مسارات حسّاسة، الخطأ يُعرَض
// بصدق عبر apiErrorMessage. الأشكال تطابق services/auth/main.py.
// ═══════════════════════════════════════════════════════════════
function AccountSecurity({ Section, Row, inputCls, inputSty }: {
  Section: (p: { title?: string; children: any }) => React.ReactNode;
  Row: (p: { label: string; hint?: string; children: any }) => React.ReactNode;
  inputCls: string;
  inputSty: React.CSSProperties;
}) {
  // ── MFA setup state ──────────────────────────────────────────
  // setupData != null ⇒ بدأ الاقتران (يُعرض السرّ + otpauth) بانتظار التفعيل.
  const [setupData, setSetupData] = useState<MfaSetupResponse | null>(null);
  const [mfaActivated, setMfaActivated] = useState(false);
  const [activateCode, setActivateCode] = useState('');
  const [mfaBusy, setMfaBusy] = useState(false);
  const [mfaErr, setMfaErr]   = useState('');
  const [copied, setCopied]   = useState(false);

  // ── MFA disable state ────────────────────────────────────────
  const [showDisable, setShowDisable] = useState(false);
  const [disableCode, setDisableCode] = useState('');
  const [disableBusy, setDisableBusy] = useState(false);
  const [disableErr, setDisableErr]   = useState('');
  const [disabledOk, setDisabledOk]   = useState(false);

  // ── Change password state ────────────────────────────────────
  const [curPw, setCurPw]       = useState('');
  const [newPw, setNewPw]       = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [showPw, setShowPw]     = useState(false);
  const [pwBusy, setPwBusy]     = useState(false);
  const [pwErr, setPwErr]       = useState('');
  const [pwOk, setPwOk]         = useState(false);

  const handleSetup = async () => {
    setMfaBusy(true); setMfaErr(''); setMfaActivated(false);
    try {
      const data = await mfaSetup();
      setSetupData(data);
    } catch (e) {
      setMfaErr(apiErrorMessage(e, 'تعذّر بدء اقتران المصادقة الثنائيّة'));
    } finally {
      setMfaBusy(false);
    }
  };

  const handleActivate = async () => {
    if (!activateCode.trim()) { setMfaErr('أدخل الرمز من تطبيق المصادقة'); return; }
    setMfaBusy(true); setMfaErr('');
    try {
      await mfaActivate(activateCode.trim());
      setMfaActivated(true);
      setSetupData(null);  // السرّ يُعرَض مرّة واحدة فقط — نخفيه بعد التفعيل
      setActivateCode('');
    } catch (e) {
      setMfaErr(apiErrorMessage(e, 'رمز غير صحيح — تأكّد من تطبيق المصادقة'));
    } finally {
      setMfaBusy(false);
    }
  };

  const handleDisable = async () => {
    if (!disableCode.trim()) { setDisableErr('أدخل الرمز الحاليّ لتأكيد التعطيل'); return; }
    setDisableBusy(true); setDisableErr('');
    try {
      await mfaDisable(disableCode.trim());
      setDisabledOk(true);
      setShowDisable(false);
      setDisableCode('');
    } catch (e) {
      setDisableErr(apiErrorMessage(e, 'تعذّر تعطيل المصادقة الثنائيّة'));
    } finally {
      setDisableBusy(false);
    }
  };

  // قواعد كلمة المرور = ما يفرضه SignupPage/الخادم (8+، كبير، رقم، رمز خاص).
  const pwValidation = (): string | null => {
    if (newPw.length < 8) return 'كلمة المرور 8 أحرف على الأقل';
    if (!/[A-Z]/.test(newPw)) return 'يجب أن تحتوي على حرف كبير (إنجليزيّ)';
    if (!/[0-9]/.test(newPw)) return 'يجب أن تحتوي على رقم';
    if (!/[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/.test(newPw)) return 'يجب أن تحتوي على رمز خاص (مثل !@#$)';
    if (newPw !== confirmPw) return 'كلمتا المرور غير متطابقتين';
    return null;
  };

  const handleChangePw = async () => {
    if (!curPw) { setPwErr('أدخل كلمة المرور الحاليّة'); return; }
    const v = pwValidation();
    if (v) { setPwErr(v); return; }
    setPwBusy(true); setPwErr(''); setPwOk(false);
    try {
      await changePassword(curPw, newPw);
      setPwOk(true);
      setCurPw(''); setNewPw(''); setConfirmPw('');
    } catch (e) {
      setPwErr(apiErrorMessage(e, 'تعذّر تغيير كلمة المرور'));
    } finally {
      setPwBusy(false);
    }
  };

  const copySecret = async () => {
    if (!setupData) return;
    try {
      await navigator.clipboard.writeText(setupData.secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* الحافظة غير متاحة — المستخدم ينسخ يدويّاً */ }
  };

  const errBox = (msg: string) => (
    <div className="flex items-center gap-2 p-2.5 rounded-lg text-xs" style={{ background:'#1a0000', border:'1px solid #dc262633' }}>
      <AlertTriangle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
      <span className="text-red-300">{msg}</span>
    </div>
  );
  const okBox = (msg: string) => (
    <div className="flex items-center gap-2 p-2.5 rounded-lg text-xs text-emerald-300" style={{ background:'#052e16', border:'1px solid #16a34a33' }}>
      <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" /> {msg}
    </div>
  );

  return (
    <>
      {/* ── MFA (TOTP) ──────────────────────────────────────── */}
      <Section title="المصادقة الثنائيّة (TOTP)">
        <p className="text-[11px] text-slate-500">
          طبقة حماية إضافيّة: عند الدخول يُطلب رمز مؤقّت من تطبيق مصادقة (Google Authenticator / Authy).
        </p>

        {mfaActivated && okBox('تم تفعيل المصادقة الثنائيّة بنجاح')}
        {disabledOk && okBox('تم تعطيل المصادقة الثنائيّة')}

        {/* بدء الاقتران */}
        {!setupData && !mfaActivated && (
          <button onClick={handleSetup} disabled={mfaBusy}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white"
            style={{ background: mfaBusy ? '#15803d' : '#16a34a', opacity: mfaBusy ? 0.8 : 1 }}>
            {mfaBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
            بدء تفعيل المصادقة الثنائيّة
          </button>
        )}

        {/* عرض السرّ + إدخال الرمز للتفعيل */}
        {setupData && (
          <div className="space-y-3">
            <div className="p-3 rounded-lg space-y-2" style={{ background:'#0f1117', border:'1px solid #334155' }}>
              <p className="text-[11px] text-slate-400">امسح هذا الرابط كـ QR أو أدخل السرّ يدويّاً في تطبيق المصادقة. <span className="text-amber-400">يُعرَض مرّة واحدة فقط.</span></p>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-xs text-emerald-300 font-mono break-all">{setupData.secret}</code>
                <button onClick={copySecret} className="flex items-center gap-1 px-2 py-1 rounded text-[11px] text-slate-300 hover:text-white" style={{ border:'1px solid #334155' }}>
                  {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />} {copied ? 'نُسخ' : 'نسخ'}
                </button>
              </div>
              <div className="text-[10px] text-slate-600 font-mono break-all border-t pt-2" style={{ borderColor:'#334155' }}>
                {setupData.provisioning_uri}
              </div>
            </div>
            <Row label="رمز التأكيد" hint="من تطبيق المصادقة">
              <div className="flex gap-2">
                <input value={activateCode}
                  onChange={e => setActivateCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="123456" inputMode="numeric"
                  className={inputCls + ' tracking-[0.3em] text-center'} style={inputSty} />
                <button onClick={handleActivate} disabled={mfaBusy}
                  className="flex items-center gap-1.5 px-4 rounded-lg text-sm font-medium text-white whitespace-nowrap"
                  style={{ background: mfaBusy ? '#15803d' : '#16a34a', opacity: mfaBusy ? 0.8 : 1 }}>
                  {mfaBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />} تفعيل
                </button>
              </div>
            </Row>
          </div>
        )}

        {mfaErr && errBox(mfaErr)}

        {/* تعطيل MFA */}
        <div className="border-t pt-3" style={{ borderColor:'#334155' }}>
          {!showDisable ? (
            <button onClick={() => { setShowDisable(true); setDisableErr(''); setDisabledOk(false); }}
              className="text-xs text-slate-400 hover:text-red-400">
              تعطيل المصادقة الثنائيّة (إن كانت مفعّلة)
            </button>
          ) : (
            <div className="space-y-2">
              <p className="text-[11px] text-slate-500">أدخل رمزاً صحيحاً حاليّاً لتأكيد التعطيل.</p>
              <div className="flex gap-2">
                <input value={disableCode}
                  onChange={e => setDisableCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="123456" inputMode="numeric"
                  className={inputCls + ' tracking-[0.3em] text-center'} style={inputSty} />
                <button onClick={handleDisable} disabled={disableBusy}
                  className="flex items-center gap-1.5 px-4 rounded-lg text-sm font-medium text-white whitespace-nowrap"
                  style={{ background: disableBusy ? '#7f1d1d' : '#dc2626', opacity: disableBusy ? 0.8 : 1 }}>
                  {disableBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : null} تعطيل
                </button>
                <button onClick={() => setShowDisable(false)}
                  className="px-3 rounded-lg text-xs text-slate-400" style={{ border:'1px solid #334155' }}>إلغاء</button>
              </div>
              {disableErr && errBox(disableErr)}
            </div>
          )}
        </div>
      </Section>

      {/* ── Change password ─────────────────────────────────── */}
      <Section title="تغيير كلمة المرور">
        {pwOk && okBox('تم تغيير كلمة المرور بنجاح')}
        <Row label="كلمة المرور الحاليّة">
          <div className="relative">
            <input type={showPw ? 'text' : 'password'} value={curPw} onChange={e => setCurPw(e.target.value)}
              placeholder="••••••••" autoComplete="current-password"
              className={inputCls + ' pl-10'} style={inputSty} />
            <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          </div>
        </Row>
        <Row label="كلمة المرور الجديدة" hint="8 أحرف، حرف كبير، رقم، رمز">
          <div className="relative">
            <input type={showPw ? 'text' : 'password'} value={newPw} onChange={e => setNewPw(e.target.value)}
              placeholder="••••••••" autoComplete="new-password"
              className={inputCls + ' pl-10'} style={inputSty} />
            <button type="button" onClick={() => setShowPw(!showPw)}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200">
              {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </Row>
        <Row label="تأكيد الجديدة">
          <input type={showPw ? 'text' : 'password'} value={confirmPw} onChange={e => setConfirmPw(e.target.value)}
            placeholder="••••••••" autoComplete="new-password"
            className={inputCls} style={inputSty} />
        </Row>
        {pwErr && errBox(pwErr)}
        <div className="flex justify-end">
          <button onClick={handleChangePw} disabled={pwBusy}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white"
            style={{ background: pwBusy ? '#15803d' : '#16a34a', opacity: pwBusy ? 0.8 : 1 }}>
            {pwBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />} تحديث كلمة المرور
          </button>
        </div>
      </Section>
    </>
  );
}
