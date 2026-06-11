// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — AddSeasonWithStages.tsx
// نموذج إضافة موسم زراعي كامل:
//   ✅ اختيار محاصيل متعددة (تناوب) مع تلميح ملاءمة GAEZ
//   ✅ تواريخ: تسوية → حراثة → بذار + تحقق تسلسلي
//   ✅ كمية البذور + نوع الري (مع أيقونات)
//   ✅ مراحل إضافية ديناميكية
//   ✅ محاكاة WOFOST عند الحفظ
//   ✅ رسالة تقدم واضحة
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  X, Check, Plus, Trash2, Loader2, Sprout, Droplets,
  Calendar, Wheat, ChevronDown, AlertCircle, Info,
} from 'lucide-react';

interface Stage { name: string; date: string; notes: string; }

interface SeasonData {
  field_id:          string;
  crops:             string[];
  cultivar:          string;
  land_leveling_date:string;
  plowing_date:      string;
  sowing_date:       string;
  season_end:        string;
  seed_rate_kg_ha:   number;
  irrigation_type:   string;
  custom_stages:     Stage[];
}

interface Props {
  fieldId:  string;
  fieldName:string;
  onSave:   (data: SeasonData) => Promise<void>;
  onCancel: () => void;
}

const CROPS = [
  { label:'قمح صلب',    suitability:'S1', emoji:'🌾', desc:'ملاءمة عالية للمنطقة (GAEZ S1)' },
  { label:'شعير',       suitability:'S1', emoji:'🌾', desc:'ملاءمة عالية' },
  { label:'ذرة صفراء', suitability:'S2', emoji:'🌽', desc:'ملاءمة متوسطة' },
  { label:'طماطم',     suitability:'S2', emoji:'🍅', desc:'ملاءمة متوسطة' },
  { label:'بطاطس',     suitability:'S2', emoji:'🥔', desc:'ملاءمة متوسطة — تتطلب ري كافٍ' },
  { label:'خضروات',    suitability:'S3', emoji:'🥬', desc:'ملاءمة منخفضة — تتطلب عناية إضافية' },
  { label:'برسيم',     suitability:'S1', emoji:'🌿', desc:'ملاءمة ممتازة كمحصول ثانوي' },
  { label:'دخن',        suitability:'S3', emoji:'🌿', desc:'مقاوم للجفاف' },
];

const IRRIGATION_TYPES = [
  { value:'drip',       label:'تنقيط',   icon:'💧', desc:'90% كفاءة — الأفضل للمنطقة' },
  { value:'pivot',      label:'محوري',   icon:'🔄', desc:'مناسب للحقول الكبيرة' },
  { value:'flood',      label:'غمر',     icon:'🌊', desc:'70% كفاءة — تكلفة أقل' },
  { value:'sprinkler',  label:'رش',      icon:'🚿', desc:'مناسب للخضروات' },
  { value:'rainfed',    label:'بعل',     icon:'☁️', desc:'يعتمد على الأمطار' },
  { value:'subsurface', label:'تحت سطحي',icon:'⬇️', desc:'كفاءة عالية جداً' },
];

const PREDEFINED_STAGES = [
  'التسميد الأساسي','مكافحة الأعشاب','الرية الأولى','مكافحة الآفات',
  'التسميد التكميلي','التصرف الزائد','الرية قبيل الحصاد','الحصاد',
];

function suitabilityColor(s: string) {
  return s === 'S1' ? '#16a34a' : s === 'S2' ? '#ca8a04' : '#dc2626';
}

export default function AddSeasonWithStages({ fieldId, fieldName, onSave, onCancel }: Props) {
  const [selectedCrops, setSelectedCrops] = useState<string[]>([]);
  const [cultivar,   setCultivar]   = useState('');
  const [landDate,   setLandDate]   = useState('');
  const [plowDate,   setPlowDate]   = useState('');
  const [sowDate,    setSowDate]    = useState('');
  const [endDate,    setEndDate]    = useState('');
  const [seedRate,   setSeedRate]   = useState<string>('');
  const [irrType,    setIrrType]    = useState('drip');
  const [stages,     setStages]     = useState<Stage[]>([]);
  const [saving,     setSaving]     = useState(false);
  const [errors,     setErrors]     = useState<Record<string, string>>({});
  const [showCropPicker, setShowCropPicker] = useState(false);

  const addCrop = (label: string) => {
    if (!selectedCrops.includes(label)) setSelectedCrops(p => [...p, label]);
  };

  const validate = () => {
    const e: Record<string, string> = {};
    if (!selectedCrops.length)  e.crops = 'اختر محصولاً واحداً على الأقل';
    if (!sowDate)                e.sowDate = 'تاريخ البذار مطلوب';
    if (!seedRate || +seedRate <= 0) e.seedRate = 'أدخل كمية البذور';
    if (landDate && plowDate && plowDate < landDate)
      e.plowDate = 'تاريخ الحراثة يجب أن يكون بعد تسوية الأرض';
    if (plowDate && sowDate && sowDate < plowDate)
      e.sowDate = 'تاريخ البذار يجب أن يكون بعد الحراثة';
    if (endDate && sowDate && endDate < sowDate)
      e.endDate = 'نهاية الموسم يجب أن تكون بعد البذار';
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;
    setSaving(true);
    try {
      await onSave({
        field_id:           fieldId,
        crops:              selectedCrops,
        cultivar:           cultivar,
        land_leveling_date: landDate,
        plowing_date:       plowDate,
        sowing_date:        sowDate,
        season_end:         endDate,
        seed_rate_kg_ha:    +seedRate,
        irrigation_type:    irrType,
        custom_stages:      stages,
      });
    } catch (e: any) {
      setErrors({ general: e?.message || 'فشل الحفظ' });
    } finally {
      setSaving(false);
    }
  };

  const addStage = () => setStages(p => [...p, { name:'', date:'', notes:'' }]);
  const updateStage = (i: number, k: keyof Stage, v: string) =>
    setStages(p => p.map((s, idx) => idx === i ? { ...s, [k]: v } : s));
  const removeStage = (i: number) =>
    setStages(p => p.filter((_, idx) => idx !== i));

  const Err = ({ field }: { field: string }) =>
    errors[field] ? (
      <p className="text-xs text-red-400 mt-0.5 flex items-center gap-1">
        <AlertCircle className="w-3 h-3" />{errors[field]}
      </p>
    ) : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background:'rgba(0,0,0,0.7)' }}>
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl shadow-2xl"
        style={{ background:'#1e293b', border:'1px solid #334155' }}>

        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-3.5 border-b"
          style={{ background:'#1e293b', borderColor:'#334155' }}>
          <div className="flex items-center gap-2">
            <Sprout className="w-5 h-5 text-emerald-400" />
            <div>
              <h2 className="font-bold text-slate-100 text-sm">إضافة موسم زراعي</h2>
              <p className="text-[11px] text-slate-400">{fieldName}</p>
            </div>
          </div>
          <button onClick={onCancel} className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-400">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-5" dir="rtl">
          {/* ① المحاصيل */}
          <div>
            <label className="block text-sm font-semibold text-slate-200 mb-2 flex items-center gap-2">
              <Wheat className="w-4 h-4 text-emerald-400" /> المحصول / المحاصيل *
            </label>
            {/* Selected badges */}
            <div className="flex flex-wrap gap-2 mb-2 min-h-[32px]">
              {selectedCrops.map(c => {
                const cd = CROPS.find(x => x.label === c);
                return (
                  <span key={c} className="flex items-center gap-1 px-2.5 py-1 rounded-full text-sm"
                    style={{ background:'#1e3a1e', color:'#4ade80', border:'1px solid #16a34a44' }}>
                    {cd?.emoji} {c}
                    <button onClick={() => setSelectedCrops(p => p.filter(x => x !== c))}
                      className="hover:text-red-400 text-emerald-600 ml-1">×</button>
                  </span>
                );
              })}
              <button onClick={() => setShowCropPicker(!showCropPicker)}
                className="flex items-center gap-1 px-2.5 py-1 rounded-full text-sm border border-dashed text-slate-400 hover:text-slate-200"
                style={{ borderColor:'#475569' }}>
                <Plus className="w-3 h-3" /> إضافة محصول
              </button>
            </div>
            <Err field="crops" />

            {/* Crop picker */}
            {showCropPicker && (
              <div className="rounded-xl p-3 grid grid-cols-2 gap-2 mt-2"
                style={{ background:'#0f1117', border:'1px solid #334155' }}>
                {CROPS.map(c => (
                  <button key={c.label} onClick={() => { addCrop(c.label); setShowCropPicker(false); }}
                    disabled={selectedCrops.includes(c.label)}
                    className="flex items-center gap-2 p-2 rounded-lg text-sm text-right transition-colors hover:bg-slate-800 disabled:opacity-40">
                    <span className="text-lg">{c.emoji}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-slate-200 font-medium">{c.label}</div>
                      <div className="text-[10px]" style={{ color: suitabilityColor(c.suitability) }}>
                        {c.suitability} — {c.desc}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* ② التواريخ */}
          <div>
            <label className="block text-sm font-semibold text-slate-200 mb-2 flex items-center gap-2">
              <Calendar className="w-4 h-4 text-emerald-400" /> تواريخ إعداد الأرض والبذار
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label:'تسوية الأرض',  val:landDate,  set:setLandDate,  key:'landDate',  tip:'' },
                { label:'حراثة الأرض', val:plowDate,  set:setPlowDate,  key:'plowDate',  tip:'بعد التسوية' },
                { label:'البذار *',     val:sowDate,   set:setSowDate,   key:'sowDate',   tip:'بعد الحراثة' },
                { label:'نهاية الموسم', val:endDate,   set:setEndDate,   key:'endDate',   tip:'حصاد متوقّع' },
              ].map(f => (
                <div key={f.key}>
                  <label className="block text-xs text-slate-400 mb-1">
                    {f.label} {f.tip && <span className="text-slate-600">({f.tip})</span>}
                  </label>
                  <input type="date" value={f.val} onChange={e => f.set(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg text-sm"
                    style={{ background:'#0f1117', border:`1px solid ${errors[f.key]?'#dc2626':'#334155'}`, color:'#e2e8f0' }} />
                  <Err field={f.key} />
                </div>
              ))}
            </div>
          </div>

          {/* ③ الصنف + البذور + الري */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1">الصنف (اختياري)</label>
              <input value={cultivar} onChange={e => setCultivar(e.target.value)}
                placeholder="مثال: صنف محلّي / Yecora"
                className="w-full px-3 py-2 rounded-lg text-sm"
                style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }} />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">كمية البذور (كجم/هـ) *</label>
              <input type="number" value={seedRate} onChange={e => setSeedRate(e.target.value)}
                placeholder="مثال: 120"
                className="w-full px-3 py-2 rounded-lg text-sm"
                style={{ background:'#0f1117', border:`1px solid ${errors.seedRate?'#dc2626':'#334155'}`, color:'#e2e8f0' }} />
              <Err field="seedRate" />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">نوع الري</label>
              <select value={irrType} onChange={e => setIrrType(e.target.value)}
                className="w-full px-3 py-2 rounded-lg text-sm"
                style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
                {IRRIGATION_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.icon} {t.label} — {t.desc}</option>
                ))}
              </select>
            </div>
          </div>

          {/* ④ مراحل إضافية */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <Plus className="w-4 h-4 text-emerald-400" /> مراحل إضافية <span className="text-slate-500 font-normal text-xs">(اختياري)</span>
              </label>
              <button onClick={addStage}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs text-emerald-400 hover:text-emerald-300"
                style={{ background:'#1e3a1e' }}>
                <Plus className="w-3 h-3" /> إضافة مرحلة
              </button>
            </div>
            {stages.map((st, i) => (
              <div key={i} className="flex gap-2 mb-2 items-start">
                <div className="flex-1">
                  <select value={st.name} onChange={e => updateStage(i,'name',e.target.value)}
                    className="w-full px-2 py-1.5 rounded-lg text-sm mb-1"
                    style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
                    <option value="">اختر أو اكتب اسم المرحلة</option>
                    {PREDEFINED_STAGES.map(s => <option key={s}>{s}</option>)}
                  </select>
                </div>
                <input type="date" value={st.date} onChange={e => updateStage(i,'date',e.target.value)}
                  className="w-36 px-2 py-1.5 rounded-lg text-sm"
                  style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }} />
                <button onClick={() => removeStage(i)} className="p-1.5 text-red-400 hover:text-red-300 mt-0.5">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>

          {/* ⑤ WOFOST info */}
          <div className="rounded-xl p-3 text-xs flex items-start gap-2" style={{ background:'#172032', border:'1px solid #1e3a4a' }}>
            <Info className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />
            <p className="text-slate-400">
              عند الحفظ سيتم تشغيل محاكاة <strong className="text-blue-400">WOFOST-RUE-v8</strong> تلقائياً لحساب:
              إنتاجية متوقعة، GDD، LAI، احتياجات الري والتسميد. قد يستغرق ذلك حتى دقيقة.
            </p>
          </div>

          {errors.general && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm"
              style={{ background:'#1a000022', border:'1px solid #dc262633', color:'#f87171' }}>
              <AlertCircle className="w-4 h-4" /> {errors.general}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2 justify-end pt-2 border-t" style={{ borderColor:'#334155' }}>
            <button onClick={onCancel} className="px-4 py-2 rounded-lg text-sm text-slate-400 border hover:text-slate-200"
              style={{ borderColor:'#334155' }}>إلغاء</button>
            <button onClick={handleSave} disabled={saving}
              className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white"
              style={{ background: saving ? '#15803d' : '#16a34a' }}>
              {saving
                ? <><Loader2 className="w-4 h-4 animate-spin" /> جاري الحفظ والمحاكاة...</>
                : <><Check className="w-4 h-4" /> حفظ الموسم وبدء WOFOST</>
              }
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
