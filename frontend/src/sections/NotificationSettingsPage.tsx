// ═══════════════════════════════════════════════════════════════
// SAHOOL — sections/NotificationSettingsPage.tsx
// إعدادات قنوات تسليم التنبيهات (ربط حيّ، بلا تلفيق):
//   ✅ بريد إلكتروني + SMS + Push + واتساب (تفعيل + عنوان لكلّ قناة)
//   ✅ أرضيّة خطورة دنيا (info/warning/critical)
//   ✅ اختيار أنواع الأحداث المُشترَك بها
//   ✅ قراءة/حفظ فعليّ عبر GET/PUT /api/v1/notifications/preferences
//   ✅ حالات صادقة: تحميل/خطأ/حفظ — لا fallback وهميّ
//   ملاحظة: أرضيّة SMS/واتساب الافتراضيّة 'critical' خادميّاً (قناة مكلفة).
// ═══════════════════════════════════════════════════════════════
import { useState, useEffect } from 'react';
import {
  Bell, Mail, MessageSquare, Smartphone, Phone, Check,
  Loader2, AlertTriangle, RefreshCw, Wifi, WifiOff, Shield,
} from 'lucide-react';
import { wsService, toastStore } from '../services/websocket';
import {
  useNotificationPreferences, useUpdateNotificationPreferences,
} from '../hooks/useApi';
import type { NotificationPreferences } from '../services/api';

type Severity = 'info' | 'warning' | 'critical';

const DEFAULT_PREFS: NotificationPreferences = {
  email_enabled:    false, email_address:    '',
  sms_enabled:      false, sms_number:       '',
  push_enabled:     false, push_token:       '',
  whatsapp_enabled: false, whatsapp_number:  '',
  event_types:      ['weather_alert', 'pest_alert', 'disease_risk', 'frost_risk'],
  min_severity:     null,
};

const EVENTS: { value: string; label: string; emoji: string }[] = [
  { value: 'weather_alert',   label: 'تنبيهات الطقس القاسي', emoji: '🌩️' },
  { value: 'pest_alert',      label: 'آفات',                 emoji: '🐛' },
  { value: 'disease_risk',    label: 'خطر مرض',              emoji: '🦠' },
  { value: 'low_moisture',    label: 'رطوبة منخفضة',         emoji: '💧' },
  { value: 'heavy_rain',      label: 'أمطار غزيرة',          emoji: '🌧️' },
  { value: 'heat_stress',     label: 'إجهاد حراريّ',         emoji: '🌡️' },
  { value: 'frost_risk',      label: 'خطر صقيع',             emoji: '❄️' },
  { value: 'irrigation_rec',  label: 'توصيات الري',          emoji: '🚿' },
  { value: 'fertilizer_rec',  label: 'توصيات التسميد',       emoji: '🌱' },
  { value: 'low_stock',       label: 'مخزون منخفض',          emoji: '📦' },
  { value: 'task_assigned',   label: 'مهام ميدانية',         emoji: '✅' },
  { value: 'satellite',       label: 'صورة قمر صناعي',       emoji: '🛰️' },
];

const SEVERITIES: { value: Severity | ''; label: string }[] = [
  { value: '',         label: 'كلّ الدرجات (افتراضيّ القناة)' },
  { value: 'info',     label: 'معلومة فأعلى' },
  { value: 'warning',  label: 'تحذير فأعلى' },
  { value: 'critical', label: 'حرِج فقط' },
];

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
      className="relative inline-flex h-5 w-9 items-center rounded-full transition-colors flex-shrink-0"
      style={{ background: checked ? '#16a34a' : '#475569' }}>
      <span className="inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform"
        style={{ transform: checked ? 'translateX(18px)' : 'translateX(2px)' }} />
    </button>
  );
}

function Channel({
  icon: Icon, title, desc, enabled, onToggle, children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string; desc: string; enabled: boolean;
  onToggle: (v: boolean) => void; children?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border overflow-hidden" style={{ background: '#1e293b', borderColor: '#334155' }}>
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: '#334155' }}>
            <Icon className="w-4 h-4 text-slate-300" />
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-200">{title}</div>
            <div className="text-xs text-slate-500">{desc}</div>
          </div>
        </div>
        <Toggle checked={enabled} onChange={onToggle} />
      </div>
      {enabled && children && (
        <div className="px-4 pb-4 border-t" style={{ borderColor: '#334155' }}>
          {children}
        </div>
      )}
    </div>
  );
}

function TextField({
  value, onChange, type = 'text', placeholder, label,
}: { value: string; onChange: (v: string) => void; type?: string; placeholder?: string; label: string }) {
  return (
    <div className="pt-3">
      <label className="block text-xs text-slate-400 mb-1">{label}</label>
      <input value={value} onChange={e => onChange(e.target.value)} type={type} placeholder={placeholder}
        className="w-full px-3 py-2 rounded-lg text-sm"
        style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
    </div>
  );
}

export default function NotificationSettingsPage() {
  const prefsQuery = useNotificationPreferences();
  const saveMutation = useUpdateNotificationPreferences();

  const [prefs, setPrefs] = useState<NotificationPreferences>(DEFAULT_PREFS);
  const [saved, setSaved] = useState(false);
  const [wsOk, setWsOk] = useState(wsService.isConnected());

  // عند وصول التفضيلات من الخادم — نملأ النموذج (مع تطبيع null → '').
  useEffect(() => {
    if (prefsQuery.data) {
      const d = prefsQuery.data;
      setPrefs({
        email_enabled:    d.email_enabled,
        email_address:    d.email_address ?? '',
        sms_enabled:      d.sms_enabled,
        sms_number:       d.sms_number ?? '',
        push_enabled:     d.push_enabled,
        push_token:       d.push_token ?? '',
        whatsapp_enabled: d.whatsapp_enabled,
        whatsapp_number:  d.whatsapp_number ?? '',
        event_types:      d.event_types ?? [],
        min_severity:     d.min_severity ?? null,
      });
    }
  }, [prefsQuery.data]);

  useEffect(() => {
    const interval = setInterval(() => setWsOk(wsService.isConnected()), 3000);
    return () => clearInterval(interval);
  }, []);

  const update = <K extends keyof NotificationPreferences>(key: K, val: NotificationPreferences[K]) =>
    setPrefs(p => ({ ...p, [key]: val }));

  const toggleEvent = (ev: string) =>
    setPrefs(p => ({
      ...p,
      event_types: p.event_types.includes(ev)
        ? p.event_types.filter(e => e !== ev)
        : [...p.event_types, ev],
    }));

  const handleSave = () => {
    // نُحوّل العناوين الفارغة إلى null (الخادم يقبل null؛ يبقى صادقاً عن «غير مضبوط»).
    const payload: NotificationPreferences = {
      ...prefs,
      email_address:   prefs.email_address?.trim()   || null,
      sms_number:      prefs.sms_number?.trim()       || null,
      push_token:      prefs.push_token?.trim()       || null,
      whatsapp_number: prefs.whatsapp_number?.trim()  || null,
    };
    saveMutation.mutate(payload, {
      onSuccess: () => {
        setSaved(true);
        setTimeout(() => setSaved(false), 2500);
        toastStore.add('success', 'تم الحفظ', 'تم حفظ إعدادات الإشعارات');
      },
      onError: () => {
        toastStore.add('error', 'خطأ', 'فشل حفظ الإعدادات — تحقّق من الاتصال/الصلاحيّة');
      },
    });
  };

  const requestBrowserPermission = async () => {
    const ok = await wsService.requestNotificationPermission();
    toastStore.add(ok ? 'success' : 'warning',
      ok ? 'مسموح' : 'مرفوض',
      ok ? 'إشعارات المتصفح مفعّلة' : 'يرجى السماح بالإشعارات في إعدادات المتصفح');
  };

  // ── حالات صادقة: تحميل / خطأ ──────────────────────────────────
  if (prefsQuery.isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 text-emerald-500 animate-spin" />
      </div>
    );
  }

  if (prefsQuery.isError) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 text-center" dir="rtl">
        <AlertTriangle className="w-8 h-8 text-amber-500" />
        <div className="text-slate-300 text-sm">تعذّر تحميل إعدادات الإشعارات</div>
        <div className="text-slate-500 text-xs max-w-sm">
          قد تكون قاعدة البيانات غير متاحة أو لا تملك صلاحيّة العرض.
        </div>
        <button onClick={() => prefsQuery.refetch()}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm border text-slate-300 hover:text-white"
          style={{ borderColor: '#334155' }}>
          <RefreshCw className="w-4 h-4" /> إعادة المحاولة
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-5 max-w-2xl mx-auto" dir="rtl">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Bell className="w-5 h-5 text-emerald-400" /> إعدادات الإشعارات
          </h2>
          <p className="text-sm text-slate-400 mt-0.5">قنوات تسليم التنبيهات وأنواع الأحداث</p>
        </div>
        <span className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] border ${wsOk ? 'bg-emerald-950 text-emerald-400 border-emerald-900' : 'bg-slate-800 text-slate-500 border-slate-700'}`}>
          {wsOk ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
          WebSocket {wsOk ? 'متصل' : 'غير متصل'}
        </span>
      </div>

      {/* Channels */}
      <Channel icon={Mail} title="البريد الإلكتروني" desc="يستقبل كلّ الدرجات افتراضيّاً"
        enabled={prefs.email_enabled} onToggle={(v: boolean) => update('email_enabled', v)}>
        <TextField label="عنوان البريد" type="email" placeholder="you@example.com"
          value={prefs.email_address ?? ''} onChange={v => update('email_address', v)} />
      </Channel>

      <Channel icon={MessageSquare} title="رسالة نصّيّة (SMS)" desc="التنبيهات الحرِجة فقط (مكلفة)"
        enabled={prefs.sms_enabled} onToggle={(v: boolean) => update('sms_enabled', v)}>
        <TextField label="رقم الهاتف" type="tel" placeholder="+9677xxxxxxxx"
          value={prefs.sms_number ?? ''} onChange={v => update('sms_number', v)} />
      </Channel>

      <Channel icon={Smartphone} title="تطبيق الجوال (Push)" desc="يستقبل كلّ الدرجات افتراضيّاً"
        enabled={prefs.push_enabled} onToggle={(v: boolean) => update('push_enabled', v)}>
        <TextField label="رمز الجهاز (Device Token)" placeholder="FCM token يُولَّد تلقائياً من التطبيق"
          value={prefs.push_token ?? ''} onChange={v => update('push_token', v)} />
      </Channel>

      <Channel icon={Phone} title="واتساب (WhatsApp)" desc="التنبيهات الحرِجة فقط"
        enabled={prefs.whatsapp_enabled} onToggle={(v: boolean) => update('whatsapp_enabled', v)}>
        <TextField label="رقم واتساب" type="tel" placeholder="+9677xxxxxxxx"
          value={prefs.whatsapp_number ?? ''} onChange={v => update('whatsapp_number', v)} />
      </Channel>

      {/* Browser notifications */}
      <div className="rounded-xl p-4 border" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Bell className="w-4 h-4 text-slate-300" />
            <div>
              <div className="text-sm font-semibold text-slate-200">إشعارات المتصفح</div>
              <div className="text-xs text-slate-500">تظهر حتى لو الصفحة في الخلفية</div>
            </div>
          </div>
          <button onClick={requestBrowserPermission}
            className="px-3 py-1.5 rounded-lg text-xs font-medium text-emerald-400 hover:text-emerald-300"
            style={{ background: '#1e3a1e', border: '1px solid #16a34a44' }}>
            طلب الإذن
          </button>
        </div>
      </div>

      {/* Min severity */}
      <div className="rounded-xl p-4 border" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <h3 className="text-sm font-semibold text-slate-200 mb-2 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-400" /> أدنى درجة خطورة
        </h3>
        <p className="text-xs text-slate-500 mb-3">حدّ أدنى عامّ يُطبَّق فوق أرضيّة كلّ قناة (لا يخفّضها).</p>
        <select value={prefs.min_severity ?? ''}
          onChange={e => update('min_severity', (e.target.value || null) as Severity | null)}
          className="w-full px-3 py-2 rounded-lg text-sm"
          style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
          {SEVERITIES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </div>

      {/* Event types */}
      <div className="rounded-xl p-4 border" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2">
          <Shield className="w-4 h-4 text-emerald-400" /> أنواع الإشعارات المطلوبة
        </h3>
        <div className="grid grid-cols-2 gap-2">
          {EVENTS.map(ev => {
            const active = prefs.event_types.includes(ev.value);
            return (
              <button key={ev.value} onClick={() => toggleEvent(ev.value)}
                className="flex items-center gap-2 p-2.5 rounded-lg text-sm transition-all text-right"
                style={{ background: active ? '#1e3a1e' : '#0f1117', border: `1px solid ${active ? '#16a34a44' : '#334155'}`, color: active ? '#4ade80' : '#64748b' }}>
                <span className="text-base">{ev.emoji}</span>
                <span className="flex-1">{ev.label}</span>
                {active && <Check className="w-3.5 h-3.5 flex-shrink-0" />}
              </button>
            );
          })}
        </div>
      </div>

      {/* Save */}
      <div className="flex justify-end">
        <button onClick={handleSave} disabled={saveMutation.isPending}
          className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white transition-colors disabled:opacity-60"
          style={{ background: saved ? '#15803d' : '#16a34a' }}>
          {saveMutation.isPending ? <><Loader2 className="w-4 h-4 animate-spin" /> جاري الحفظ...</>
            : saved ? <><Check className="w-4 h-4" /> تم الحفظ</>
              : <><Check className="w-4 h-4" /> حفظ الإعدادات</>}
        </button>
      </div>
    </div>
  );
}
