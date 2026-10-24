import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { CallApi } from './api';
import { CallController } from './controller';
import { livekitMedia } from './livekit-room';
import './call.css';
export function CallApp() {
  const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [mfa, setMfa] = useState(''); const [mfaRequired, setMfaRequired] = useState(false);
  const [authenticated, setAuthenticated] = useState(false); const [field, setField] = useState('');
  const [consent, setConsent] = useState(false); const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false); const [status, setStatus] = useState('');
  const api = useMemo(() => new CallApi(), []);
  const controller = useMemo(() => new CallController(api, livekitMedia, value => { setStatus(value); if (value === 'انتهت الجلسة') setConnected(false); }), [api]);
  useEffect(() => {
    const hide = () => { void controller.leave(true); api.clear(); setAuthenticated(false); setConnected(false); };
    const blur = () => controller.mute();
    window.addEventListener('pagehide', hide); window.addEventListener('blur', blur);
    return () => { window.removeEventListener('pagehide', hide); window.removeEventListener('blur', blur); void controller.leave(); api.clear(); };
  }, [api, controller]);
  if (import.meta.env.VITE_REALTIME_CALL_ENABLED !== 'true') return <main dir="rtl"><h1>المكالمات غير مفعلة</h1><a href="/">العودة إلى سهول</a></main>;
  if (window.top !== window.self) return <main>يلزم فتح صفحة الاتصال مستقلة.</main>;
  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true);
    try { await api.login(email, password, mfa); setAuthenticated(true); setPassword(''); setMfa(''); setStatus('تم تسجيل الدخول'); }
    catch (error) { const message = (error as Error).message; setMfaRequired(message === 'MFA_REQUIRED'); setStatus(message === 'MFA_REQUIRED' ? 'أدخل رمز المصادقة الثنائية' : message); }
    finally { setBusy(false); }
  }
  async function join(event: FormEvent) {
    event.preventDefault(); if (!consent || !field.trim()) return; setBusy(true);
    try { setConnected(await controller.join(field.trim())); } catch { setStatus('تعذّر الاتصال؛ تحقق من صلاحية الحقل والخدمة'); } finally { setBusy(false); }
  }
  return <main dir="rtl"><h1>مكالمة المستشار الزراعي</h1><p>صوت فقط · استشارة للقراءة · دون تشغيل معدات</p>
    {!authenticated ? <form onSubmit={login}>
      <p>سجّل الدخول لهذه الصفحة. لا تُنقل رموز الجلسة من واجهة أخرى.</p>
      <label>البريد الإلكتروني<input type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required /></label>
      <label>كلمة المرور<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
      {mfaRequired && <label>رمز المصادقة الثنائية<input inputMode="numeric" autoComplete="one-time-code" value={mfa} onChange={e => setMfa(e.target.value.replace(/\D/g, '').slice(0, 6))} required /></label>}
      <button disabled={busy}>تسجيل الدخول</button>
    </form> : <form onSubmit={join}>
      <label>معرّف الحقل<input value={field} maxLength={128} onChange={e => setField(e.target.value)} required disabled={connected} /></label>
      <label className="consent"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} disabled={connected} />أوافق على تحويل صوتي إلى نص ومعالجته للاستشارة. يُحفظ السؤال والجواب ضمن سجل تدقيق سهول وفق سياسة المستأجر. لا تُسجّل هذه الميزة المكالمة.</label>
      <button disabled={!consent || busy || connected}>إنشاء جلسة صوتية (حتى 5 دقائق)</button>
    </form>}
    {connected && <section><button onClick={() => { void controller.enableMicrophone().catch(() => setStatus('تعذّر فتح الميكروفون')); }}>تشغيل الميكروفون</button><button onClick={() => { controller.mute(); setStatus('الميكروفون مغلق'); }}>كتم</button><button onClick={() => { setConnected(false); void controller.leave(); }}>إنهاء المكالمة</button></section>}
    <p role="status" aria-live="polite">{status}</p><a href="/" onClick={() => { void controller.leave(true); api.clear(); }}>العودة إلى سهول وإنهاء المكالمة</a>
  </main>;
}
