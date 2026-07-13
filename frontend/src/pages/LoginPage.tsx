// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — LoginPage.tsx
// صفحة تسجيل الدخول: email + password + demo mode
// ✅ رمز MFA (TOTP) يظهر عند طلب الخادم له (X-MFA-Required)
// ✅ تدفّق "نسيت كلمة المرور؟": طلب بالبريد → رمز + كلمة مرور جديدة → تأكيد
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Leaf, Eye, EyeOff, Loader2, Shield, AlertTriangle, KeyRound, ArrowRight, CheckCircle2 } from 'lucide-react';
import { useAuthStore } from '../hooks/useAuth';
import { requestPasswordReset, confirmPasswordReset, apiErrorMessage, isMfaRequiredError } from '../services/api';

// شاشات هذه الصفحة: الدخول، أو تدفّق إعادة التعيين (طلب ثمّ تأكيد).
type View = 'login' | 'reset-request' | 'reset-confirm';

export default function LoginPage({ onSignup }: { onSignup?: () => void }) {
  const [view, setView]       = useState<View>('login');
  const [email, setEmail]     = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw]   = useState(false);
  const [error, setError]     = useState('');
  const [loading, setLoading] = useState(false);
  // MFA: يظهر الحقل فقط بعد أن يطلبه الخادم (كلمة المرور صحّت، يلزم رمز).
  const [mfaRequired, setMfaRequired] = useState(false);
  const [mfaCode, setMfaCode] = useState('');
  const { login, loginDemo }  = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) { setError('أدخل البريد وكلمة المرور'); return; }
    if (mfaRequired && !mfaCode.trim()) { setError('أدخل رمز المصادقة الثنائيّة'); return; }
    setLoading(true); setError('');
    try {
      await login(email, password, mfaRequired ? mfaCode.trim() : undefined);
    } catch (err: unknown) {
      // الخادم يردّ 401 + X-MFA-Required حين تصحّ كلمة المرور لكن يلزم رمز TOTP.
      if (!mfaRequired && isMfaRequiredError(err)) {
        setMfaRequired(true);
        setError('هذا الحساب محميّ بالمصادقة الثنائيّة — أدخل الرمز من تطبيق المصادقة');
      } else {
        setError(apiErrorMessage(err, 'فشل تسجيل الدخول'));
      }
    } finally {
      setLoading(false);
    }
  };

  const fieldStyle = { background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0', outline:'none' } as const;

  return (
    <div className="min-h-screen flex items-center justify-center p-4 dir-rtl"
      style={{ background:'linear-gradient(135deg, #0f1117 0%, #0d2010 50%, #0f1117 100%)' }}>

      {/* Background decoration */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 right-1/4 w-96 h-96 rounded-full opacity-5"
          style={{ background:'radial-gradient(circle, #16a34a, transparent)' }} />
        <div className="absolute bottom-1/4 left-1/4 w-64 h-64 rounded-full opacity-5"
          style={{ background:'radial-gradient(circle, #0ea5e9, transparent)' }} />
      </div>

      <div className="relative w-full max-w-md">
        {/* Card */}
        <div className="rounded-2xl p-8 border" style={{ background:'#1e293b', borderColor:'#334155', boxShadow:'0 25px 50px rgba(0,0,0,0.5)' }}>

          {/* Logo */}
          <div className="text-center mb-8">
            <div className="w-16 h-16 rounded-2xl bg-emerald-600 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-emerald-900/50">
              <Leaf className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-slate-100">سهول</h1>
            <p className="text-slate-400 text-sm mt-1">منصة الزراعة الذكية اليمنية</p>
          </div>

          {/* ── Login view ───────────────────────────────────────── */}
          {view === 'login' && (
          <form onSubmit={handleSubmit} className="space-y-4" dir="rtl">
            {/* Email */}
            <div>
              <label className="block text-sm text-slate-400 mb-1.5">البريد الإلكتروني</label>
              <input
                type="email" value={email} onChange={e => setEmail(e.target.value)}
                placeholder="admin@sahool.ye"
                className="w-full px-4 py-3 rounded-xl text-sm"
                style={fieldStyle}
                autoComplete="email"
              />
            </div>

            {/* Password */}
            <div>
              <label className="block text-sm text-slate-400 mb-1.5">كلمة المرور</label>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'} value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-4 py-3 pl-11 rounded-xl text-sm"
                  style={fieldStyle}
                  autoComplete="current-password"
                />
                <button type="button" onClick={() => setShowPw(!showPw)}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200">
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* MFA code (يظهر فقط حين يطلبه الخادم) */}
            {mfaRequired && (
              <div>
                <label className="block text-sm text-slate-400 mb-1.5 flex items-center gap-1.5">
                  <Shield className="w-3.5 h-3.5 text-emerald-400" /> رمز المصادقة الثنائيّة (TOTP)
                </label>
                <input
                  value={mfaCode} onChange={e => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="123456" inputMode="numeric" autoComplete="one-time-code" autoFocus
                  className="w-full px-4 py-3 rounded-xl text-sm tracking-[0.4em] text-center"
                  style={fieldStyle}
                />
                <p className="text-[11px] text-slate-500 mt-1">من تطبيق المصادقة (Google Authenticator / Authy)</p>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="flex items-center gap-2 p-3 rounded-xl text-sm" style={{ background:'#1a0000', border:'1px solid #dc262633' }}>
                <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                <span className="text-red-300">{error}</span>
              </div>
            )}

            {/* Submit */}
            <button type="submit" disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all"
              style={{ background: loading ? '#15803d' : '#16a34a', color:'white', opacity: loading ? 0.8 : 1 }}>
              {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> جاري الدخول...</> : 'تسجيل الدخول'}
            </button>

            {/* Forgot password */}
            <div className="text-center">
              <button type="button"
                onClick={() => { setView('reset-request'); setError(''); }}
                className="text-xs text-slate-400 hover:text-emerald-400">
                نسيت كلمة المرور؟
              </button>
            </div>

            {/* Divider */}
            <div className="flex items-center gap-3">
              <div className="flex-1 h-px" style={{ background:'#334155' }} />
              <span className="text-xs text-slate-500">أو</span>
              <div className="flex-1 h-px" style={{ background:'#334155' }} />
            </div>

            {/* Demo mode — tree-shaken out of production builds (import.meta.env.PROD is
                statically evaluated by Vite, so the whole branch is dropped in prod). */}
            {!import.meta.env.PROD && (
              <button type="button" onClick={loginDemo}
                className="w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm transition-all border"
                style={{ background:'transparent', borderColor:'#334155', color:'#94a3b8' }}>
                <Shield className="w-4 h-4" />
                دخول تجريبي (بيانات افتراضية)
              </button>
            )}

            {/* Signup link */}
            <p className="text-center text-xs text-slate-500 pt-1">
              ليس لديك حساب؟{' '}
              <button type="button" onClick={onSignup}
                className="text-emerald-500 hover:text-emerald-400 font-medium">
                إنشاء حساب جديد
              </button>
            </p>
          </form>
          )}

          {/* ── Reset flow ───────────────────────────────────────── */}
          {(view === 'reset-request' || view === 'reset-confirm') && (
            <ResetFlow
              view={view}
              setView={setView}
              initialEmail={email}
              onBackToLogin={() => { setView('login'); setError(''); }}
            />
          )}

          {/* أُزيل تلميح بيانات اعتماد المدير (تسريب حرج: كلمة سرّ على شاشة الدخول). */}
        </div>

        <p className="text-center text-xs text-slate-600 mt-4">
          SAHOOL v8.0 · 47/47 اختبار ✅
        </p>
      </div>
    </div>
  );
}

// ── Reset flow component ─────────────────────────────────────────
// خطوتان: (1) طلب الرمز بالبريد، (2) إدخال الرمز + كلمة مرور جديدة. الخادم
// يردّ دائماً برسالة موحّدة عند الطلب (منع تعداد البريد)، فننتقل دائماً للتأكيد.
function ResetFlow({
  view, setView, initialEmail, onBackToLogin,
}: {
  view: 'reset-request' | 'reset-confirm';
  setView: (v: 'login' | 'reset-request' | 'reset-confirm') => void;
  initialEmail: string;
  onBackToLogin: () => void;
}) {
  const [email, setEmail]     = useState(initialEmail);
  const [token, setToken]     = useState('');
  const [newPw, setNewPw]     = useState('');
  const [showPw, setShowPw]   = useState(false);
  const [error, setError]     = useState('');
  const [info, setInfo]       = useState('');
  const [done, setDone]       = useState(false);
  const [loading, setLoading] = useState(false);

  const fieldStyle = { background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0', outline:'none' } as const;

  // قواعد كلمة المرور = ما يفرضه الخادم (8+، حرف كبير، رقم). نضيف رمزاً خاصّاً
  // اتّساقاً مع SignupPage (أقوى من حدّ الخادم الأدنى — مقبول).
  const pwError = (): string | null => {
    if (newPw.length < 8) return 'كلمة المرور 8 أحرف على الأقل';
    if (!/[A-Z]/.test(newPw)) return 'يجب أن تحتوي على حرف كبير (إنجليزيّ)';
    if (!/[0-9]/.test(newPw)) return 'يجب أن تحتوي على رقم';
    if (!/[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/.test(newPw)) return 'يجب أن تحتوي على رمز خاص (مثل !@#$)';
    return null;
  };

  const handleRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) { setError('أدخل البريد الإلكتروني'); return; }
    setLoading(true); setError('');
    try {
      const res = await requestPasswordReset(email.trim());
      setInfo(res.message || 'إذا كان البريد مسجلاً، ستصلك رسالة إعادة التعيين');
      setView('reset-confirm');
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'تعذّر إرسال طلب إعادة التعيين'));
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim()) { setError('أدخل رمز إعادة التعيين من بريدك'); return; }
    const pe = pwError();
    if (pe) { setError(pe); return; }
    setLoading(true); setError('');
    try {
      await confirmPasswordReset(token.trim(), newPw);
      setDone(true);
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'رمز غير صالح أو منتهٍ'));
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return (
      <div className="space-y-4 text-center" dir="rtl">
        <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto" />
        <p className="text-slate-200 text-sm">تم تغيير كلمة المرور بنجاح</p>
        <button type="button" onClick={onBackToLogin}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm text-white"
          style={{ background:'#16a34a' }}>
          العودة لتسجيل الدخول
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={view === 'reset-request' ? handleRequest : handleConfirm} className="space-y-4" dir="rtl">
      <div className="flex items-center gap-2 text-slate-200">
        <KeyRound className="w-4 h-4 text-emerald-400" />
        <span className="text-sm font-semibold">
          {view === 'reset-request' ? 'إعادة تعيين كلمة المرور' : 'تأكيد إعادة التعيين'}
        </span>
      </div>

      {view === 'reset-request' && (
        <>
          <p className="text-xs text-slate-500">أدخل بريدك المسجَّل، وسنرسل رمز إعادة تعيين صالحاً 30 دقيقة.</p>
          <div>
            <label className="block text-sm text-slate-400 mb-1.5">البريد الإلكتروني</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com" autoComplete="email"
              className="w-full px-4 py-3 rounded-xl text-sm" style={fieldStyle} />
          </div>
        </>
      )}

      {view === 'reset-confirm' && (
        <>
          {info && (
            <div className="p-3 rounded-xl text-xs text-emerald-300" style={{ background:'#052e16', border:'1px solid #16a34a33' }}>
              {info}
            </div>
          )}
          <div>
            <label className="block text-sm text-slate-400 mb-1.5">رمز إعادة التعيين</label>
            <input value={token} onChange={e => setToken(e.target.value)}
              placeholder="الرمز من بريدك" autoComplete="one-time-code"
              className="w-full px-4 py-3 rounded-xl text-sm" style={fieldStyle} />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1.5">كلمة المرور الجديدة <span className="text-slate-600">(8 أحرف، حرف كبير، رقم، رمز)</span></label>
            <div className="relative">
              <input type={showPw ? 'text' : 'password'} value={newPw}
                onChange={e => setNewPw(e.target.value)} placeholder="••••••••" autoComplete="new-password"
                className="w-full px-4 py-3 pl-11 rounded-xl text-sm" style={fieldStyle} />
              <button type="button" onClick={() => setShowPw(!showPw)}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200">
                {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
        </>
      )}

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl text-sm" style={{ background:'#1a0000', border:'1px solid #dc262633' }}>
          <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
          <span className="text-red-300">{error}</span>
        </div>
      )}

      <button type="submit" disabled={loading}
        className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all"
        style={{ background: loading ? '#15803d' : '#16a34a', color:'white', opacity: loading ? 0.8 : 1 }}>
        {loading
          ? <><Loader2 className="w-4 h-4 animate-spin" /> جارٍ المعالجة...</>
          : view === 'reset-request'
            ? <>إرسال الرمز <ArrowRight className="w-4 h-4" /></>
            : <>تأكيد كلمة المرور الجديدة <CheckCircle2 className="w-4 h-4" /></>}
      </button>

      <div className="text-center">
        <button type="button" onClick={onBackToLogin}
          className="text-xs text-slate-400 hover:text-emerald-400">
          العودة لتسجيل الدخول
        </button>
      </div>
    </form>
  );
}
