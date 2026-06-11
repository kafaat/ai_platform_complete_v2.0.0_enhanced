// ═══════════════════════════════════════════════════════════════
// SAHOOL — FarmCreatePage (ربط حيّ بـ POST /api/v1/farms)
// شاشة «إنشاء مزرعة»: تجمع الاسم* + الدولة + المنطقة + نظام الوحدات + العملة +
// نوع النشاط + الوصف. تُستخدم مستقلّةً وكبوّابة تأهيل إجباريّة (App.tsx): مستخدم
// جديد بلا مزرعة يُجبَر على إنشاء واحدة قبل بلوغ اللوحة. لا تلفيق — الخطأ يُعرَض
// من detail ردّ الخادم (apiErrorMessage). 503 عند تعطيل قاعدة البيانات.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Leaf, Sprout, AlertTriangle } from 'lucide-react';
import { useCreateFarm } from '../hooks/useApi';
import { apiErrorMessage, type FarmCreateInput, type FarmUnits } from '../services/api';

// قائمة الدول (الافتراضيّة اليمن — سوق الإطلاق). «أخرى» تتيح أيّ دولة لاحقاً.
const COUNTRIES = ['اليمن', 'السعودية', 'الإمارات', 'عُمان', 'مصر', 'الأردن', 'أخرى'] as const;

// نوع النشاط الزراعيّ — يضبط القوالب/التوصيات لاحقاً.
const ACTIVITY_TYPES = ['زراعة محاصيل', 'بساتين/أشجار', 'خضروات محميّة', 'ثروة حيوانيّة', 'مختلط', 'أخرى'] as const;

const PANEL = { background: '#0f1117', borderColor: '#334155' } as const;
const CARD = { background: '#1e293b', borderColor: '#334155' } as const;
const INPUT = { background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' } as const;

interface FormState {
  name: string;
  country: string;
  region: string;
  units: FarmUnits;
  currency: string;
  activity_type: string;
  description: string;
}

export default function FarmCreatePage({ onCreated }: { onCreated?: () => void } = {}) {
  const mut = useCreateFarm();
  const [f, setF] = useState<FormState>({
    name: '',
    country: 'اليمن',
    region: '',
    units: 'metric',
    currency: '',
    activity_type: '',
    description: '',
  });

  const canSubmit = f.name.trim().length > 0 && !mut.isPending;

  const onSubmit = () => {
    if (!f.name.trim()) return;
    const payload: FarmCreateInput = {
      name: f.name.trim(),
      units: f.units,
      ...(f.country.trim() ? { country: f.country.trim() } : {}),
      ...(f.region.trim() ? { region: f.region.trim() } : {}),
      ...(f.currency.trim() ? { currency: f.currency.trim() } : {}),
      ...(f.activity_type.trim() ? { activity_type: f.activity_type.trim() } : {}),
      ...(f.description.trim() ? { description: f.description.trim() } : {}),
    };
    mut.mutate(payload, { onSuccess: () => onCreated?.() });
  };

  return (
    <div className="space-y-5 max-w-2xl mx-auto" dir="rtl">
      {/* رأس الصفحة */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-emerald-600 flex items-center justify-center flex-shrink-0">
          <Leaf className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-slate-100">إنشاء مزرعتك</h2>
          <p className="text-sm text-slate-400">
            ابدأ بتعريف مزرعتك — ستجمع الحقول والمحاصيل والبيانات تحتها.
          </p>
        </div>
      </div>

      {/* النموذج */}
      <div className="rounded-xl p-5 border" style={PANEL}>
        <div className="rounded-lg border p-4 space-y-4" style={CARD}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* الاسم (إلزاميّ) */}
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className="text-xs text-slate-400">اسم المزرعة *</span>
              <input
                value={f.name}
                onChange={(e) => setF((v) => ({ ...v, name: e.target.value }))}
                placeholder="مثال: مزرعة وادي سبأ"
                className="px-3 py-2 rounded-lg text-sm"
                style={INPUT}
              />
            </label>

            {/* الدولة */}
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">الدولة</span>
              <select
                value={f.country}
                onChange={(e) => setF((v) => ({ ...v, country: e.target.value }))}
                className="px-3 py-2 rounded-lg text-sm"
                style={INPUT}
              >
                {COUNTRIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </label>

            {/* المنطقة */}
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">المنطقة / المحافظة</span>
              <input
                value={f.region}
                onChange={(e) => setF((v) => ({ ...v, region: e.target.value }))}
                placeholder="مثال: البيضاء"
                className="px-3 py-2 rounded-lg text-sm"
                style={INPUT}
              />
            </label>

            {/* نظام الوحدات */}
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">نظام الوحدات</span>
              <select
                value={f.units}
                onChange={(e) => setF((v) => ({ ...v, units: e.target.value as FarmUnits }))}
                className="px-3 py-2 rounded-lg text-sm"
                style={INPUT}
              >
                <option value="metric">متري (هكتار، لتر، °م)</option>
                <option value="imperial">إمبراطوري (فدّان، غالون، °ف)</option>
              </select>
            </label>

            {/* العملة */}
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">العملة</span>
              <input
                value={f.currency}
                onChange={(e) => setF((v) => ({ ...v, currency: e.target.value }))}
                placeholder="مثال: YER / SAR / USD"
                className="px-3 py-2 rounded-lg text-sm"
                style={INPUT}
              />
            </label>

            {/* نوع النشاط */}
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className="text-xs text-slate-400">نوع النشاط</span>
              <select
                value={f.activity_type}
                onChange={(e) => setF((v) => ({ ...v, activity_type: e.target.value }))}
                className="px-3 py-2 rounded-lg text-sm"
                style={INPUT}
              >
                <option value="">— اختر نوع النشاط —</option>
                {ACTIVITY_TYPES.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </label>

            {/* الوصف */}
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className="text-xs text-slate-400">وصف (اختياريّ)</span>
              <textarea
                value={f.description}
                onChange={(e) => setF((v) => ({ ...v, description: e.target.value }))}
                rows={3}
                placeholder="نبذة عن المزرعة: المساحة التقريبيّة، المحاصيل الرئيسيّة…"
                className="px-3 py-2 rounded-lg text-sm resize-y"
                style={INPUT}
              />
            </label>
          </div>

          {/* خطأ الخادم — يُعرَض من detail الردّ (لا رسالة مُلفَّقة) */}
          {mut.isError && (
            <p className="flex items-center gap-2 text-xs text-orange-300">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              {apiErrorMessage(mut.error, 'تعذّر إنشاء المزرعة. تحقّق من الاتصال وحاول مرّة أخرى.')}
            </p>
          )}

          <div className="flex justify-end">
            <button
              onClick={onSubmit}
              disabled={!canSubmit}
              className="flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
              style={{ background: '#16a34a' }}
            >
              <Sprout className="w-4 h-4" />
              {mut.isPending ? 'جارٍ الإنشاء…' : 'إنشاء المزرعة'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
