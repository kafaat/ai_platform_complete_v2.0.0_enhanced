// ═══════════════════════════════════════════════════════════════
// SAHOOL — MfaEnrollmentStep.tsx
// تسجيل MFA الإلزاميّ عند الدخول (دورٌ حسّاس بلا MFA مُفعّل).
//
// العقد (services/auth/routers/session.py + mfa.py): الدخول بكلمة مرور صحيحة يردّ 403
// بـ{enrollment_token, expires_in}. هذا الإثبات يفتح /auth/mfa/setup وحده (مرّة واحدة)،
// وsetup يُعيد السرّ + otpauth + إثباتاً ثانياً يفتح /auth/mfa/activate وحده. التفعيل
// يُعيد رموز الاسترداد فقط — لا جلسة — فيعود المستخدم ليدخل بكلمة المرور + رمز TOTP.
//
// أمان: الإثباتان في حالة المكوّن (الذاكرة) فقط — لا localStorage/sessionStorage ولا
// سجلّ console. setup يُستدعى بزرّ صريح لا بـuseEffect: StrictMode يُكرّر التأثيرات في
// التطوير فيستهلك الاستدعاءُ الأوّل الإثبات ويفشل الثاني بـ401.
// لا مكتبة QR في package.json ⇒ نعرض السرّ ورابط otpauth نصّاً مع نسخ، ورابطاً يفتح
// تطبيق المصادقة على الهاتف (لا تبعيّة جديدة).
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Shield, AlertTriangle, Loader2, CheckCircle2, Copy, Check, KeyRound } from 'lucide-react';
import {
  classifyMfaEnrollmentError,
  mfaEnrollmentActivate,
  mfaEnrollmentSetup,
  type MfaEnrollmentChallenge,
} from '../services/api/auth';

type Stage = 'intro' | 'setup' | 'done' | 'restart';

interface SetupView {
  secret: string;
  provisioningUri: string;
  activationProof: string;
  expiresIn?: number;
}

const fieldStyle = { background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0', outline:'none' } as const;

function minutesText(seconds?: number): string | null {
  if (!seconds || seconds <= 0) return null;
  const m = Math.max(1, Math.round(seconds / 60));
  return m === 1 ? 'دقيقة واحدة' : m === 2 ? 'دقيقتين' : `${m} دقائق`;
}

// رسالة صادقة لكلّ صنف خطأ (لا نعرض نصّ الخادم الإنجليزيّ للمستخدم).
function enrollmentErrorMessage(e: unknown, phase: 'setup' | 'activate'): { msg: string; restart: boolean } {
  switch (classifyMfaEnrollmentError(e)) {
    case 'network':
      return { msg: 'تعذّر الوصول إلى خدمة المصادقة — تحقّق من الاتصال وأعد المحاولة', restart: false };
    case 'bad_code':
      return phase === 'activate'
        ? { msg: 'رمز غير صحيح — تأكّد من الرمز الحاليّ في تطبيق المصادقة وأعد المحاولة', restart: false }
        : { msg: 'تعذّر بدء الإعداد: حالة MFA للحساب تغيّرت — سجّل الدخول من جديد', restart: true };
    case 'restart':
      return { msg: 'انتهت صلاحيّة خطوة التفعيل أو استُخدمت من قبل — سجّل الدخول من جديد للمتابعة', restart: true };
    case 'locked':
      return { msg: 'تجاوزت محاولات MFA المسموحة — الحساب مقفل مؤقّتاً، حاول لاحقاً', restart: true };
    case 'unavailable':
      return { msg: 'خدمة تفعيل المصادقة الثنائيّة غير متاحة حاليّاً — حاول بعد قليل أو تواصل مع المسؤول', restart: false };
    default:
      return { msg: 'تعذّر إكمال تفعيل المصادقة الثنائيّة — حاول مرّة أخرى', restart: false };
  }
}

export default function MfaEnrollmentStep({
  email, challenge, onEnrolled, onBackToLogin,
}: {
  email: string;
  challenge: MfaEnrollmentChallenge;
  onEnrolled: () => void;
  onBackToLogin: () => void;
}) {
  const [stage, setStage]     = useState<Stage>('intro');
  const [setup, setSetup]     = useState<SetupView | null>(null);
  const [code, setCode]       = useState('');
  const [recovery, setRecovery] = useState<string[]>([]);
  const [error, setError]     = useState('');
  const [loading, setLoading] = useState(false);
  const [copied, setCopied]   = useState<'secret' | 'uri' | 'codes' | null>(null);

  const fail = (e: unknown, phase: 'setup' | 'activate') => {
    const { msg, restart } = enrollmentErrorMessage(e, phase);
    setError(msg);
    if (restart) {
      // الإثبات لم يعد صالحاً: نُسقطه من الذاكرة ولا نعرض السرّ بعد الآن.
      setSetup(null);
      setCode('');
      setStage('restart');
    }
  };

  const handleStart = async () => {
    setLoading(true); setError('');
    try {
      const res = await mfaEnrollmentSetup(challenge.enrollment_token);
      if (!res.enrollment_token || !res.secret || !res.provisioning_uri) {
        // ردّ setup بلا إثبات تفعيل لا يمكن إكماله من شاشة الدخول.
        setError('ردّ غير متوقَّع من خدمة المصادقة — سجّل الدخول من جديد');
        setStage('restart');
        return;
      }
      setSetup({
        secret: res.secret,
        provisioningUri: res.provisioning_uri,
        activationProof: res.enrollment_token,
        expiresIn: res.expires_in,
      });
      setStage('setup');
    } catch (e: unknown) {
      fail(e, 'setup');
    } finally {
      setLoading(false);
    }
  };

  const handleActivate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!setup) return;
    if (!/^\d{6}$/.test(code)) { setError('أدخل الرمز المكوّن من ٦ أرقام من تطبيق المصادقة'); return; }
    setLoading(true); setError('');
    try {
      const res = await mfaEnrollmentActivate(setup.activationProof, code);
      setRecovery(Array.isArray(res.recovery_codes) ? res.recovery_codes : []);
      setSetup(null);  // السرّ والإثبات لا يُحتفَظ بهما بعد التفعيل
      setCode('');
      setStage('done');
    } catch (err: unknown) {
      fail(err, 'activate');
      setCode('');
    } finally {
      setLoading(false);
    }
  };

  const copy = async (what: 'secret' | 'uri' | 'codes', text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
      setTimeout(() => setCopied(null), 2000);
    } catch { /* الحافظة غير متاحة — النصّ ظاهر للنسخ اليدويّ */ }
  };

  const errorBox = error && (
    <div role="alert" aria-live="polite" className="flex items-center gap-2 p-3 rounded-xl text-sm" style={{ background:'#1a0000', border:'1px solid #dc262633' }}>
      <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
      <span className="text-red-300">{error}</span>
    </div>
  );

  const primaryBtn = 'w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all';
  const primaryStyle = { background: loading ? '#15803d' : '#16a34a', color:'white', opacity: loading ? 0.8 : 1 };
  const backLink = (
    <div className="text-center">
      <button type="button" onClick={onBackToLogin} className="text-xs text-slate-400 hover:text-emerald-400">
        العودة لتسجيل الدخول
      </button>
    </div>
  );
  const header = (
    <div className="flex items-center gap-2 text-slate-200">
      <Shield className="w-4 h-4 text-emerald-400" />
      <span className="text-sm font-semibold">تفعيل المصادقة الثنائيّة (إلزاميّ)</span>
    </div>
  );

  if (stage === 'restart') {
    return (
      <div className="space-y-4" dir="rtl">
        {header}
        {errorBox}
        <button type="button" onClick={onBackToLogin} className={primaryBtn} style={{ background:'#16a34a', color:'white' }}>
          العودة لتسجيل الدخول
        </button>
      </div>
    );
  }

  if (stage === 'done') {
    return (
      <div className="space-y-4" dir="rtl">
        <div className="text-center space-y-2">
          <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto" />
          <p className="text-slate-200 text-sm font-semibold">تم تفعيل المصادقة الثنائيّة بنجاح</p>
        </div>
        {recovery.length > 0 && (
          <div className="p-3 rounded-xl space-y-2" style={{ background:'#0f1117', border:'1px solid #f59e0b55' }}>
            <p className="text-xs text-amber-300 flex items-center gap-1.5">
              <KeyRound className="w-3.5 h-3.5" /> رموز الاسترداد — احفظها الآن في مكان آمن، لن تُعرَض مرّة أخرى.
            </p>
            <ul aria-label="رموز الاسترداد" className="grid grid-cols-2 gap-1 font-mono text-xs text-slate-200" dir="ltr">
              {recovery.map(c => <li key={c}>{c}</li>)}
            </ul>
            <button type="button" onClick={() => copy('codes', recovery.join('\n'))}
              className="flex items-center gap-1 px-2 py-1 rounded-sm text-[11px] text-slate-300" style={{ border:'1px solid #334155' }}>
              {copied === 'codes' ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
              {copied === 'codes' ? 'نُسخت' : 'نسخ الرموز'}
            </button>
          </div>
        )}
        <p className="text-xs text-slate-400">
          سجّل الدخول الآن بكلمة المرور ورمزٍ من تطبيق المصادقة. الرمز الذي استُخدم للتفعيل لا يُقبَل مرّة ثانية — انتظر ظهور رمز جديد.
        </p>
        <button type="button" onClick={onEnrolled} className={primaryBtn} style={{ background:'#16a34a', color:'white' }}>
          متابعة لتسجيل الدخول
        </button>
      </div>
    );
  }

  if (stage === 'intro') {
    const ttl = minutesText(challenge.expires_in);
    return (
      <div className="space-y-4" dir="rtl">
        {header}
        <p className="text-xs text-slate-400 leading-relaxed">
          كلمة المرور صحيحة، لكنّ هذا الحساب (<span className="text-slate-200" dir="ltr">{email}</span>) يتطلّب تفعيل
          المصادقة الثنائيّة قبل الدخول. ستحتاج تطبيق مصادقة على هاتفك (Google Authenticator / Authy).
          {ttl && <> أكمِل الخطوات خلال {ttl}.</>}
        </p>
        {errorBox}
        <button type="button" onClick={handleStart} disabled={loading} className={primaryBtn} style={primaryStyle}>
          {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> جارٍ التحضير...</> : 'بدء تفعيل المصادقة الثنائيّة'}
        </button>
        {backLink}
      </div>
    );
  }

  // stage === 'setup'
  const ttl = minutesText(setup?.expiresIn);
  const uri = setup?.provisioningUri ?? '';
  return (
    <form onSubmit={handleActivate} className="space-y-4" dir="rtl">
      {header}
      <div className="p-3 rounded-xl space-y-2" style={{ background:'#0f1117', border:'1px solid #334155' }}>
        <p className="text-[11px] text-slate-400">
          ١. أضِف الحساب في تطبيق المصادقة بإدخال المفتاح يدويّاً أو بفتح الرابط على هاتفك.
          <span className="text-amber-300"> يُعرَض مرّة واحدة فقط.</span>
        </p>
        <div>
          <span className="block text-[11px] text-slate-500 mb-1">المفتاح السرّيّ</span>
          <div className="flex items-center gap-2">
            <code data-testid="mfa-enroll-secret" className="flex-1 text-xs font-mono break-all text-emerald-300" dir="ltr">{setup?.secret}</code>
            <button type="button" onClick={() => copy('secret', setup?.secret ?? '')}
              className="flex items-center gap-1 px-2 py-1 rounded-sm text-[11px] text-slate-300" style={{ border:'1px solid #334155' }}>
              {copied === 'secret' ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
              {copied === 'secret' ? 'نُسخ' : 'نسخ'}
            </button>
          </div>
        </div>
        <div className="pt-2" style={{ borderTop:'1px solid #334155' }}>
          <span className="block text-[11px] text-slate-500 mb-1">رابط otpauth</span>
          <div className="flex items-center gap-2">
            <code data-testid="mfa-enroll-uri" className="flex-1 text-[10px] font-mono break-all text-slate-400" dir="ltr">{uri}</code>
            <button type="button" onClick={() => copy('uri', uri)}
              className="flex items-center gap-1 px-2 py-1 rounded-sm text-[11px] text-slate-300" style={{ border:'1px solid #334155' }}>
              {copied === 'uri' ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
              {copied === 'uri' ? 'نُسخ' : 'نسخ'}
            </button>
          </div>
          {uri.startsWith('otpauth://') && (
            <a href={uri} className="inline-block mt-1 text-[11px] text-emerald-400 hover:text-emerald-300">
              فتح في تطبيق المصادقة (على الهاتف)
            </a>
          )}
        </div>
      </div>
      <div>
        <label htmlFor="mfa-enroll-code" className="block text-sm text-slate-400 mb-1.5">
          ٢. رمز التأكيد من تطبيق المصادقة
        </label>
        <input
          id="mfa-enroll-code"
          value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
          placeholder="123456" inputMode="numeric" autoComplete="one-time-code"
          className="w-full px-4 py-3 rounded-xl text-sm tracking-[0.4em] text-center"
          style={fieldStyle}
        />
        {ttl && <p className="text-[11px] text-slate-500 mt-1">أكمِل التفعيل خلال {ttl}، وإلّا سجّل الدخول من جديد.</p>}
      </div>
      {errorBox}
      <button type="submit" disabled={loading} className={primaryBtn} style={primaryStyle}>
        {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> جارٍ التفعيل...</> : <>تفعيل <CheckCircle2 className="w-4 h-4" /></>}
      </button>
      {backLink}
    </form>
  );
}
