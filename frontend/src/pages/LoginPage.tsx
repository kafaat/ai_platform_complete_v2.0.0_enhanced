// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — LoginPage.tsx
// صفحة تسجيل الدخول: email + password + demo mode
// ✅ رمز MFA (TOTP) يظهر عند طلب الخادم له (X-MFA-Required)
// ✅ تدفّق "نسيت كلمة المرور؟": طلب بالبريد → رابط /reset-password?token= → كلمة مرور جديدة
// ✅ تسجيل MFA الإلزاميّ: 403 + enrollment_token ⇒ خطوة setup/activate (MfaEnrollmentStep)
// ═══════════════════════════════════════════════════════════════
import { useEffect, useState } from 'react';
import { Leaf, Eye, EyeOff, Loader2, Shield, AlertTriangle, KeyRound, ArrowRight, CheckCircle2, Mail } from 'lucide-react';
import { useAuthStore } from '../hooks/useAuth';
import { requestPasswordReset, confirmPasswordReset, apiErrorMessage, isMfaRequiredError } from '../services/api';
import { mfaEnrollmentChallenge, type MfaEnrollmentChallenge } from '../services/api/auth';
import MfaEnrollmentStep from './MfaEnrollmentStep';

// شاشات هذه الصفحة: الدخول، أو تدفّق إعادة التعيين (طلب ثمّ تأكيد)، أو تسجيل MFA الإلزاميّ.
type View = 'login' | 'reset-request' | 'reset-confirm' | 'mfa-enroll';

export default function LoginPage({
  onSignup,
  onForgotPassword,
  onLogin,
  initialView = 'login',
  initialEmail = '',
  initialToken = '',
}: {
  onSignup?: () => void;
  onForgotPassword?: (email: string) => void;
  onLogin?: () => void;
  initialView?: 'login' | 'reset-request' | 'reset-confirm';
  initialEmail?: string;
  /** The token of a /reset-password link (reset or tenant-owner setup email). */
  initialToken?: string;
}) {
  const [view, setView]       = useState<View>(initialView);
  const [email, setEmail]     = useState(initialEmail);
  const [password, setPassword] = useState('');
  const [showPw, setShowPw]   = useState(false);
  const [error, setError]     = useState('');
  const [loading, setLoading] = useState(false);
  // MFA: يظهر الحقل فقط بعد أن يطلبه الخادم (كلمة المرور صحّت، يلزم رمز).
  const [mfaRequired, setMfaRequired] = useState(false);
  const [mfaCode, setMfaCode] = useState('');
  // تسجيل MFA الإلزاميّ: إثبات كلمة المرور (403 + enrollment_token) في الذاكرة فقط —
  // لا Storage ولا سجلّ؛ يُسقَط عند العودة لنموذج الدخول.
  const [enrollment, setEnrollment] = useState<MfaEnrollmentChallenge | null>(null);
  const [notice, setNotice]   = useState('');
  const { login, loginDemo }  = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) { setError('أدخل البريد وكلمة المرور'); return; }
    if (mfaRequired && !mfaCode.trim()) { setError('أدخل رمز المصادقة الثنائيّة'); return; }
    setLoading(true); setError(''); setNotice('');
    try {
      await login(email, password, mfaRequired ? mfaCode.trim() : undefined);
    } catch (err: unknown) {
      // دورٌ حسّاس بلا MFA: الخادم يردّ 403 + enrollment_token (كلمة المرور صحّت، يلزم
      // تفعيل MFA أوّلاً). 403 بلا إثبات يبقى خطأً عاديّاً أدناه.
      const challenge = mfaEnrollmentChallenge(err);
      if (challenge) {
        setEnrollment(challenge);
        setView('mfa-enroll');
        return;
      }
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

  const fieldStyle = { background:'#fff', border:'1px solid #a7b3a7', color:'#202621' } as const;

  return (
    <main className="ops-auth min-h-screen flex items-center justify-center p-4 dir-rtl">
      <div className="relative w-full max-w-md">
        {/* Card */}
        <div className="ops-auth-card p-6 sm:p-8">

          {/* Logo */}
          <div className="text-center mb-8">
            <div className="w-16 h-16 rounded-md bg-[#367c2b] flex items-center justify-center mx-auto mb-4 ">
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
              <label htmlFor="login-email" className="block text-sm text-slate-400 mb-1.5">البريد الإلكتروني</label>
              <input
                id="login-email"
                type="email" value={email} onChange={e => setEmail(e.target.value)}
                placeholder="admin@sahool.ye"
                className="w-full px-4 py-3 rounded-xl text-sm"
                style={fieldStyle}
                autoComplete="email"
              />
            </div>

            {/* Password */}
            <div>
              <label htmlFor="login-password" className="block text-sm text-slate-400 mb-1.5">كلمة المرور</label>
              <div className="relative">
                <input
                  id="login-password"
                  type={showPw ? 'text' : 'password'} value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-4 py-3 pl-11 rounded-xl text-sm"
                  style={fieldStyle}
                  autoComplete="current-password"
                />
                <button type="button" onClick={() => setShowPw(!showPw)}
                  aria-label={showPw ? 'إخفاء كلمة المرور' : 'إظهار كلمة المرور'}
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

            {/* Notice (بعد تفعيل MFA الإلزاميّ) */}
            {notice && (
              <div role="status" className="flex items-center gap-2 p-3 rounded-xl text-sm text-emerald-300" style={{ background:'#052e16', border:'1px solid #16a34a33' }}>
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>{notice}</span>
              </div>
            )}

            {/* Error */}
            {error && (
              <div role="alert" aria-live="polite" className="flex items-center gap-2 p-3 rounded-xl text-sm" style={{ background:'#1a0000', border:'1px solid #dc262633' }}>
                <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
                <span className="text-red-300">{error}</span>
              </div>
            )}

            {/* Submit */}
            <button type="submit" disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all"
              style={{ background: loading ? '#275d20' : '#367c2b', color:'white', opacity: loading ? 0.8 : 1 }}>
              {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> جاري الدخول...</> : 'تسجيل الدخول'}
            </button>

            {/* Forgot password */}
            <div className="text-center">
              <button type="button"
                onClick={() => { setError(''); if (onForgotPassword) onForgotPassword(email.trim()); else setView('reset-request'); }}
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
                style={{ background:'transparent', borderColor:'#a7b3a7', color:'#334437' }}>
                <Shield className="w-4 h-4" />
                دخول تجريبي (بيانات افتراضية)
              </button>
            )}

            {/* Signup link */}
            <p className="text-center text-xs text-slate-500 pt-1">
              ليس لديك حساب؟{' '}
              <button type="button" onClick={onSignup}
                className="text-[#275d20] hover:underline font-semibold">
                إنشاء حساب جديد
              </button>
            </p>
          </form>
          )}

          {/* ── Mandatory MFA enrollment ─────────────────────────── */}
          {view === 'mfa-enroll' && enrollment && (
            <MfaEnrollmentStep
              email={email}
              challenge={enrollment}
              onEnrolled={() => {
                // التفعيل لا يُصدِر جلسة: نعود للدخول بكلمة المرور + رمز TOTP.
                setEnrollment(null);
                setMfaRequired(true);
                setMfaCode('');
                setError('');
                setNotice('تم تفعيل المصادقة الثنائيّة — سجّل الدخول الآن برمزٍ جديد من تطبيق المصادقة');
                setView('login');
              }}
              onBackToLogin={() => {
                setEnrollment(null);
                setError('');
                setNotice('');
                setView('login');
              }}
            />
          )}

          {/* ── Reset flow ───────────────────────────────────────── */}
          {(view === 'reset-request' || view === 'reset-confirm') && (
            <ResetFlow
              view={view}
              initialEmail={email}
              initialToken={initialToken}
              onBackToLogin={() => { setError(''); if (onLogin) onLogin(); else setView('login'); }}
            />
          )}

          {/* أُزيل تلميح بيانات اعتماد المدير (تسريب حرج: كلمة سرّ على شاشة الدخول). */}
        </div>

        {/* أُزيل ادّعاءُ «47/47 اختبار ✅» الثابت (مراجعة Railway 2026-09-20، RW-05): نصٌّ لا يرتبط
            بأيّ تشغيل CI ولا بهويّة النشر، فيُقرأ دليلَ جاهزيّة وهو ليس كذلك. */}
      </div>
    </main>
  );
}

// ── Reset flow component ─────────────────────────────────────────
// خطوتان: (1) طلب الرابط بالبريد، (2) كلمة مرور جديدة من رابط البريد. الخادم يرسل
// **رابطاً** (/reset-password?token=…، صالح 30 دقيقة) لا رمزاً يُكتب، ويردّ دائماً برسالة
// موحّدة عند الطلب (منع تعداد البريد). فبعد الطلب نطلب فتح الرابط؛ والخطوة الثانية تُفتح
// من الرابط برمزه معبّأً (وكذلك بريد إعداد مالك مستأجِر جديد).
function ResetFlow({
  view, initialEmail, initialToken = '', onBackToLogin,
}: {
  view: 'reset-request' | 'reset-confirm';
  initialEmail: string;
  initialToken?: string;
  onBackToLogin: () => void;
}) {
  const [email, setEmail]     = useState(initialEmail);
  const [token, setToken]     = useState(initialToken);
  const [sent, setSent]       = useState(false);
  // Like the invitation page: once the link's token is held in state, drop it from the
  // address bar and browser history, so the secret is not left in history, screenshots or a
  // copied URL. A reload then asks for a new link instead of reusing an exposed one.
  useEffect(() => {
    if (!initialToken || typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    if (!params.has('token')) return;
    params.delete('token');
    const qs = params.toString();
    window.history.replaceState(window.history.state, '', window.location.pathname + (qs ? `?${qs}` : '') + window.location.hash);
  }, [initialToken]);
  const [newPw, setNewPw]     = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [showPw, setShowPw]   = useState(false);
  const [error, setError]     = useState('');
  const [info, setInfo]       = useState('');
  const [done, setDone]       = useState(false);
  const [loading, setLoading] = useState(false);

  const fieldStyle = { background:'#fff', border:'1px solid #a7b3a7', color:'#202621' } as const;

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
      setSent(true);
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'تعذّر إرسال طلب إعادة التعيين'));
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim()) { setError('افتح رابط إعادة التعيين من بريدك'); return; }
    const pe = pwError();
    if (pe) { setError(pe); return; }
    if (confirmPw !== newPw) { setError('كلمتا المرور غير متطابقتين'); return; }
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

  if (sent && view === 'reset-request') {
    return (
      <div className="space-y-4 text-center" dir="rtl">
        <Mail className="w-12 h-12 text-emerald-400 mx-auto" />
        <p className="text-slate-200 text-sm">{info}</p>
        <p className="text-xs text-slate-500">افتح رابط إعادة التعيين في البريد لإكمال التغيير. الرابط صالح 30 دقيقة.</p>
        <button type="button" onClick={onBackToLogin}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm text-white"
          style={{ background:'#367c2b' }}>
          العودة لتسجيل الدخول
        </button>
      </div>
    );
  }

  if (done) {
    return (
      <div className="space-y-4 text-center" dir="rtl">
        <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto" />
        <p className="text-slate-200 text-sm">تم تغيير كلمة المرور بنجاح</p>
        <button type="button" onClick={onBackToLogin}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm text-white"
          style={{ background:'#367c2b' }}>
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
          {view === 'reset-request' ? 'إعادة تعيين كلمة المرور' : 'تعيين كلمة مرور جديدة'}
        </span>
      </div>

      {view === 'reset-request' && (
        <>
          <p className="text-xs text-slate-500">أدخل بريدك المسجَّل، وسنرسل رابط إعادة تعيين صالحاً 30 دقيقة.</p>
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
          {!initialToken && (
            <div>
              <label htmlFor="reset-token" className="block text-sm text-slate-400 mb-1.5">رمز إعادة التعيين (من رابط البريد)</label>
              <input id="reset-token" value={token} onChange={e => setToken(e.target.value)}
                placeholder="الرمز بعد token= في الرابط" autoComplete="one-time-code"
                className="w-full px-4 py-3 rounded-xl text-sm" style={fieldStyle} />
            </div>
          )}
          <div>
            <label htmlFor="reset-new-password" className="block text-sm text-slate-400 mb-1.5">كلمة المرور الجديدة <span className="text-slate-600">(8 أحرف، حرف كبير، رقم، رمز)</span></label>
            <div className="relative">
              <input id="reset-new-password" type={showPw ? 'text' : 'password'} value={newPw}
                onChange={e => setNewPw(e.target.value)} placeholder="••••••••" autoComplete="new-password"
                className="w-full px-4 py-3 pl-11 rounded-xl text-sm" style={fieldStyle} />
              <button type="button" onClick={() => setShowPw(!showPw)}
                aria-label={showPw ? 'إخفاء كلمة المرور' : 'إظهار كلمة المرور'}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200">
                {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <div>
            <label htmlFor="reset-confirm-password" className="block text-sm text-slate-400 mb-1.5">تأكيد كلمة المرور</label>
            <input id="reset-confirm-password" type={showPw ? 'text' : 'password'} value={confirmPw}
              onChange={e => setConfirmPw(e.target.value)} placeholder="••••••••" autoComplete="new-password"
              className="w-full px-4 py-3 rounded-xl text-sm" style={fieldStyle} />
          </div>
        </>
      )}

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl text-sm" style={{ background:'#1a0000', border:'1px solid #dc262633' }}>
          <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
          <span className="text-red-300">{error}</span>
        </div>
      )}

      <button type="submit" disabled={loading}
        className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all"
        style={{ background: loading ? '#275d20' : '#367c2b', color:'white', opacity: loading ? 0.8 : 1 }}>
        {loading
          ? <><Loader2 className="w-4 h-4 animate-spin" /> جارٍ المعالجة...</>
          : view === 'reset-request'
            ? <>إرسال الرابط <ArrowRight className="w-4 h-4" /></>
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
