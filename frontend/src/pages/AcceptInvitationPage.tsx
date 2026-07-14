// ═══════════════════════════════════════════════════════════════
// SAHOOL — AcceptInvitationPage.tsx — قبول دعوة عضو (انضمام بأدوار أدنى)
// شاشة عموميّة (ما قبل المصادقة): تقرأ ?token= من الرابط، تجمع الاسم وكلمة
// المرور، وتنادي acceptInvitation. الدور والمستأجِر يُؤخذان من صفّ الدعوة
// خادم-جانبيّاً (لا يختارهما العميل) — العضو ينضمّ لمستأجِر الداعي بدوره المدعوّ.
// النجاح ⇒ توكن محفوظ ⇒ التطبيق ينتقل تلقائيّاً (isAuthenticated).
// ═══════════════════════════════════════════════════════════════
import { useEffect, useState } from 'react';
import { Leaf, Eye, EyeOff, Loader2, AlertTriangle, UserPlus } from 'lucide-react';
import { useAuthStore } from '../hooks/useAuth';
import { apiErrorMessage } from '../services/api';

/** يستخرج token من الرابط (?token=…). يُمرَّر من App عند الكشف عن الـquery. */
function tokenFromUrl(): string {
  if (typeof window === 'undefined') return '';
  return new URLSearchParams(window.location.search).get('token') ?? '';
}

export default function AcceptInvitationPage({ onLogin }: { onLogin?: () => void }) {
  const { acceptInvite } = useAuthStore();
  const [token] = useState(tokenFromUrl);

  // بعد التقاط الرمز مرّةً (في الحالة)، أزِله من الرابط عبر history.replaceState كي لا
  // يبقى رمز الدعوة السرّيّ في سجلّ المتصفّح/اللقطات/التتبّع أو يُنسَخ مع الرابط
  // (continuation-1 P0). لا يُعيد تحميل الصفحة، والحالة تحتفظ بالرمز للإرسال.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    if (!params.has('token')) return;
    params.delete('token');
    const qs = params.toString();
    const clean = window.location.pathname + (qs ? `?${qs}` : '') + window.location.hash;
    window.history.replaceState(window.history.state, '', clean);
  }, []);
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm]   = useState('');
  const [showPw, setShowPw]     = useState(false);
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) { setError('رابط الدعوة غير صالح (لا رمز)'); return; }
    if (fullName.trim().length < 2) { setError('أدخل الاسم الكامل'); return; }
    // مطابقة قواعد الخلفيّة (InvitationAcceptRequest): 8+ أحرف، حرف كبير، رقم، رمز خاص.
    if (password.length < 8) { setError('كلمة المرور 8 أحرف على الأقل'); return; }
    if (!/[A-Z]/.test(password)) { setError('كلمة المرور يجب أن تحتوي على حرف كبير (إنجليزيّ)'); return; }
    if (!/[0-9]/.test(password)) { setError('كلمة المرور يجب أن تحتوي على رقم'); return; }
    if (!/[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/.test(password)) { setError('كلمة المرور يجب أن تحتوي على رمز خاص (مثل !@#$)'); return; }
    if (password !== confirm) { setError('كلمتا المرور غير متطابقتين'); return; }
    setLoading(true); setError('');
    try {
      await acceptInvite({ token, full_name: fullName.trim(), password });
      // النجاح ⇒ توكن محفوظ ⇒ التطبيق ينتقل تلقائيّاً (isAuthenticated).
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'تعذّر قبول الدعوة — قد يكون الرابط منتهياً أو مستهلَكاً'));
    } finally {
      setLoading(false);
    }
  };

  const fieldStyle = { background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0', outline:'none' } as const;

  return (
    <div className="min-h-screen flex items-center justify-center p-4"
      style={{ background:'linear-gradient(135deg, #0f1117 0%, #0d2010 50%, #0f1117 100%)' }}>
      <div className="relative w-full max-w-md">
        <div className="rounded-2xl p-8 border" style={{ background:'#1e293b', borderColor:'#334155', boxShadow:'0 25px 50px rgba(0,0,0,0.5)' }}>
          <div className="text-center mb-6">
            <div className="w-16 h-16 rounded-2xl bg-emerald-600 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-emerald-900/50">
              <Leaf className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-slate-100">قبول دعوة الانضمام</h1>
            <p className="text-slate-400 text-sm mt-1">انضمّ إلى فريق مؤسّستك على منصّة سهول</p>
          </div>

          {!token && (
            <div className="flex items-center gap-2 p-3 rounded-xl text-sm mb-4" style={{ background:'#1a0000', border:'1px solid #dc262633' }}>
              <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
              <span className="text-red-300">رابط الدعوة غير صالح — تأكّد من فتح الرابط كاملاً.</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3.5" dir="rtl">
            <div>
              <label className="block text-sm text-slate-400 mb-1.5">الاسم الكامل *</label>
              <input value={fullName} onChange={e => setFullName(e.target.value)}
                placeholder="مثال: محمد أحمد" className="w-full px-4 py-2.5 rounded-xl text-sm" style={fieldStyle} />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1.5">كلمة المرور * <span className="text-slate-600">(8 أحرف فأكثر)</span></label>
              <div className="relative">
                <input type={showPw ? 'text' : 'password'} value={password}
                  onChange={e => setPassword(e.target.value)} placeholder="••••••••" autoComplete="new-password"
                  className="w-full px-4 py-2.5 pl-11 rounded-xl text-sm" style={fieldStyle} />
                <button type="button" onClick={() => setShowPw(!showPw)}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200">
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1.5">تأكيد كلمة المرور *</label>
              <input type={showPw ? 'text' : 'password'} value={confirm}
                onChange={e => setConfirm(e.target.value)} placeholder="••••••••" autoComplete="new-password"
                className="w-full px-4 py-2.5 rounded-xl text-sm" style={fieldStyle} />
            </div>

            {error && (
              <div className="flex items-center gap-2 p-3 rounded-xl text-sm" style={{ background:'#1a0000', border:'1px solid #dc262633' }}>
                <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                <span className="text-red-300">{error}</span>
              </div>
            )}

            <button type="submit" disabled={loading || !token}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all"
              style={{ background: loading ? '#15803d' : '#16a34a', color:'white', opacity: (loading || !token) ? 0.8 : 1 }}>
              {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> جاري الانضمام...</> : <><UserPlus className="w-4 h-4" /> الانضمام للفريق</>}
            </button>

            <p className="text-center text-xs text-slate-500">
              لديك حساب؟{' '}
              <button type="button" onClick={onLogin} className="text-emerald-500 hover:text-emerald-400 font-medium">
                تسجيل الدخول
              </button>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
