// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — SettingsPage.tsx (مكسوّة على نظام التصميم DS)
// ✅ تبويبات: عام | إشعارات | اتصالات | أمان | (مشاركة | فريق — owner)
// ✅ ربط NotificationSettingsPage كتبويب
// ✅ حالة الخدمات الحقيقية (checkAllServices)
// ✅ إعدادات الخريطة والمظهر
// ✅ تبويب «المشاركة»: واجهة مشاركة بمستوى الحقل (components/sharing/SharingPanel)
// عبر نقاط sharing-keys القائمة. الكسوة عرضيّة فقط — كلّ المنطق/النداءات محفوظة.
// ═══════════════════════════════════════════════════════════════
import { useEffect, useState } from 'react';
import {
  Settings, Bell, Globe, Shield, Server, Save,
  Check, Loader2, Eye, EyeOff, RefreshCw,
  Wifi, WifiOff, KeyRound, Lock, Copy, AlertTriangle, CheckCircle2,
  Mail, Phone, BadgeCheck, Users, Trash2, UserPlus, Share2,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import NotificationSettingsPage from './NotificationSettingsPage';
import SharingPanel from '../components/sharing/SharingPanel';
import { useAllServicesHealth, type ServiceHealth } from '../hooks/useApi';
import { wsService } from '../services/websocket';
import { useAuthStore } from '../hooks/useAuth';
import { normalizeRole, ROLE_LABEL_AR } from '../lib/permissions';
import { Card, Button, Pill, TabBar } from '../components/ds/atoms';
import { T } from '../components/ds/tokens';
import { loadSettings, saveSettings } from '../lib/appSettings';
import {
  mfaSetup, mfaActivate, mfaDisable, changePassword, apiErrorMessage,
  getVerificationStatus, requestVerification, confirmVerification,
  createInvitation, listInvitations, revokeInvitation,
  listTeamUsers, changeUserRole, deactivateUser, type TeamUser, type AssignableRole,
  type MfaSetupResponse, type VerifyChannel, type VerificationStatus,
  type InviteableRole, type PendingInvitation,
} from '../services/api';

type Tab = 'general' | 'notifications' | 'services' | 'security' | 'sharing' | 'team';

// حفظ/قراءة تفضيلات العميل (لغة/خريطة) عبر الوحدة المُشترَكة lib/appSettings —
// نفس المفتاح والمنطق الدفاعيّ يقرأه SetupCabin (منع انحراف نسختَين).

const BASE_TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id:'general',       label:'عام',         icon:Globe  },
  { id:'notifications', label:'الإشعارات',   icon:Bell   },
  { id:'services',      label:'الاتصالات',   icon:Server },
  { id:'security',      label:'الأمان',      icon:Shield },
  // تبويب «المشاركة» متاح للجميع: العرض tenant-scoped؛ الإنشاء محكوم بالصلاحيّة
  // داخل SharingPanel (والإنفاذ الحقيقيّ خادم-جانبيّ).
  { id:'sharing',       label:'المشاركة',    icon:Share2 },
];
// تبويب «الفريق» (الدعوات) لمالك المستأجِر فقط — يدير دعوة الأعضاء بأدوار أدنى.
const TEAM_TAB: { id: Tab; label: string; icon: LucideIcon } = { id:'team', label:'الفريق', icon:Users };

export default function SettingsPage() {
  const [tab,     setTab]    = useState<Tab>('general');
  const [saved,   setSaved]  = useState(false);
  const [lang,    setLang]   = useState(() => loadSettings().lang ?? 'ar');
  const [map,     setMap]    = useState(() => loadSettings().map ?? 'satellite');
  // المفتاح في الذاكرة فقط (لا localStorage) — تخزينه دائماً يعرّضه لسرقة عبر XSS.
  const [claude,  setClaude] = useState('');
  const [showKey, setShowKey] = useState(false);

  const { user } = useAuthStore();
  // إدارة الفريق/الدعوات لمالك المستأجِر فقط (owner). الواجهة حارس عرض؛ الإنفاذ
  // الحقيقيّ خادم-جانبيّ (auth يرفض غير owner/admin بـ403).
  const isOwner = normalizeRole(user?.role) === 'owner';
  const TABS = isOwner ? [...BASE_TABS, TEAM_TAB] : BASE_TABS;
  const { data: services, isLoading: svLoading, refetch: refetchSv } = useAllServicesHealth();
  const wsOk = wsService.isConnected();

  const handleSave = () => {
    // persist للتفضيلات غير الحسّاسة فقط (لغة/خريطة) — يصمد عبر تحديث الصفحة.
    // لا نحفظ المفتاح أبداً (سرّ: تخزينه في localStorage مخاطرة XSS).
    saveSettings({ lang, map });
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  // ── غلاف قسم موحّد (DS): عنوان + سطح بطاقة. يُمرَّر للأقسام الفرعيّة كي ترث
  //    الكسوة الجديدة دون إعادة كتابة منطقها (تعديل عرضيّ فقط).
  const Section = ({ title, children }: { title?: string; children: React.ReactNode }) => (
    <Card pad={0} style={{ overflow: 'hidden' }}>
      {title && (
        <div
          style={{
            padding: '12px 16px',
            borderBottom: `1px solid ${T.line}`,
            background: T.card2,
            fontSize: 14, fontWeight: 700, color: T.brownSoft,
          }}
        >
          {title}
        </div>
      )}
      <div className="space-y-4" style={{ padding: 16 }}>{children}</div>
    </Card>
  );

  const Row = ({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) => (
    <div className="flex flex-col sm:flex-row sm:items-center gap-2">
      <div className="sm:w-44 flex-shrink-0">
        <div style={{ fontSize: 13, color: T.ink, fontWeight: 600 }}>{label}</div>
        {hint && <div style={{ fontSize: 11, color: T.faint }}>{hint}</div>}
      </div>
      <div className="flex-1">{children}</div>
    </div>
  );

  const inputCls = "w-full px-3 py-2 rounded-lg text-sm";
  // قيَم DS فاتحة — تُمرَّر للأقسام الفرعيّة (تحقّق/أمان/فريق) فترث الكسوة.
  const inputSty: React.CSSProperties = { background: T.card, border: `1px solid ${T.line}`, color: T.ink, outline: 'none' };
  const selSty   = { ...inputSty };

  return (
    <div className="space-y-5 max-w-2xl mx-auto" dir="rtl" data-testid="settings-page">
      <div className="flex items-center gap-2">
        <Settings style={{ width: 20, height: 20, color: T.gold }} />
        <h2 style={{ fontSize: 20, fontWeight: 800, color: T.ink }}>الإعدادات</h2>
      </div>

      {/* شريط التبويبات (DS) */}
      <TabBar<Tab>
        tabs={TABS.map(t => ({ id: t.id, label: t.label, icon: <t.icon className="w-4 h-4" /> }))}
        active={tab}
        onChange={setTab}
      />

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
                  className="absolute left-3 top-1/2 -translate-y-1/2"
                  style={{ color: T.muted }}>
                  {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </Row>
            <p style={{ fontSize: 11, color: T.faint }}>
              احصل على مفتاح من <a href="https://console.anthropic.com" target="_blank" rel="noopener noreferrer" style={{ color: T.green }} className="hover:underline">console.anthropic.com</a>
              {' '}· لا يُخزَّن (يبقى في الذاكرة للجلسة فقط — حمايةً من XSS؛ المستشار يعمل عبر الخدمة الخلفيّة).
            </p>
          </Section>

          <div className="flex justify-end">
            <Button full={false} onClick={handleSave} style={{ padding: '10px 20px', background: saved ? T.greenDark : T.green }}>
              {saved ? <><Check className="w-4 h-4" /> تم الحفظ ✓</> : <><Save className="w-4 h-4" /> حفظ</>}
            </Button>
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
              <span style={{ fontSize: 12, color: T.muted }}>آخر فحص</span>
              <button onClick={() => refetchSv()}
                className="flex items-center gap-1 px-2 py-1 rounded"
                style={{ fontSize: 12, color: T.muted }}>
                <RefreshCw className={`w-3 h-3 ${svLoading?'animate-spin':''}`} /> تحديث
              </button>
            </div>

            {/* WebSocket */}
            <div className="flex items-center justify-between py-2" style={{ borderBottom: `1px solid ${T.line}` }}>
              <span style={{ fontSize: 13, color: T.ink }}>WebSocket (الإشعارات)</span>
              <Pill tone={wsOk ? 'ok' : 'neutral'} icon={wsOk ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}>
                {wsOk ? 'متصل' : 'غير متصل'}
              </Pill>
            </div>

            {svLoading ? (
              <div className="flex justify-center py-4">
                <Loader2 className="w-5 h-5 animate-spin" style={{ color: T.green }} />
              </div>
            ) : (
              (services || []).map((svc: ServiceHealth) => {
                // ServiceHealth.status ∈ {'ok','error','unknown'} (checkAll يصدر ok/error فقط)؛
                // 'ready'/'alive' كانتا شرطين ميّتين لا يتحقّقان أبداً — أُزيلتا.
                const ok = svc.status === 'ok';
                return (
                  // مفتاح ثابت باسم الخدمة (لا فهرس المصفوفة): إعادة الترتيب/التحديث
                  // الجزئيّ لا يُعيد استخدام حالة صفٍّ لخدمة أخرى (continuation-1 P1).
                  <div key={svc.name} className="flex items-center justify-between py-2"
                    style={{ borderBottom: `1px solid ${T.line}` }}>
                    <span className="capitalize" style={{ fontSize: 13, color: T.ink }}>{svc.name}</span>
                    <Pill tone={ok ? 'ok' : 'danger'}>{ok ? 'متاح' : 'غير متاح'}</Pill>
                  </div>
                );
              })
            )}

            {(!services || services.length === 0) && !svLoading && (
              <div className="space-y-2">
                {[
                  {n:'auth-service (:8120)'},
                  {n:'indicators-contract (:8091)'},
                  {n:'vegetation-service (:8090)'},
                  {n:'weather-service (:8092)'},
                  {n:'soil-service (:8094)'},
                  {n:'kong-gateway (:8000)'},
                ].map((s,i)=>(
                  <div key={i} className="flex justify-between items-center py-1">
                    <span style={{ fontSize: 12, color: T.muted }}>{s.n}</span>
                    <span style={{ fontSize: 12, color: T.faint }}>—</span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section title="متغيرات البيئة">
            {[
              {k:'VITE_API_MODE',       v:import.meta.env.VITE_API_MODE || 'gateway'},
              {k:'VITE_API_BASE_URL',   v:import.meta.env.VITE_API_BASE_URL ?? '(gateway: نسبيّ)'},
              {k:'VITE_INDICATORS',     v:import.meta.env.VITE_INDICATORS_BASE_URL || '/api/indicators'},
              {k:'VITE_WEATHER',        v:import.meta.env.VITE_WEATHER_BASE_URL || '/api/weather'},
              {k:'VITE_MOCK_MODE',      v:import.meta.env.VITE_MOCK_MODE || 'false'},
            ].map((e,i)=>(
              <div key={i} className="flex justify-between text-xs py-1" style={{ borderBottom: `1px solid ${T.line}` }}>
                <span className="font-mono" style={{ color: T.muted }}>{e.k}</span>
                <span className="font-mono truncate max-w-48" style={{ color: T.ink }}>{e.v}</span>
              </div>
            ))}
          </Section>
        </div>
      )}

      {/* ── Security ─────────────────────────────────────────── */}
      {tab === 'security' && (
        <div className="space-y-4">
          {/* تأكيد البريد/الهاتف (تحقّق ناعم عبر OTP — ربط حيّ مع auth-service) */}
          <AccountVerification Section={Section} Row={Row} inputCls={inputCls} inputSty={inputSty} />

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
              <div key={i} className="flex justify-between items-center py-1.5 text-sm"
                style={{ borderBottom: `1px solid ${T.line}` }}>
                <span style={{ color: T.muted }}>{s.k}</span>
                <span style={{ color: s.ok ? T.green : T.warn, fontWeight: 600 }}>{s.v}</span>
              </div>
            ))}
          </Section>

          <Section title="أدوار المستخدمين (RBAC — مُطبَّق فعليّاً)">
            <div className="flex items-center justify-between mb-1">
              <p style={{ fontSize: 11, color: T.muted }}>
                دورك الحاليّ:{' '}
                <span style={{ color: T.green, fontWeight: 700 }}>{ROLE_LABEL_AR[normalizeRole(user?.role)]}</span>
              </p>
              <SessionRefreshButton />
            </div>
            {([
              { r: 'owner',      perms: 'كل الصفحات + الإدارة' },
              { r: 'manager',    perms: 'كل الصفحات + إدارة' },
              { r: 'agronomist', perms: 'كل الصفحات (بلا إدارة مستخدمين)' },
              { r: 'worker',     perms: 'لوحة + أقمار + حقول + مهام + تنبيهات + مستشار' },
              { r: 'viewer',     perms: 'قراءة فقط — بلا إضافة/حذف/إقرار' },
            ] as const).map((row, i) => {
              const isCurrent = normalizeRole(user?.role) === row.r;
              return (
                <div key={i} className="flex gap-3 py-1.5 text-sm items-center"
                  style={{ borderBottom: `1px solid ${T.line}` }}>
                  <span className="px-2 py-0.5 rounded text-[11px]"
                    style={{ background: isCurrent ? T.greenSoft : T.card2,
                      border: `1px solid ${isCurrent ? T.green : T.line}`,
                      color: isCurrent ? T.greenDark : T.info, fontWeight: 600 }}>
                    {ROLE_LABEL_AR[row.r]}{isCurrent ? ' ●' : ''}
                  </span>
                  <span style={{ fontSize: 12, color: T.muted }}>{row.perms}</span>
                </div>
              );
            })}
          </Section>
        </div>
      )}

      {/* ── Sharing (واجهة مشاركة بمستوى الحقل عبر نقاط sharing-keys القائمة) ── */}
      {tab === 'sharing' && <SharingPanel />}

      {/* ── Team / Invitations (owner only) ──────────────────── */}
      {tab === 'team' && isOwner && (
        <TeamManagement Section={Section} inputCls={inputCls} inputSty={inputSty} />
      )}

      <div className="text-center py-2" style={{ fontSize: 10, color: T.faint }}>
        SAHOOL v8.0.0 · 88 ملف · 16,181 سطر · MIT License
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// TeamManagement — إدارة الفريق/الدعوات (لمالك المستأجِر فقط).
// نموذج (بريد + دور من {expert/farmer/viewer}) ⇒ createInvitation ⇒ يعرض رابط
// القبول للنسخ. + قائمة الدعوات المعلّقة مع إلغاء. ربط حيّ مع auth-service.
// الأدوار المعروضة تطابق التسميات الخماسيّة في الواجهة عبر تخطيط auth→منصّة:
//   expert→خبير زراعيّ (agronomist) · farmer→عامل (worker) · viewer→مشاهد.
// owner/admin غير معروضَين عمداً (auth يرفضهما — منع تصعيد الصلاحيّات).
// ═══════════════════════════════════════════════════════════════
const INVITE_ROLE_OPTIONS: { value: InviteableRole; label: string }[] = [
  { value: 'expert', label: 'خبير زراعيّ' },
  { value: 'farmer', label: 'عامل' },
  { value: 'viewer', label: 'مشاهد (قراءة فقط)' },
];

function TeamManagement({ Section, inputCls, inputSty }: {
  Section: (p: { title?: string; children: React.ReactNode }) => React.JSX.Element;
  inputCls: string;
  inputSty: React.CSSProperties;
}) {
  const [email, setEmail]   = useState('');
  const [role, setRole]     = useState<InviteableRole>('viewer');
  const [busy, setBusy]     = useState(false);
  const [error, setError]   = useState('');
  const [acceptUrl, setAcceptUrl] = useState('');
  const [copied, setCopied] = useState(false);
  const [invites, setInvites] = useState<PendingInvitation[]>([]);
  const [loadingList, setLoadingList] = useState(false);

  const refresh = async () => {
    setLoadingList(true);
    try {
      setInvites(await listInvitations());
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'تعذّر جلب الدعوات'));
    } finally {
      setLoadingList(false);
    }
  };

  useEffect(() => { refresh(); /* mount */ }, []);

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) { setError('أدخل بريد العضو'); return; }
    setBusy(true); setError(''); setAcceptUrl(''); setCopied(false);
    try {
      const res = await createInvitation({ email: email.trim(), role });
      // رابط مطلق قابل للنسخ (origin + المسار النسبيّ الذي تُعيده الخلفيّة).
      const origin = typeof window !== 'undefined' ? window.location.origin : '';
      setAcceptUrl(`${origin}${res.accept_url}`);
      setEmail('');
      await refresh();
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'تعذّر إنشاء الدعوة'));
    } finally {
      setBusy(false);
    }
  };

  const handleRevoke = async (id: number) => {
    setError('');
    try {
      await revokeInvitation(id);
      await refresh();
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'تعذّر إلغاء الدعوة'));
    }
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(acceptUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* الحافظة غير متاحة — يبقى الرابط ظاهراً للنسخ اليدويّ */
    }
  };

  return (
    <div className="space-y-4" dir="rtl">
      <Section title="دعوة عضو جديد">
        <p style={{ fontSize: 11, color: T.muted }}>
          الأعضاء ينضمّون لمؤسّستك بأدوار أدنى عبر دعوة (لا عبر التسجيل الذاتيّ). لا يمكن
          الدعوة بدور مالك/مشرف (منع تصعيد الصلاحيّات).
        </p>
        <form onSubmit={handleInvite} className="space-y-3">
          <div>
            <label className="block mb-1.5" style={{ fontSize: 13, color: T.brownSoft, fontWeight: 600 }}>البريد الإلكتروني</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="member@example.com" autoComplete="email"
              className={inputCls} style={inputSty} />
          </div>
          <div>
            <label className="block mb-1.5" style={{ fontSize: 13, color: T.brownSoft, fontWeight: 600 }}>الدور</label>
            <select value={role} onChange={e => setRole(e.target.value as InviteableRole)}
              className={inputCls} style={inputSty}>
              {INVITE_ROLE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-xl text-sm" style={{ background: T.dangerBg, border: `1px solid ${T.danger}` }}>
              <AlertTriangle className="w-4 h-4 flex-shrink-0" style={{ color: T.danger }} />
              <span style={{ color: T.danger }}>{error}</span>
            </div>
          )}
          <div className="flex justify-end">
            <Button full={false} onClick={() => handleInvite({ preventDefault: () => {} } as React.FormEvent)} disabled={busy} style={{ padding: '10px 20px' }}>
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserPlus className="w-4 h-4" />} إنشاء الدعوة
            </Button>
          </div>
        </form>

        {acceptUrl && (
          <div className="mt-2 p-3 rounded-xl text-sm" style={{ background: T.okBg, border: `1px solid ${T.green}` }}>
            <div className="flex items-center gap-2 mb-2" style={{ color: T.greenDark }}>
              <CheckCircle2 className="w-4 h-4" /> أُنشئت الدعوة — انسخ الرابط وأرسله للعضو:
            </div>
            <div className="flex items-center gap-2">
              <input readOnly value={acceptUrl}
                className="flex-1 px-3 py-2 rounded-lg text-xs font-mono"
                style={{ ...inputSty, direction:'ltr' }} />
              <button type="button" onClick={copyLink}
                className="flex items-center gap-1 px-3 py-2 rounded-lg text-xs"
                style={{ background: T.card2, border: `1px solid ${T.line}`, color: T.brownSoft }}>
                {copied ? <Check className="w-3.5 h-3.5" style={{ color: T.green }} /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? 'نُسخ' : 'نسخ'}
              </button>
            </div>
          </div>
        )}
      </Section>

      <Section title="الدعوات المعلّقة">
        <div className="flex items-center justify-between mb-1">
          <span style={{ fontSize: 12, color: T.muted }}>{invites.length} دعوة معلّقة</span>
          <button type="button" onClick={refresh}
            className="flex items-center gap-1 px-2 py-1 rounded"
            style={{ fontSize: 12, color: T.muted }}>
            <RefreshCw className={`w-3 h-3 ${loadingList ? 'animate-spin' : ''}`} /> تحديث
          </button>
        </div>
        {invites.length === 0 && !loadingList && (
          <p className="py-2" style={{ fontSize: 12, color: T.muted }}>لا دعوات معلّقة.</p>
        )}
        {invites.map(inv => (
          <div key={inv.id} className="flex items-center justify-between py-2"
            style={{ borderBottom: `1px solid ${T.line}` }}>
            <div className="min-w-0">
              <div className="truncate" style={{ fontSize: 13, color: T.ink }}>{inv.email}</div>
              <div style={{ fontSize: 11, color: T.muted }}>
                {INVITE_ROLE_OPTIONS.find(o => o.value === inv.role)?.label ?? inv.role}
                {inv.expires_at ? ` · تنتهي ${new Date(inv.expires_at).toLocaleDateString('ar')}` : ''}
              </div>
            </div>
            <button type="button" onClick={() => handleRevoke(inv.id)}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs"
              style={{ background: T.dangerBg, border: `1px solid ${T.danger}`, color: T.danger }}>
              <Trash2 className="w-3.5 h-3.5" /> إلغاء
            </button>
          </div>
        ))}
      </Section>

      <TeamMembersRoles Section={Section} inputCls={inputCls} inputSty={inputSty} />
    </div>
  );
}

// تحديث الجلسة/الدور من الخادم (GET /api/v1/me) — بعد أن يغيّر مشرفٌ دورَك،
// يُبطل الخادم جلستك؛ هذا الزرّ يجلب الدور الجديد فوراً بلا خروج/دخول. رسالة
// الخطأ (401 لو أُبطلت الجلسة فعلاً) تُعرَض بصدق كي يعيد المستخدم الدخول.
function SessionRefreshButton() {
  const refreshUser = useAuthStore(s => s.refreshUser);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const run = async () => {
    setBusy(true); setMsg('');
    try {
      await refreshUser();
      setMsg('حُدِّثت الجلسة');
    } catch (err: unknown) {
      setMsg(apiErrorMessage(err, 'تعذّر التحديث — قد تحتاج لإعادة الدخول'));
    } finally {
      setBusy(false);
      setTimeout(() => setMsg(''), 3000);
    }
  };
  return (
    <span className="inline-flex items-center gap-2">
      {msg && <span style={{ fontSize: 11, color: T.muted }}>{msg}</span>}
      <button type="button" onClick={run} disabled={busy}
        className="inline-flex items-center gap-1 px-2 py-1 rounded disabled:opacity-50"
        style={{ fontSize: 11, color: T.muted, border: `1px solid ${T.line}` }}>
        <RefreshCw className={`w-3 h-3 ${busy ? 'animate-spin' : ''}`} /> تحديث الجلسة
      </button>
    </span>
  );
}

// أعضاء الفريق + تغيير الأدوار — كان PATCH /auth/users/{id}/role بلا أيّ واجهة
// (الدعوات تحدّد الدور عند الدعوة فقط، وتغيير دور عضو قائم كان API-فقط).
// الخلفيّة admin-only + step-up MFA اختياريّ: عند 403 «يتطلّب رمز MFA» يظهر
// حقل الرمز ويُعاد الإرسال — لا تخمين ولا إخفاء لرسالة الخادم.
const ASSIGNABLE_ROLES: { value: AssignableRole; label: string }[] = [
  { value: 'viewer', label: 'مُشاهِد' },
  { value: 'farmer', label: 'مزارع/عامل' },
  { value: 'expert', label: 'خبير زراعيّ' },
  { value: 'admin',  label: 'مشرف' },
  { value: 'owner',  label: 'مالك' },
];

function TeamMembersRoles({ Section, inputCls, inputSty }: {
  Section: (p: { title?: string; children: React.ReactNode }) => React.JSX.Element;
  inputCls: string;
  inputSty: React.CSSProperties;
}) {
  const [users, setUsers] = useState<TeamUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState('');
  const [pending, setPending] = useState<Record<number, AssignableRole>>({});
  const [mfaCode, setMfaCode] = useState('');
  const [needsMfa, setNeedsMfa] = useState(false);
  const [rowMsg, setRowMsg] = useState<Record<number, string>>({});

  const refresh = async () => {
    setLoading(true); setListError('');
    try {
      setUsers(await listTeamUsers());
    } catch (err: unknown) {
      // 403 = الجلسة ليست admin في الخلفيّة — نُظهرها كما هي (لا إخفاء للقسم:
      // المشغّل يعرف أنّ القدرة موجودة ويتطلّب دور مشرف).
      setListError(apiErrorMessage(err, 'تعذّر جلب الأعضاء — يتطلّب دور مشرف (admin)'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); /* mount */ }, []);

  const deactivate = async (u: TeamUser) => {
    // تأكيد صريح: التعطيل يُبطل كلّ جلسات الحساب فوراً، ولا مسار «إعادة تفعيل»
    // في الخلفيّة (الاستعادة عبر مشغّل القاعدة) — يُقال ذلك قبل الفعل لا بعده.
    if (!window.confirm(`تعطيل حساب ${u.email}؟ يُبطل كلّ جلساته فوراً ولا إعادة تفعيل من الواجهة.`)) return;
    setRowMsg(m => ({ ...m, [u.id]: '…' }));
    try {
      const res = await deactivateUser(u.id, needsMfa && mfaCode.trim() ? mfaCode.trim() : undefined);
      setRowMsg(m => ({ ...m, [u.id]: res.message }));
      await refresh();
    } catch (err: unknown) {
      const msg = apiErrorMessage(err, 'تعذّر التعطيل');
      if (msg.includes('MFA')) setNeedsMfa(true);
      setRowMsg(m => ({ ...m, [u.id]: msg }));
    }
  };

  const applyRole = async (u: TeamUser) => {
    const newRole = pending[u.id];
    if (!newRole || newRole === u.role) return;
    setRowMsg(m => ({ ...m, [u.id]: '…' }));
    try {
      await changeUserRole(u.id, newRole, needsMfa && mfaCode.trim() ? mfaCode.trim() : undefined);
      setRowMsg(m => ({ ...m, [u.id]: 'غُيِّر الدور — أُبطلت جلساته ليسري فوراً' }));
      setNeedsMfa(false); setMfaCode('');
      await refresh();
    } catch (err: unknown) {
      const msg = apiErrorMessage(err, 'تعذّر تغيير الدور');
      // step-up MFA مُفعَّل: الخادم يطلب رمزاً حديثاً — أظهر الحقل وأعد المحاولة.
      if (msg.includes('MFA')) setNeedsMfa(true);
      setRowMsg(m => ({ ...m, [u.id]: msg }));
    }
  };

  return (
    <Section title="أعضاء الفريق وتغيير الأدوار">
      <p style={{ fontSize: 11, color: T.muted }}>
        تغيير الدور يسري فوراً (تُبطَل جلسات العضو ليُعاد تحميل دوره) ويُسجَّل في تدقيق
        الخادم. قد يتطلّب رمز MFA حديثاً من المشرف المنفِّذ (step-up) حسب إعداد البيئة.
      </p>
      <div className="flex items-center justify-between mb-1">
        <span style={{ fontSize: 12, color: T.muted }}>{users.length} عضواً</span>
        <button type="button" onClick={refresh}
          className="flex items-center gap-1 px-2 py-1 rounded"
          style={{ fontSize: 12, color: T.muted }}>
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> تحديث
        </button>
      </div>
      {listError && (
        <div className="p-3 rounded-xl text-sm" style={{ background: T.dangerBg, border: `1px solid ${T.danger}`, color: T.danger }}>
          {listError}
        </div>
      )}
      {needsMfa && (
        <div className="mb-2">
          <label className="block mb-1.5" style={{ fontSize: 13, color: T.brownSoft, fontWeight: 600 }}>
            رمز MFA الحديث (مطلوب لتغيير الأدوار في هذه البيئة)
          </label>
          <input value={mfaCode} onChange={e => setMfaCode(e.target.value)} inputMode="numeric"
            placeholder="123456" className={inputCls} style={{ ...inputSty, maxWidth: 180, direction: 'ltr' }} />
        </div>
      )}
      {users.map(u => (
        <div key={u.id} className="flex flex-wrap items-center gap-2 py-2"
          style={{ borderBottom: `1px solid ${T.line}` }}>
          <div className="min-w-0 flex-1">
            <div className="truncate" style={{ fontSize: 13, color: T.ink }}>
              {u.full_name || u.email}
              {!u.active && <span style={{ color: T.danger, fontSize: 11 }}> · مُعطَّل</span>}
            </div>
            <div className="truncate" style={{ fontSize: 11, color: T.muted, direction: 'ltr', textAlign: 'right' }}>{u.email}</div>
          </div>
          <select value={pending[u.id] ?? (u.role as AssignableRole)}
            onChange={e => setPending(p => ({ ...p, [u.id]: e.target.value as AssignableRole }))}
            className={inputCls} style={{ ...inputSty, width: 150 }}>
            {ASSIGNABLE_ROLES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <button type="button" onClick={() => applyRole(u)}
            disabled={!pending[u.id] || pending[u.id] === u.role}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-40"
            style={{ background: T.card2, border: `1px solid ${T.line}`, color: T.brownSoft }}>
            تطبيق
          </button>
          {u.active && (
            <button type="button" onClick={() => deactivate(u)}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold"
              style={{ background: T.dangerBg, border: `1px solid ${T.danger}`, color: T.danger }}>
              تعطيل
            </button>
          )}
          {rowMsg[u.id] && <span style={{ fontSize: 11, color: T.muted }}>{rowMsg[u.id]}</span>}
        </div>
      ))}
      {users.length === 0 && !loading && !listError && (
        <p className="py-2" style={{ fontSize: 12, color: T.muted }}>لا أعضاء بعد.</p>
      )}
    </Section>
  );
}

// ═══════════════════════════════════════════════════════════════
// AccountVerification — تأكيد البريد/الهاتف (تحقّق ناعم عبر OTP).
// تدفّق: اطلب رمزاً → أدخل ٦ أرقام → تأكيد ⇒ يُعلَّم الحساب verified_*.
// ربط حيّ مع auth-service (/auth/verify/*). التسليم STUB خادميّاً (سجلّ).
// الحالات صادقة عبر apiErrorMessage — لا حجب للدخول (تحقّق ناعم).
// ═══════════════════════════════════════════════════════════════
function AccountVerification({ Section, Row, inputCls, inputSty }: {
  Section: (p: { title?: string; children: React.ReactNode }) => React.ReactNode;
  Row: (p: { label: string; hint?: string; children: React.ReactNode }) => React.ReactNode;
  inputCls: string;
  inputSty: React.CSSProperties;
}) {
  const [status, setStatus] = useState<VerificationStatus | null>(null);
  // القناة التي يجري إدخال رمزها حاليّاً (null = لا تدفّق نشط).
  const [activeChannel, setActiveChannel] = useState<VerifyChannel | null>(null);
  const [code, setCode]     = useState('');
  const [busy, setBusy]     = useState(false);
  const [err, setErr]       = useState('');
  const [sentMsg, setSentMsg] = useState('');

  // جلب الحالة الحاليّة عند الفتح (إن تعذّر، نُكمل بحالة افتراضيّة غير متحقّقة).
  useEffect(() => {
    let alive = true;
    getVerificationStatus()
      .then(s => { if (alive) setStatus(s); })
      .catch(() => { if (alive) setStatus({ verified_email: false, verified_phone: false }); });
    return () => { alive = false; };
  }, []);

  const handleRequest = async (channel: VerifyChannel) => {
    setBusy(true); setErr(''); setSentMsg('');
    try {
      await requestVerification(channel);
      setActiveChannel(channel);
      setCode('');
      setSentMsg(channel === 'email'
        ? 'أُرسل رمز التحقّق إلى بريدك — قد يستغرق وصوله بضع دقائق'
        : 'أُرسل رمز التحقّق إلى هاتفك — قد يستغرق وصوله بضع دقائق');
    } catch (e) {
      setErr(apiErrorMessage(e, 'تعذّر إرسال رمز التحقّق'));
    } finally {
      setBusy(false);
    }
  };

  const handleConfirm = async () => {
    if (!activeChannel) return;
    if (code.trim().length !== 6) { setErr('أدخل الرمز المكوّن من ٦ أرقام'); return; }
    setBusy(true); setErr('');
    try {
      await confirmVerification(activeChannel, code.trim());
      setStatus(prev => ({
        verified_email: activeChannel === 'email' ? true : (prev?.verified_email ?? false),
        verified_phone: activeChannel === 'phone' ? true : (prev?.verified_phone ?? false),
      }));
      setActiveChannel(null);
      setCode('');
      setSentMsg('');
    } catch (e) {
      setErr(apiErrorMessage(e, 'رمز غير صالح أو منتهٍ'));
    } finally {
      setBusy(false);
    }
  };

  const errBox = (msg: string) => (
    <div className="flex items-center gap-2 p-2.5 rounded-lg text-xs" style={{ background: T.dangerBg, border: `1px solid ${T.danger}` }}>
      <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" style={{ color: T.danger }} />
      <span style={{ color: T.danger }}>{msg}</span>
    </div>
  );

  const channelRow = (channel: VerifyChannel, label: string, Icon: LucideIcon, verified: boolean) => (
    <div className="p-3 rounded-lg space-y-2" style={{ background: T.card2, border: `1px solid ${T.line}` }}>
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-sm" style={{ color: T.ink }}>
          <Icon className="w-4 h-4" style={{ color: T.muted }} /> {label}
        </span>
        {verified ? (
          <span className="flex items-center gap-1 text-xs" style={{ color: T.greenDark }}>
            <BadgeCheck className="w-4 h-4" /> مُتحقَّق منه
          </span>
        ) : (
          <span className="text-xs" style={{ color: T.warn }}>غير مُتحقَّق منه</span>
        )}
      </div>

      {!verified && activeChannel !== channel && (
        <Button full={false} onClick={() => handleRequest(channel)} disabled={busy} style={{ padding: '8px 12px', fontSize: 12 }}>
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Icon className="w-3.5 h-3.5" />}
          {channel === 'email' ? 'تأكيد البريد' : 'تأكيد الهاتف'}
        </Button>
      )}

      {!verified && activeChannel === channel && (
        <Row label="رمز التحقّق" hint="٦ أرقام، صالح ١٠ دقائق">
          <div className="flex gap-2">
            <input value={code}
              onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="123456" inputMode="numeric"
              className={inputCls + ' tracking-[0.3em] text-center'} style={inputSty} />
            <Button full={false} onClick={handleConfirm} disabled={busy} style={{ padding: '0 16px', whiteSpace: 'nowrap' }}>
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />} تأكيد
            </Button>
            <button onClick={() => handleRequest(channel)} disabled={busy}
              className="px-3 rounded-lg text-xs" style={{ border: `1px solid ${T.line}`, color: T.muted }}>
              إعادة إرسال
            </button>
          </div>
        </Row>
      )}
    </div>
  );

  return (
    <Section title="تأكيد البريد/الهاتف">
      <p style={{ fontSize: 11, color: T.muted }}>
        تحقّق ناعم لتعزيز ثقة الحساب — لا يحجب الدخول. سنرسل رمزاً مؤقّتاً (٦ أرقام) للقناة، ثمّ تؤكّده هنا.
      </p>
      {channelRow('email', 'البريد الإلكتروني', Mail, status?.verified_email ?? false)}
      {channelRow('phone', 'الهاتف', Phone, status?.verified_phone ?? false)}
      {sentMsg && (
        <div className="flex items-center gap-2 p-2.5 rounded-lg text-xs" style={{ background: T.infoBg, border: `1px solid ${T.info}`, color: T.info }}>
          <Mail className="w-3.5 h-3.5 flex-shrink-0" /> {sentMsg}
        </div>
      )}
      {err && errBox(err)}
    </Section>
  );
}

// ═══════════════════════════════════════════════════════════════
// AccountSecurity — أمان الحساب: تفعيل/تعطيل MFA + تغيير كلمة المرور
// ربط حيّ مع auth-service. لا fallback وهميّ — مسارات حسّاسة، الخطأ يُعرَض
// بصدق عبر apiErrorMessage. الأشكال تطابق services/auth/main.py.
// ═══════════════════════════════════════════════════════════════
function AccountSecurity({ Section, Row, inputCls, inputSty }: {
  Section: (p: { title?: string; children: React.ReactNode }) => React.ReactNode;
  Row: (p: { label: string; hint?: string; children: React.ReactNode }) => React.ReactNode;
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
    <div className="flex items-center gap-2 p-2.5 rounded-lg text-xs" style={{ background: T.dangerBg, border: `1px solid ${T.danger}` }}>
      <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" style={{ color: T.danger }} />
      <span style={{ color: T.danger }}>{msg}</span>
    </div>
  );
  const okBox = (msg: string) => (
    <div className="flex items-center gap-2 p-2.5 rounded-lg text-xs" style={{ background: T.okBg, border: `1px solid ${T.green}`, color: T.greenDark }}>
      <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" /> {msg}
    </div>
  );

  return (
    <>
      {/* ── MFA (TOTP) ──────────────────────────────────────── */}
      <Section title="المصادقة الثنائيّة (TOTP)">
        <p style={{ fontSize: 11, color: T.muted }}>
          طبقة حماية إضافيّة: عند الدخول يُطلب رمز مؤقّت من تطبيق مصادقة (Google Authenticator / Authy).
        </p>

        {mfaActivated && okBox('تم تفعيل المصادقة الثنائيّة بنجاح')}
        {disabledOk && okBox('تم تعطيل المصادقة الثنائيّة')}

        {/* بدء الاقتران */}
        {!setupData && !mfaActivated && (
          <Button full={false} onClick={handleSetup} disabled={mfaBusy} style={{ padding: '10px 16px' }}>
            {mfaBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
            بدء تفعيل المصادقة الثنائيّة
          </Button>
        )}

        {/* عرض السرّ + إدخال الرمز للتفعيل */}
        {setupData && (
          <div className="space-y-3">
            <div className="p-3 rounded-lg space-y-2" style={{ background: T.card2, border: `1px solid ${T.line}` }}>
              <p style={{ fontSize: 11, color: T.muted }}>امسح هذا الرابط كـ QR أو أدخل السرّ يدويّاً في تطبيق المصادقة. <span style={{ color: T.warn }}>يُعرَض مرّة واحدة فقط.</span></p>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-xs font-mono break-all" style={{ color: T.greenDark }}>{setupData.secret}</code>
                <button onClick={copySecret} className="flex items-center gap-1 px-2 py-1 rounded text-[11px]" style={{ border: `1px solid ${T.line}`, color: T.brownSoft }}>
                  {copied ? <Check className="w-3 h-3" style={{ color: T.green }} /> : <Copy className="w-3 h-3" />} {copied ? 'نُسخ' : 'نسخ'}
                </button>
              </div>
              <div className="text-[10px] font-mono break-all pt-2" style={{ color: T.faint, borderTop: `1px solid ${T.line}` }}>
                {setupData.provisioning_uri}
              </div>
            </div>
            <Row label="رمز التأكيد" hint="من تطبيق المصادقة">
              <div className="flex gap-2">
                <input value={activateCode}
                  onChange={e => setActivateCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="123456" inputMode="numeric"
                  className={inputCls + ' tracking-[0.3em] text-center'} style={inputSty} />
                <Button full={false} onClick={handleActivate} disabled={mfaBusy} style={{ padding: '0 16px', whiteSpace: 'nowrap' }}>
                  {mfaBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />} تفعيل
                </Button>
              </div>
            </Row>
          </div>
        )}

        {mfaErr && errBox(mfaErr)}

        {/* تعطيل MFA */}
        <div className="pt-3" style={{ borderTop: `1px solid ${T.line}` }}>
          {!showDisable ? (
            <button onClick={() => { setShowDisable(true); setDisableErr(''); setDisabledOk(false); }}
              className="text-xs" style={{ color: T.muted }}>
              تعطيل المصادقة الثنائيّة (إن كانت مفعّلة)
            </button>
          ) : (
            <div className="space-y-2">
              <p style={{ fontSize: 11, color: T.muted }}>أدخل رمزاً صحيحاً حاليّاً لتأكيد التعطيل.</p>
              <div className="flex gap-2">
                <input value={disableCode}
                  onChange={e => setDisableCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="123456" inputMode="numeric"
                  className={inputCls + ' tracking-[0.3em] text-center'} style={inputSty} />
                <button onClick={handleDisable} disabled={disableBusy}
                  className="flex items-center gap-1.5 px-4 rounded-lg text-sm font-medium text-white whitespace-nowrap"
                  style={{ background: disableBusy ? '#7f1d1d' : T.danger, opacity: disableBusy ? 0.8 : 1 }}>
                  {disableBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : null} تعطيل
                </button>
                <button onClick={() => setShowDisable(false)}
                  className="px-3 rounded-lg text-xs" style={{ border: `1px solid ${T.line}`, color: T.muted }}>إلغاء</button>
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
            <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: T.faint }} />
          </div>
        </Row>
        <Row label="كلمة المرور الجديدة" hint="8 أحرف، حرف كبير، رقم، رمز">
          <div className="relative">
            <input type={showPw ? 'text' : 'password'} value={newPw} onChange={e => setNewPw(e.target.value)}
              placeholder="••••••••" autoComplete="new-password"
              className={inputCls + ' pl-10'} style={inputSty} />
            <button type="button" onClick={() => setShowPw(!showPw)}
              className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: T.muted }}>
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
          <Button full={false} onClick={handleChangePw} disabled={pwBusy} style={{ padding: '10px 20px' }}>
            {pwBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />} تحديث كلمة المرور
          </Button>
        </div>
      </Section>
    </>
  );
}
