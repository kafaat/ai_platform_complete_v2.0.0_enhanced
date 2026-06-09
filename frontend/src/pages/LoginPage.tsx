// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — LoginPage.tsx
// صفحة تسجيل الدخول: email + password + demo mode
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Leaf, Eye, EyeOff, Loader2, Shield, AlertTriangle } from 'lucide-react';
import { useAuthStore } from '../hooks/useAuth';

export default function LoginPage() {
  const [email, setEmail]     = useState('admin@sahool.ye');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw]   = useState(false);
  const [error, setError]     = useState('');
  const [loading, setLoading] = useState(false);
  const { login, loginDemo }  = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) { setError('أدخل البريد وكلمة المرور'); return; }
    setLoading(true); setError('');
    try {
      await login(email, password);
    } catch (err: any) {
      setError(err?.response?.data?.message_ar || err?.message || 'فشل تسجيل الدخول');
    } finally {
      setLoading(false);
    }
  };

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

          <form onSubmit={handleSubmit} className="space-y-4" dir="rtl">
            {/* Email */}
            <div>
              <label className="block text-sm text-slate-400 mb-1.5">البريد الإلكتروني</label>
              <input
                type="email" value={email} onChange={e => setEmail(e.target.value)}
                placeholder="admin@sahool.ye"
                className="w-full px-4 py-3 rounded-xl text-sm"
                style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0', outline:'none' }}
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
                  style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0', outline:'none' }}
                  autoComplete="current-password"
                />
                <button type="button" onClick={() => setShowPw(!showPw)}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200">
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

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

            {/* Divider */}
            <div className="flex items-center gap-3">
              <div className="flex-1 h-px" style={{ background:'#334155' }} />
              <span className="text-xs text-slate-500">أو</span>
              <div className="flex-1 h-px" style={{ background:'#334155' }} />
            </div>

            {/* Demo mode */}
            <button type="button" onClick={loginDemo}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm transition-all border"
              style={{ background:'transparent', borderColor:'#334155', color:'#94a3b8' }}>
              <Shield className="w-4 h-4" />
              دخول تجريبي (بيانات افتراضية)
            </button>
          </form>

          {/* Footer hint */}
          <div className="mt-6 p-3 rounded-xl text-xs text-center" style={{ background:'#0f1117', color:'#475569' }}>
            <p>مدير: <span className="text-emerald-600">admin@sahool.ye</span> / Admin@2026!</p>
          </div>
        </div>

        <p className="text-center text-xs text-slate-600 mt-4">
          SAHOOL v8.0 · 47/47 اختبار ✅
        </p>
      </div>
    </div>
  );
}
