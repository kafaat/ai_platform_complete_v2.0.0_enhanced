// ═══════════════════════════════════════════════════════════════
// SAHOOL — SignupPage.tsx — إنشاء حساب (Sprint 1: الهوية)
// يجمع حقول الهوية ويُرسل ما تقبله /auth/register (الاسم/البريد/كلمة المرور).
// الدور يُثبَّت 'farmer' خادم-جانبيّاً (منع تصعيد الصلاحيّات) — لا يُختار هنا.
// الدولة/اللغة تُحفظ كتفضيل واجهة (الخلفيّة لا تخزّنها بعد — تُملأ تدريجيّاً).
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Leaf, Eye, EyeOff, Loader2, AlertTriangle, UserPlus } from 'lucide-react';
import { useAuthStore } from '../hooks/useAuth';

const COUNTRIES = ['اليمن', 'السعودية', 'الإمارات', 'عُمان', 'مصر', 'الأردن', 'أخرى'];
const LANGUAGES = [
  { value: 'ar', label: 'العربية' },
  { value: 'en', label: 'English' },
];

export default function SignupPage({ onLogin }: { onLogin?: () => void }) {
  const { signup } = useAuthStore();
  const [fullName, setFullName] = useState('');
  const [email, setEmail]       = useState('');
  const [phone, setPhone]       = useState('');
  const [country, setCountry]   = useState(COUNTRIES[0]);
  const [language, setLanguage] = useState('ar');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm]   = useState('');
  const [agree, setAgree]       = useState(false);
  const [showPw, setShowPw]     = useState(false);
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (fullName.trim().length < 2) { setError('أدخل الاسم الكامل'); return; }
    if (!email) { setError('أدخل البريد الإلكتروني'); return; }
    if (password.length < 8) { setError('كلمة المرور 8 أحرف على الأقل'); return; }
    if (password !== confirm) { setError('كلمتا المرور غير متطابقتين'); return; }
    if (!agree) { setError('يجب الموافقة على الشروط'); return; }
    setLoading(true); setError('');
    try {
      // تفضيل اللغة/الدولة محليّاً (الخلفيّة لا تستقبلهما بعد).
      localStorage.setItem('sahool_locale', JSON.stringify({ country, language }));
      await signup({ full_name: fullName.trim(), email: email.trim(), password });
      // النجاح ⇒ توكن محفوظ ⇒ التطبيق ينتقل تلقائيّاً (isAuthenticated).
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.response?.data?.message_ar
        || err?.message || 'تعذّر إنشاء الحساب');
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
            <h1 className="text-2xl font-bold text-slate-100">إنشاء حساب</h1>
            <p className="text-slate-400 text-sm mt-1">منصة الزراعة الذكية اليمنية</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3.5" dir="rtl">
            <div>
              <label className="block text-sm text-slate-400 mb-1.5">الاسم الكامل *</label>
              <input value={fullName} onChange={e => setFullName(e.target.value)}
                placeholder="مثال: محمد أحمد" className="w-full px-4 py-2.5 rounded-xl text-sm" style={fieldStyle} />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1.5">البريد الإلكتروني *</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com" autoComplete="email"
                className="w-full px-4 py-2.5 rounded-xl text-sm" style={fieldStyle} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm text-slate-400 mb-1.5">الهاتف (اختياري)</label>
                <input value={phone} onChange={e => setPhone(e.target.value)}
                  placeholder="+9677…" inputMode="tel"
                  className="w-full px-4 py-2.5 rounded-xl text-sm" style={fieldStyle} />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1.5">الدولة</label>
                <select value={country} onChange={e => setCountry(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl text-sm" style={fieldStyle}>
                  {COUNTRIES.map(c => <option key={c}>{c}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1.5">اللغة</label>
              <select value={language} onChange={e => setLanguage(e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl text-sm" style={fieldStyle}>
                {LANGUAGES.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
              </select>
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

            <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer">
              <input type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)}
                className="accent-emerald-500 w-4 h-4" />
              أوافق على شروط الاستخدام وسياسة الخصوصيّة
            </label>

            {error && (
              <div className="flex items-center gap-2 p-3 rounded-xl text-sm" style={{ background:'#1a0000', border:'1px solid #dc262633' }}>
                <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                <span className="text-red-300">{error}</span>
              </div>
            )}

            <button type="submit" disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all"
              style={{ background: loading ? '#15803d' : '#16a34a', color:'white', opacity: loading ? 0.8 : 1 }}>
              {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> جاري الإنشاء...</> : <><UserPlus className="w-4 h-4" /> إنشاء الحساب</>}
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
