// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — sections/NotificationSettingsPage.tsx
// إعدادات الإشعارات الكاملة:
//   ✅ بريد إلكتروني + تلغرام + Push + Webhook
//   ✅ اختيار أنواع الأحداث
//   ✅ اختبار الاتصال (Test notification)
//   ✅ حفظ في DB عبر API
//   ✅ WebSocket status badge
// ═══════════════════════════════════════════════════════════════
import { useState, useEffect } from 'react';
import {
  Bell, Mail, Send, Smartphone, Globe, Check, X,
  Loader2, RefreshCw, Wifi, WifiOff, TestTube, Shield,
} from 'lucide-react';
import { wsService, toastStore } from '../services/websocket';
import { kongApi } from '../services/api';

interface Prefs {
  email_enabled:     boolean;
  email_address:     string;
  telegram_enabled:  boolean;
  telegram_chat_id:  string;
  push_enabled:      boolean;
  push_device_token: string;
  webhook_enabled:   boolean;
  webhook_url:       string;
  event_types:       string[];
}

const DEFAULT_PREFS: Prefs = {
  email_enabled:true, email_address:'',
  telegram_enabled:false, telegram_chat_id:'',
  push_enabled:false, push_device_token:'',
  webhook_enabled:false, webhook_url:'',
  event_types:['satellite','weather_alert','pest_alert','irrigation_rec','fertilizer_rec','low_stock'],
};

const EVENTS = [
  { value:'satellite',       label:'صورة قمر صناعي جديدة', emoji:'🛰️' },
  { value:'weather_alert',   label:'تنبيهات الطقس القاسي', emoji:'🌩️' },
  { value:'pest_alert',      label:'آفات وأمراض',           emoji:'🐛' },
  { value:'irrigation_rec',  label:'توصيات الري',            emoji:'💧' },
  { value:'fertilizer_rec',  label:'توصيات التسميد',         emoji:'🌱' },
  { value:'low_stock',       label:'مخزون منخفض',           emoji:'📦' },
  { value:'task_assigned',   label:'مهام ميدانية جديدة',    emoji:'✅' },
  { value:'economic_analysis',label:'تحليل اقتصادي',        emoji:'💰' },
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
}: any) {
  return (
    <div className="rounded-xl border overflow-hidden" style={{ background:'#1e293b', borderColor:'#334155' }}>
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background:'#334155' }}>
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
        <div className="px-4 pb-4 border-t" style={{ borderColor:'#334155' }}>
          {children}
        </div>
      )}
    </div>
  );
}

export default function NotificationSettingsPage() {
  const [prefs,    setPrefs]   = useState<Prefs>(DEFAULT_PREFS);
  const [loading,  setLoading]  = useState(true);
  const [saving,   setSaving]   = useState(false);
  const [testing,  setTesting]  = useState(false);
  const [saved,    setSaved]    = useState(false);
  const [wsOk,     setWsOk]     = useState(wsService.isConnected());

  useEffect(() => {
    // جلب التفضيلات
    kongApi.get('/notifications/preferences').then(r => {
      if (r.data) setPrefs({ ...DEFAULT_PREFS, ...r.data });
    }).catch(() => {}).finally(() => setLoading(false));

    // WS status
    const interval = setInterval(() => setWsOk(wsService.isConnected()), 3000);
    return () => clearInterval(interval);
  }, []);

  const update = (key: keyof Prefs, val: any) =>
    setPrefs(p => ({ ...p, [key]: val }));

  const toggleEvent = (ev: string) =>
    setPrefs(p => ({
      ...p,
      event_types: p.event_types.includes(ev)
        ? p.event_types.filter(e => e !== ev)
        : [...p.event_types, ev],
    }));

  const handleSave = async () => {
    setSaving(true);
    try {
      await kongApi.put('/notifications/preferences', prefs);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
      toastStore.add('success', '✅ تم الحفظ', 'تم حفظ إعدادات الإشعارات');
    } catch {
      toastStore.add('error', '❌ خطأ', 'فشل حفظ الإعدادات');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      await kongApi.post('/notifications/test', { event_types: prefs.event_types });
      toastStore.add('info', '🔔 اختبار', 'تم إرسال إشعار تجريبي عبر جميع القنوات المفعّلة');
    } catch {
      toastStore.add('error', '❌ فشل الاختبار', 'تحقق من إعدادات الاتصال');
    } finally {
      setTesting(false);
    }
  };

  const requestBrowserPermission = async () => {
    const ok = await wsService.requestNotificationPermission();
    toastStore.add(ok ? 'success' : 'warning',
      ok ? '✅ مسموح' : '⚠️ مرفوض',
      ok ? 'إشعارات المتصفح مفعّلة' : 'يرجى السماح بالإشعارات في إعدادات المتصفح');
  };

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="w-6 h-6 text-emerald-500 animate-spin" />
    </div>
  );

  return (
    <div className="space-y-5 max-w-2xl mx-auto" dir="rtl">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Bell className="w-5 h-5 text-emerald-400" /> إعدادات الإشعارات
          </h2>
          <p className="text-sm text-slate-400 mt-0.5">تلقّى تنبيهات فورية عبر قناتك المفضلة</p>
        </div>
        <div className="flex items-center gap-2">
          {/* WS Status */}
          <span className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] border ${wsOk ? 'bg-emerald-950 text-emerald-400 border-emerald-900' : 'bg-slate-800 text-slate-500 border-slate-700'}`}>
            {wsOk ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
            WebSocket {wsOk ? 'متصل' : 'غير متصل'}
          </span>
        </div>
      </div>

      {/* Channels */}
      <Channel icon={Mail} title="البريد الإلكتروني" desc="SMTP — مرسل لكل تنبيه حرج"
        enabled={prefs.email_enabled} onToggle={(v: boolean) => update('email_enabled', v)}>
        <div className="pt-3">
          <label className="block text-xs text-slate-400 mb-1">عنوان البريد</label>
          <input value={prefs.email_address} onChange={e => update('email_address', e.target.value)}
            type="email" placeholder="you@example.com"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }} />
        </div>
      </Channel>

      <Channel icon={Send} title="Telegram" desc="بوت مجاني وفوري"
        enabled={prefs.telegram_enabled} onToggle={(v: boolean) => update('telegram_enabled', v)}>
        <div className="pt-3 space-y-2">
          <label className="block text-xs text-slate-400 mb-1">
            Chat ID — احصل عليه من <a href="https://t.me/userinfobot" target="_blank" rel="noreferrer" className="text-blue-400 hover:underline">@userinfobot</a>
          </label>
          <input value={prefs.telegram_chat_id} onChange={e => update('telegram_chat_id', e.target.value)}
            placeholder="123456789"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }} />
        </div>
      </Channel>

      <Channel icon={Smartphone} title="تطبيق الجوال (Push)" desc="Firebase FCM"
        enabled={prefs.push_enabled} onToggle={(v: boolean) => update('push_enabled', v)}>
        <div className="pt-3">
          <label className="block text-xs text-slate-400 mb-1">رمز الجهاز (Device Token)</label>
          <input value={prefs.push_device_token} onChange={e => update('push_device_token', e.target.value)}
            placeholder="FCM token يُولَّد تلقائياً من التطبيق"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }} />
        </div>
      </Channel>

      <Channel icon={Globe} title="Webhook (للمطورين)" desc="HTTP POST عند كل حدث"
        enabled={prefs.webhook_enabled} onToggle={(v: boolean) => update('webhook_enabled', v)}>
        <div className="pt-3">
          <label className="block text-xs text-slate-400 mb-1">عنوان Webhook</label>
          <input value={prefs.webhook_url} onChange={e => update('webhook_url', e.target.value)}
            placeholder="https://your-server.com/webhook"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }} />
        </div>
      </Channel>

      {/* Browser notifications */}
      <div className="rounded-xl p-4 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
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
            style={{ background:'#1e3a1e', border:'1px solid #16a34a44' }}>
            طلب الإذن
          </button>
        </div>
      </div>

      {/* Event types */}
      <div className="rounded-xl p-4 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
        <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2">
          <Shield className="w-4 h-4 text-emerald-400" /> أنواع الإشعارات المطلوبة
        </h3>
        <div className="grid grid-cols-2 gap-2">
          {EVENTS.map(ev => {
            const active = prefs.event_types.includes(ev.value);
            return (
              <button key={ev.value} onClick={() => toggleEvent(ev.value)}
                className="flex items-center gap-2 p-2.5 rounded-lg text-sm transition-all text-right"
                style={{ background: active ? '#1e3a1e' : '#0f1117', border:`1px solid ${active ? '#16a34a44' : '#334155'}`, color: active ? '#4ade80' : '#64748b' }}>
                <span className="text-base">{ev.emoji}</span>
                <span className="flex-1">{ev.label}</span>
                {active && <Check className="w-3.5 h-3.5 flex-shrink-0" />}
              </button>
            );
          })}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3 justify-between flex-wrap">
        <button onClick={handleTest} disabled={testing}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm border text-slate-400 hover:text-slate-200 transition-colors"
          style={{ borderColor:'#334155' }}>
          {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <TestTube className="w-4 h-4" />}
          إرسال إشعار تجريبي
        </button>
        <button onClick={handleSave} disabled={saving}
          className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white transition-colors"
          style={{ background: saved ? '#15803d' : '#16a34a' }}>
          {saving ? <><Loader2 className="w-4 h-4 animate-spin" /> جاري الحفظ...</>
           : saved ? <><Check className="w-4 h-4" /> تم الحفظ ✓</>
           : <><Check className="w-4 h-4" /> حفظ الإعدادات</>}
        </button>
      </div>
    </div>
  );
}
