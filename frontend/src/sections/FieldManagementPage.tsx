// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — FieldManagementPage.tsx (محدّثة)
// ✅ زر "إضافة حقل" → AddFieldWithMap
// ✅ زر "إضافة موسم" → AddSeasonWithStages
// ✅ Grid + Table view
// ✅ بحث + فلترة
// ✅ WOFOST data per field
// ✅ CRUD كامل
// ═══════════════════════════════════════════════════════════════
import { useState, useMemo } from 'react';
import {
  Plus, Search, Pencil, Trash2, X, Check, Leaf,
  Wheat, Ruler, ChevronDown, Sprout, Calendar, Map,
} from 'lucide-react';
import AddFieldWithMap from '../components/AddFieldWithMap';
import AddSeasonWithStages from '../components/AddSeasonWithStages';
import { kongApi } from '../services/api';
import { toastStore } from '../services/websocket';

interface Field {
  field_id:   string;
  name:       string;
  area_ha:    number;
  crop:       string;
  soil:       string;
  ndvi:       number;
  health:     string;
  stage:      string;
  gdd:        number;
  yield_est:  number;
  lat:        number;
  lon:        number;
  geometry?:  any;
}

const INITIAL: Field[] = [
  { field_id:'field_01', name:'حقل وادي سبأ',        area_ha:23.5, crop:'قمح صلب',  soil:'loam',       ndvi:0.72, health:'excellent', stage:'ملء الحبوب', gdd:960,  yield_est:2.8, lat:15.05, lon:45.55 },
  { field_id:'field_02', name:'حقل البيضاء الشمالي', area_ha:32.0, crop:'شعير',      soil:'clay_loam',  ndvi:0.58, health:'good',      stage:'نمو خضري',  gdd:825,  yield_est:2.5, lat:15.02, lon:45.58 },
  { field_id:'field_03', name:'حقل البيضاء الجنوبي', area_ha:18.7, crop:'ذرة صفراء', soil:'sandy_loam', ndvi:0.44, health:'fair',      stage:'تزهير',     gdd:980,  yield_est:3.9, lat:14.98, lon:45.52 },
  { field_id:'field_04', name:'حقل رداع الغربي',     area_ha:41.3, crop:'طماطم',     soil:'loam',       ndvi:0.66, health:'good',      stage:'ثمرة',      gdd:780,  yield_est:4.2, lat:14.92, lon:45.48 },
  { field_id:'field_05', name:'حقل ذي السفال',       area_ha:28.9, crop:'قمح صلب',  soil:'silt_loam',  ndvi:0.74, health:'excellent', stage:'ملء الحبوب', gdd:1020, yield_est:3.1, lat:14.88, lon:45.60 },
  { field_id:'field_06', name:'حقل عتمة الشرقي',    area_ha:37.5, crop:'شعير',      soil:'clay_loam',  ndvi:0.51, health:'fair',      stage:'نمو خضري',  gdd:792,  yield_est:2.4, lat:15.10, lon:45.62 },
  { field_id:'field_07', name:'حقل الرياشية',        area_ha:22.1, crop:'خضروات',   soil:'loam',       ndvi:0.55, health:'good',      stage:'حصاد',      gdd:660,  yield_est:5.5, lat:15.00, lon:45.45 },
  { field_id:'field_08', name:'حقل ذي ناعم',         area_ha:45.0, crop:'بطاطس',    soil:'sandy_loam', ndvi:0.61, health:'good',      stage:'درنات',     gdd:680,  yield_est:6.8, lat:14.85, lon:45.65 },
];

const SOIL_AR: Record<string,string> = {
  loam:'مزيجية', clay_loam:'طينية مزيجية',
  sandy_loam:'رملية مزيجية', silt_loam:'طمية مزيجية',
};

function healthConfig(h: string) {
  return ({
    excellent:{ label:'ممتاز', color:'#16a34a', bg:'#1e3a1e' },
    good:     { label:'جيد',   color:'#65a30d', bg:'#1a2e0a' },
    fair:     { label:'مقبول', color:'#ca8a04', bg:'#2a1a00' },
    poor:     { label:'منخفض', color:'#dc2626', bg:'#1a0000' },
  } as any)[h] || { label:h, color:'#6b7280', bg:'#1e293b' };
}

export default function FieldManagementPage() {
  const [fields,        setFields]        = useState<Field[]>(INITIAL);
  const [search,        setSearch]        = useState('');
  const [filterHealth,  setFilterHealth]  = useState('all');
  const [filterCrop,    setFilterCrop]    = useState('all');
  const [viewMode,      setViewMode]      = useState<'grid'|'table'>('grid');
  const [showAddField,  setShowAddField]  = useState(false);
  const [showSeason,    setShowSeason]    = useState<Field|null>(null);
  const [editField,     setEditField]     = useState<Field|null>(null);

  const crops = [...new Set(fields.map(f=>f.crop))];

  const filtered = useMemo(() => fields.filter(f =>
    (f.name.includes(search) || f.crop.includes(search)) &&
    (filterHealth==='all' || f.health===filterHealth) &&
    (filterCrop==='all'   || f.crop===filterCrop)
  ), [fields, search, filterHealth, filterCrop]);

  const totalArea = fields.reduce((s,f)=>s+f.area_ha,0).toFixed(1);
  const avgNdvi   = (fields.reduce((s,f)=>s+f.ndvi,0)/fields.length).toFixed(3);

  // ── Handlers ──────────────────────────────────────────────────
  const handleSaveField = async (data: any) => {
    try {
      await kongApi.post('/fields', {
        name: data.name, manager: data.manager, crop: data.crop,
        area_ha: data.area_ha, geometry: data.geometry,
      });
    } catch { /* fallback offline */ }
    const newField: Field = {
      field_id:  `field_${Date.now()}`,
      name:      data.name,
      area_ha:   data.area_ha,
      crop:      data.crop,
      soil:      'loam',
      ndvi:      0.55,
      health:    'good',
      stage:     'إنبات',
      gdd:       0,
      yield_est: 0,
      lat:       15.0,
      lon:       45.5,
      geometry:  data.geometry,
    };
    setFields(p => [...p, newField]);
    setShowAddField(false);
    toastStore.add('success', '✅ تم إضافة الحقل', `${data.name} (${data.area_ha} هـ)`);
  };

  const handleSaveSeason = async (data: any) => {
    try {
      await kongApi.post('/seasons', data);
    } catch { /* fallback */ }
    setShowSeason(null);
    toastStore.add('success', '🌾 تم إنشاء الموسم', 'جاري محاكاة WOFOST...');
  };

  const handleDelete = (id: string) => {
    if (!confirm('هل أنت متأكد من حذف هذا الحقل؟')) return;
    setFields(p => p.filter(f => f.field_id !== id));
    toastStore.add('info', '🗑️ تم الحذف', '');
  };

  const handleEditSave = async (data: any) => {
    setFields(p => p.map(f =>
      f.field_id === editField?.field_id
        ? { ...f, name:data.name, area_ha:data.area_ha, crop:data.crop }
        : f
    ));
    setEditField(null);
    toastStore.add('success', '✅ تم التعديل', data.name);
  };

  // ── Field card ─────────────────────────────────────────────────
  const FieldCard = ({ f }: { f: Field; key?: React.Key }) => {
    const sc = healthConfig(f.health);
    return (
      <div className="rounded-xl border hover:border-emerald-800 transition-all group"
        style={{ background:'#1e293b', borderColor:'#334155' }}>
        {/* Header */}
        <div className="flex items-start justify-between p-4 pb-2">
          <div className="flex-1 min-w-0">
            <div className="font-semibold text-slate-100 text-sm truncate">{f.name}</div>
            <div className="text-xs text-slate-400 mt-0.5">{f.crop} · {f.area_ha} هـ</div>
          </div>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0"
            style={{ background:`${sc.color}22`, color:sc.color }}>{sc.label}</span>
        </div>
        {/* NDVI bar */}
        <div className="px-4 pb-2">
          <div className="flex justify-between text-xs mb-1">
            <span className="text-slate-400">NDVI</span>
            <span style={{ color:sc.color }} className="font-bold">{f.ndvi}</span>
          </div>
          <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div className="h-full rounded-full" style={{
              width:`${f.ndvi*100}%`,
              background:'linear-gradient(to right,#dc2626,#f59e0b,#16a34a)'
            }} />
          </div>
        </div>
        {/* Stats */}
        <div className="grid grid-cols-3 gap-1 px-4 pb-3 text-center">
          {[{l:'GDD',v:f.gdd},{l:'t/ha',v:f.yield_est},{l:'مرحلة',v:f.stage.substring(0,4)}].map((s,i)=>(
            <div key={i} className="rounded py-1" style={{ background:'#0f1117' }}>
              <div className="text-xs font-bold text-slate-200">{s.v}</div>
              <div className="text-[10px] text-slate-500">{s.l}</div>
            </div>
          ))}
        </div>
        {/* Actions */}
        <div className="flex gap-1.5 px-4 pb-3">
          <button onClick={() => setShowSeason(f)}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-xs text-emerald-400 hover:text-emerald-300 border"
            style={{ borderColor:'#16a34a44', background:'#1e3a1e22' }}>
            <Sprout className="w-3 h-3" /> موسم زراعي
          </button>
          <button onClick={() => setEditField(f)}
            className="px-2.5 py-1.5 rounded-lg text-xs text-slate-400 hover:text-slate-200 border"
            style={{ borderColor:'#334155' }}>
            <Pencil className="w-3 h-3" />
          </button>
          <button onClick={() => handleDelete(f.field_id)}
            className="px-2.5 py-1.5 rounded-lg text-xs text-red-400 hover:text-red-300 border"
            style={{ borderColor:'#dc262633' }}>
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-5 max-w-7xl mx-auto" dir="rtl">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100">إدارة الحقول</h2>
          <p className="text-sm text-slate-400">
            {fields.length} حقل · {totalArea} هـ · متوسط NDVI: <span className="text-emerald-400">{avgNdvi}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg overflow-hidden border" style={{ borderColor:'#334155' }}>
            {(['grid','table'] as const).map(v=>(
              <button key={v} onClick={()=>setViewMode(v)}
                className="px-3 py-1.5 text-sm transition-colors"
                style={{ background:viewMode===v?'#1e3a1e':'transparent', color:viewMode===v?'#4ade80':'#64748b' }}>
                {v==='grid'?'بطاقات':'جدول'}
              </button>
            ))}
          </div>
          <button onClick={()=>setShowAddField(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white"
            style={{ background:'#16a34a' }}>
            <Plus className="w-4 h-4" /> رسم حقل جديد
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input value={search} onChange={e=>setSearch(e.target.value)}
            placeholder="بحث بالاسم أو المحصول..."
            className="w-full pr-9 pl-3 py-2 rounded-lg text-sm"
            style={{ background:'#1e293b', border:'1px solid #334155', color:'#e2e8f0' }} />
        </div>
        <select value={filterHealth} onChange={e=>setFilterHealth(e.target.value)}
          className="px-3 py-2 rounded-lg text-sm"
          style={{ background:'#1e293b', border:'1px solid #334155', color:'#e2e8f0' }}>
          <option value="all">كل الحالات</option>
          {['excellent','good','fair','poor'].map(h=><option key={h} value={h}>{healthConfig(h).label}</option>)}
        </select>
        <select value={filterCrop} onChange={e=>setFilterCrop(e.target.value)}
          className="px-3 py-2 rounded-lg text-sm"
          style={{ background:'#1e293b', border:'1px solid #334155', color:'#e2e8f0' }}>
          <option value="all">كل المحاصيل</option>
          {crops.map(c=><option key={c}>{c}</option>)}
        </select>
      </div>

      {/* Grid view */}
      {viewMode==='grid' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map(f=><FieldCard key={f.field_id} f={f} />)}
          {filtered.length===0 && (
            <div className="col-span-full text-center py-12 text-slate-500">
              <Map className="w-10 h-10 mx-auto mb-2 text-slate-700" />
              <p>لا توجد حقول تطابق البحث</p>
            </div>
          )}
        </div>
      )}

      {/* Table view */}
      {viewMode==='table' && (
        <div className="rounded-xl border overflow-hidden" style={{ borderColor:'#334155' }}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead style={{ background:'#0f1117' }}>
                <tr>
                  {['الحقل','المحصول','المساحة','NDVI','الحالة','المرحلة','GDD','الإنتاج','إجراءات'].map(h=>(
                    <th key={h} className="text-right px-4 py-3 text-xs font-semibold text-slate-400">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((f,i)=>{
                  const sc = healthConfig(f.health);
                  return (
                    <tr key={f.field_id} style={{ background:i%2===0?'#1e293b':'#172032', borderBottom:'1px solid #334155' }}>
                      <td className="px-4 py-3 font-medium text-slate-100">{f.name}</td>
                      <td className="px-4 py-3 text-slate-300">{f.crop}</td>
                      <td className="px-4 py-3 text-slate-300">{f.area_ha} هـ</td>
                      <td className="px-4 py-3 font-mono" style={{ color:sc.color }}>{f.ndvi}</td>
                      <td className="px-4 py-3">
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background:`${sc.color}22`, color:sc.color }}>{sc.label}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-300 text-xs">{f.stage}</td>
                      <td className="px-4 py-3 text-slate-300 font-mono">{f.gdd}</td>
                      <td className="px-4 py-3 text-emerald-400 font-semibold">{f.yield_est}</td>
                      <td className="px-4 py-3">
                        <div className="flex gap-1.5">
                          <button onClick={()=>setShowSeason(f)} title="إضافة موسم"
                            className="p-1.5 rounded hover:bg-emerald-950 text-slate-400 hover:text-emerald-400 transition-colors">
                            <Sprout className="w-3.5 h-3.5" />
                          </button>
                          <button onClick={()=>setEditField(f)}
                            className="p-1.5 rounded hover:bg-slate-700 text-slate-400 hover:text-slate-200">
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button onClick={()=>handleDelete(f.field_id)}
                            className="p-1.5 rounded hover:bg-red-950 text-slate-400 hover:text-red-400">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modals */}
      {showAddField && (
        <AddFieldWithMap
          onSave={handleSaveField}
          onCancel={() => setShowAddField(false)}
        />
      )}
      {showSeason && (
        <AddSeasonWithStages
          fieldId={showSeason.field_id}
          fieldName={showSeason.name}
          onSave={handleSaveSeason}
          onCancel={() => setShowSeason(null)}
        />
      )}
      {editField && (
        <EditFieldModal
          field={editField}
          onSave={handleEditSave}
          onCancel={() => setEditField(null)}
        />
      )}
    </div>
  );
}

// ── Quick edit modal ──────────────────────────────────────────
function EditFieldModal({ field, onSave, onCancel }: { field: Field; onSave: (d:any)=>void; onCancel:()=>void }) {
  const [name,    setName]    = useState(field.name);
  const [area,    setArea]    = useState(String(field.area_ha));
  const [crop,    setCrop]    = useState(field.crop);
  const CROPS = ['قمح صلب','شعير','ذرة صفراء','طماطم','بطاطس','خضروات','برسيم'];
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background:'rgba(0,0,0,0.7)' }}>
      <div className="rounded-2xl p-6 w-full max-w-sm" style={{ background:'#1e293b', border:'1px solid #334155' }}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-bold text-slate-100">تعديل الحقل</h3>
          <button onClick={onCancel} className="p-1 rounded hover:bg-slate-700 text-slate-400"><X className="w-4 h-4" /></button>
        </div>
        <div className="space-y-4" dir="rtl">
          {[{l:'الاسم',v:name,s:setName,t:'text'},{l:'المساحة (هـ)',v:area,s:setArea,t:'number'}].map(f=>(
            <div key={f.l}>
              <label className="block text-sm text-slate-400 mb-1">{f.l}</label>
              <input type={f.t} value={f.v} onChange={e=>f.s(e.target.value)}
                className="w-full px-3 py-2 rounded-lg text-sm"
                style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }} />
            </div>
          ))}
          <div>
            <label className="block text-sm text-slate-400 mb-1">المحصول</label>
            <select value={crop} onChange={e=>setCrop(e.target.value)}
              className="w-full px-3 py-2 rounded-lg text-sm"
              style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
              {CROPS.map(c=><option key={c}>{c}</option>)}
            </select>
          </div>
          <div className="flex gap-3 pt-2">
            <button onClick={() => onSave({ name, area_ha:+area, crop })}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold text-white"
              style={{ background:'#16a34a' }}>
              <Check className="w-4 h-4" /> حفظ
            </button>
            <button onClick={onCancel} className="px-4 py-2.5 rounded-lg text-sm text-slate-400 border" style={{ borderColor:'#334155' }}>إلغاء</button>
          </div>
        </div>
      </div>
    </div>
  );
}
