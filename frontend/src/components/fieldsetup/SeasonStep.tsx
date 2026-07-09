// ═══════════════════════════════════════════════════════════════
// SAHOOL — fieldsetup/SeasonStep.tsx  (الخطوة 2 من معالج تهيئة الحقل)
// اختيار الموسم: محصول (واحد أو أكثر) + نوع الريّ + تاريخ البذار (+ نهاية
// الموسم + إنتاجيّة مستهدفة اختياريّة). إلزاميّة (لا تُتخطّى).
// النقطة الخلفيّة الحقيقيّة:
//   POST /api/v1/fields/{field_id}/seasons
//   body: { crops, cultivar?, irrigation_type?, seed_rate_kg_ha?, sowing_date?,
//           season_end?, target_yield_kg_ha?, tillage_type?, maturity?,
//           actual_yield_kg_ha?, notes_ar? }
// المفردات (محاصيل/ريّ) مأخوذة من نفس قاموس AddSeasonWithStages القائم —
// لا مفردات جديدة مخترَعة.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Sprout, Wheat, Plus } from 'lucide-react';
import { kongApi, apiErrorMessage } from '../../services/api';
import StepShell from './StepShell';
import type { FieldSetupStepProps } from './types';

// نفس مفردات المحاصيل في AddSeasonWithStages (قاموس ثابت قائم — لا توسيع للمفردات).
const CROPS = [
  { label: 'قمح صلب', emoji: '🌾' },
  { label: 'شعير', emoji: '🌾' },
  { label: 'ذرة صفراء', emoji: '🌽' },
  { label: 'طماطم', emoji: '🍅' },
  { label: 'بطاطس', emoji: '🥔' },
  { label: 'خضروات', emoji: '🥬' },
  { label: 'برسيم', emoji: '🌿' },
  { label: 'دخن', emoji: '🌿' },
];

// نفس مفردات نوع الريّ في AddSeasonWithStages.
const IRRIGATION_TYPES = [
  { value: 'drip', label: 'تنقيط', icon: '💧' },
  { value: 'pivot', label: 'محوري', icon: '🔄' },
  { value: 'flood', label: 'غمر', icon: '🌊' },
  { value: 'sprinkler', label: 'رش', icon: '🚿' },
  { value: 'rainfed', label: 'بعل', icon: '☁️' },
  { value: 'subsurface', label: 'تحت سطحي', icon: '⬇️' },
];

// خيارات مرحلة النضج (v52) — early/medium/late مقابل تسميات عربيّة.
const MATURITY_OPTIONS = [
  { value: '', label: '— غير محدّد —' },
  { value: 'early', label: 'مبكّر' },
  { value: 'medium', label: 'متوسّط' },
  { value: 'late', label: 'متأخّر' },
];

// اقتراحات نوع الحراثة (v52) — حقل حرّ مع لائحة datalist (لا قيود على المفردات).
const TILLAGE_SUGGESTIONS = ['حراثة تقليديّة', 'بدون حراثة', 'حراثة شريطيّة'];

export default function SeasonStep({
  ctx, onNext, onBack, canGoBack, stepIndex, stepTotal,
}: FieldSetupStepProps) {
  // محصول الحقل الافتراضيّ مُهيّأ مُسبقاً إن كان ضمن المفردات المعروفة.
  const initialCrop = CROPS.some(c => c.label === ctx.crop) ? [ctx.crop] : [];
  const [crops, setCrops] = useState<string[]>(initialCrop);
  const [cultivar, setCultivar] = useState('');
  const [irrType, setIrrType] = useState('drip');
  const [sowDate, setSowDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [targetYield, setTargetYield] = useState('');
  // حقول أغرونوميّة (v52) تُحفظ فعليّاً عبر POST seasons.
  const [seedRate, setSeedRate] = useState('');
  const [tillageType, setTillageType] = useState('');
  const [maturity, setMaturity] = useState('');
  const [actualYield, setActualYield] = useState('');
  const [notesAr, setNotesAr] = useState('');
  const [showOptional, setShowOptional] = useState(false);
  const [showPicker, setShowPicker] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const toggleCrop = (label: string) =>
    setCrops(p => p.includes(label) ? p.filter(x => x !== label) : [...p, label]);

  // يحلّل رقماً غير سالب من نصّ حقل؛ يُعيد undefined إن كان فارغاً، أو null إن غير صالح.
  const parseNonNeg = (s: string): number | null | undefined => {
    if (!s.trim()) return undefined;
    const n = Number(s);
    if (!Number.isFinite(n) || n < 0) return null;
    return n;
  };

  const handleNext = async () => {
    if (!crops.length) { setError('اختر محصولاً واحداً على الأقلّ'); return; }
    if (endDate && sowDate && endDate < sowDate) {
      setError('نهاية الموسم يجب أن تكون بعد البذار'); return;
    }
    const seedRateVal = parseNonNeg(seedRate);
    if (seedRateVal === null) {
      setError('كمية البذور يجب أن تكون رقماً غير سالب'); return;
    }
    const actualYieldVal = parseNonNeg(actualYield);
    if (actualYieldVal === null) {
      setError('الغلّة الفعليّة يجب أن تكون رقماً غير سالب'); return;
    }
    const targetYieldVal = parseNonNeg(targetYield);
    if (targetYieldVal === null) {
      setError('الإنتاجيّة المستهدفة يجب أن تكون رقماً غير سالب'); return;
    }
    setSaving(true); setError('');
    try {
      // نداء حقيقيّ على عقد الخلفيّة المُتّفق عليه (الحقول الأغرونوميّة داخل جسم الموسم).
      await kongApi.post(`/api/v1/fields/${ctx.fieldId}/seasons`, {
        crops,
        cultivar: cultivar.trim() || undefined,
        irrigation_type: irrType,
        seed_rate_kg_ha: seedRateVal,
        sowing_date: sowDate || undefined,
        season_end: endDate || undefined,
        target_yield_kg_ha: targetYieldVal,
        tillage_type: tillageType.trim() || undefined,
        maturity: maturity || undefined,
        actual_yield_kg_ha: actualYieldVal,
        notes_ar: notesAr.trim() || undefined,
      });
      onNext();
    } catch (e: unknown) {
      setError(apiErrorMessage(e, 'تعذّر حفظ الموسم — تحقّق من القاعدة/الصلاحيّة والتواريخ.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <StepShell
      title="موسم زراعي"
      subtitle={ctx.fieldName}
      icon={<Sprout className="w-5 h-5" />}
      stepIndex={stepIndex}
      stepTotal={stepTotal}
      optional={false}
      canGoBack={canGoBack}
      onBack={onBack}
      onNext={handleNext}
      nextLabel="حفظ الموسم"
      saving={saving}
      error={error}
    >
      {/* المحاصيل */}
      <div>
        <label className="block text-sm font-semibold text-slate-200 mb-2 flex items-center gap-2">
          <Wheat className="w-4 h-4 text-emerald-400" /> المحصول / المحاصيل *
        </label>
        <div className="flex flex-wrap gap-2 mb-2 min-h-[32px]">
          {crops.map(c => {
            const cd = CROPS.find(x => x.label === c);
            return (
              <span key={c} className="flex items-center gap-1 px-2.5 py-1 rounded-full text-sm"
                style={{ background: '#1e3a1e', color: '#4ade80', border: '1px solid #16a34a44' }}>
                {cd?.emoji} {c}
                <button onClick={() => toggleCrop(c)} className="hover:text-red-400 text-emerald-600 ml-1">×</button>
              </span>
            );
          })}
          <button onClick={() => setShowPicker(p => !p)}
            className="flex items-center gap-1 px-2.5 py-1 rounded-full text-sm border border-dashed text-slate-400 hover:text-slate-200"
            style={{ borderColor: '#475569' }}>
            <Plus className="w-3 h-3" /> إضافة محصول
          </button>
        </div>
        {showPicker && (
          <div className="rounded-xl p-3 grid grid-cols-2 sm:grid-cols-3 gap-2 mt-1"
            style={{ background: '#0f1117', border: '1px solid #334155' }}>
            {CROPS.map(c => (
              <button key={c.label} onClick={() => { toggleCrop(c.label); setShowPicker(false); }}
                disabled={crops.includes(c.label)}
                className="flex items-center gap-2 p-2 rounded-lg text-sm text-right hover:bg-slate-800 disabled:opacity-40">
                <span className="text-lg">{c.emoji}</span>
                <span className="text-slate-200">{c.label}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* الصنف + نوع الريّ */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">الصنف (اختياري)</label>
          <input value={cultivar} onChange={e => setCultivar(e.target.value)}
            placeholder="مثال: صنف محلّي / Yecora"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">نوع الريّ</label>
          <select value={irrType} onChange={e => setIrrType(e.target.value)}
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
            {IRRIGATION_TYPES.map(t => (
              <option key={t.value} value={t.value}>{t.icon} {t.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* تواريخ + إنتاجيّة مستهدفة */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">تاريخ البذار</label>
          <input type="date" value={sowDate} onChange={e => setSowDate(e.target.value)}
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">نهاية الموسم (حصاد متوقّع)</label>
          <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">إنتاجيّة مستهدفة (كجم/هـ)</label>
          <input type="number" min={0} value={targetYield} onChange={e => setTargetYield(e.target.value)}
            placeholder="اختياري"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
        </div>
      </div>

      {/* حقول أغرونوميّة (v52): كمية البذور + نوع الحراثة + مرحلة النضج — تُحفظ فعليّاً */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">كمية البذور (كجم/هـ)</label>
          <input type="number" min={0} value={seedRate} onChange={e => setSeedRate(e.target.value)}
            placeholder="اختياري"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">نوع الحراثة</label>
          <input list="tillage-suggestions" value={tillageType} onChange={e => setTillageType(e.target.value)}
            placeholder="مثال: حراثة تقليديّة / بدون حراثة"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
          <datalist id="tillage-suggestions">
            {TILLAGE_SUGGESTIONS.map(t => <option key={t} value={t} />)}
          </datalist>
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">مرحلة النضج</label>
          <select value={maturity} onChange={e => setMaturity(e.target.value)}
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
            {MATURITY_OPTIONS.map(m => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* منطقة اختياريّة (ما بعد الحصاد + ملاحظات) — مطويّة لتجنّب الإرباك */}
      <div>
        <button type="button" onClick={() => setShowOptional(p => !p)}
          className="text-xs text-slate-400 hover:text-slate-200">
          {showOptional ? '▾ إخفاء الحقول الاختياريّة' : '▸ حقول اختياريّة (ما بعد الحصاد + ملاحظات)'}
        </button>
        {showOptional && (
          <div className="mt-2 grid grid-cols-1 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">الغلّة الفعليّة (كجم/هـ)</label>
              <input type="number" min={0} value={actualYield} onChange={e => setActualYield(e.target.value)}
                placeholder="اختياري — تُسجَّل بعد الحصاد"
                className="w-full px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">ملاحظات</label>
              <textarea value={notesAr} onChange={e => setNotesAr(e.target.value)} rows={3}
                placeholder="ملاحظات حرّة على الموسم (اختياري)"
                className="w-full px-3 py-2 rounded-lg text-sm resize-y"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </div>
          </div>
        )}
      </div>
    </StepShell>
  );
}
