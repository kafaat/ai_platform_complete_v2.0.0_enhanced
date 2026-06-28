// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — FieldManagementPage.tsx (محدّثة)
// ✅ زر "إضافة حقل" → AddFieldWithMap
// ✅ زر "إضافة موسم" → AddSeasonWithStages
// ✅ Grid + Table view
// ✅ بحث + فلترة
// ✅ WOFOST data per field
// ✅ CRUD كامل
// ═══════════════════════════════════════════════════════════════
import { useState, useMemo, useEffect } from 'react';
import {
  Plus, Search, Pencil, Trash2, X, Check, Leaf,
  Wheat, Ruler, ChevronDown, Sprout, Calendar, Map, ClipboardList, Satellite,
} from 'lucide-react';
import AddFieldWithMap from '../components/AddFieldWithMap';
import AddSeasonWithStages from '../components/AddSeasonWithStages';
import FieldDetailPanel from '../components/FieldDetailPanel';
import FieldSetupWizard from '../components/fieldsetup/FieldSetupWizard';
import FieldIndicatorMap from '../components/FieldIndicatorMap';
import { kongApi, asApiError } from '../services/api';
import { toastStore } from '../services/websocket';
import { useFields, useSimulateSeason } from '../hooks/useApi';
import type { SeasonSimResult } from '../services/api';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';

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

function ndviHealth(n: number): string {
  return n >= 0.70 ? 'excellent' : n >= 0.50 ? 'good' : n >= 0.30 ? 'fair' : 'poor';
}

// تطبيع حقل من /fields لشكل العرض. دفاعيّ: الحقول الناقصة من الخادم تُحايَد
// (تُعرَض «—»/صفر) لا تُفبرَك — لا قيم زراعيّة مخترَعة.
function mapField(f: Record<string, unknown>): Field {
  const num = (v: unknown, d = 0) => (typeof v === 'number' ? v : Number(v) || d);
  const str = (v: unknown, d: string) => (v == null || v === '' ? d : String(v));
  const ndvi = typeof f.ndvi === 'number' ? f.ndvi : num(f.ndvi, 0);
  return {
    field_id: str(f.field_id ?? f.id, `field_${Date.now()}_${Math.floor(Math.random() * 1e4)}`),
    name: str(f.name_ar ?? f.name ?? f.field_name, 'حقل'),
    area_ha: num(f.area_ha ?? f.area),
    crop: str(f.crop ?? f.crop_ar, '—'),
    soil: str(f.soil ?? f.soil_type, ''), // soil_type من الخادم؛ لا تلفيق عند الغياب
    ndvi,
    health: str(f.health, ndviHealth(ndvi)),
    stage: str(f.stage ?? f.growth_stage, '—'),
    gdd: num(f.gdd),
    yield_est: num(f.yield_est ?? f.yield_t_ha),
    lat: num(f.lat ?? f.centroid_lat),
    lon: num(f.lon ?? f.centroid_lon),
    geometry: f.geometry,
  };
}

const SOIL_AR: Record<string,string> = {
  loam:'مزيجية', clay_loam:'طينية مزيجية',
  sandy_loam:'رملية مزيجية', silt_loam:'طمية مزيجية',
};

function healthConfig(h: string) {
  const table: Record<string, { label: string; color: string; bg: string }> = {
    excellent:{ label:'ممتاز', color:'#16a34a', bg:'#1e3a1e' },
    good:     { label:'جيد',   color:'#65a30d', bg:'#1a2e0a' },
    fair:     { label:'مقبول', color:'#ca8a04', bg:'#2a1a00' },
    poor:     { label:'منخفض', color:'#dc2626', bg:'#1a0000' },
  };
  return table[h] || { label:h, color:'#6b7280', bg:'#1e293b' };
}

export default function FieldManagementPage() {
  const { user } = useAuthStore();
  const mutateAllowed = canMutate(user?.role);
  const { data, isLoading, isError, refetch } = useFields();
  const [fields,        setFields]        = useState<Field[]>([]);
  const [seeded,        setSeeded]        = useState(false);
  const [search,        setSearch]        = useState('');
  const [filterHealth,  setFilterHealth]  = useState('all');
  const [filterCrop,    setFilterCrop]    = useState('all');
  const [viewMode,      setViewMode]      = useState<'grid'|'table'>('grid');
  const [showAddField,  setShowAddField]  = useState(false);
  // معالج تهيئة الحقل المتسلسل (حقل→موسم→تربة→إنتاجيّة→مساحة العمل) — نمط FieldView.
  const [showWizard,    setShowWizard]    = useState(false);
  const [showSeason,    setShowSeason]    = useState<Field|null>(null);
  const [showDetail,    setShowDetail]    = useState<Field|null>(null);
  const [editField,     setEditField]     = useState<Field|null>(null);
  // الموسم المُنشأ حديثاً (لعرض إجراء «تشغيل المحاكاة») — v39
  const [simSeason,     setSimSeason]     = useState<{ seasonId: string; crops: string[] }|null>(null);
  // صور الأقمار الصناعية CDSE
  const [showSatellite, setShowSatellite] = useState<Field|null>(null);
  const [satelliteIdx,  setSatelliteIdx]  = useState('ndvi');

  // بذر الحالة المحلّيّة من البيانات الحيّة مرّة واحدة (CRUD تفاؤليّ بعدها لا يُداس
  // عند إعادة الجلب). كان يُبذَر من INITIAL مُلفّقة — أُزيلت.
  useEffect(() => {
    const apiFields = (data as { fields?: Record<string, unknown>[] } | undefined)?.fields;
    if (!seeded && Array.isArray(apiFields)) {
      setFields(apiFields.map(mapField));
      setSeeded(true);
    }
  }, [data, seeded]);

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
    // إنشاء حقيقيّ: POST /api/v1/fields يتحقّق من الهندسة ويحسب المساحة/المركز
    // ويُخزّن. نَبني العرض من ردّ الخادم (لا تلفيق قيم). الفشل يُعرَض بصدق.
    try {
      const r = await kongApi.post('/api/v1/fields', {
        name: data.name, crop: data.crop,
        soil_type: data.soil_type ?? data.soil,
        manager: data.manager,
        field_code: data.field_code ?? null,
        water_source: data.water_source ?? null,
        ownership_type: data.ownership_type ?? null,
        country: data.country ?? null,
        region: data.region ?? null,
        geometry: data.geometry,
      });
      setFields(p => [...p, mapField(r.data as Record<string, unknown>)]);
      setShowAddField(false);
      toastStore.add('success', '✅ تم إضافة الحقل', `${data.name}`);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      const msg = (detail && (detail.message_ar || detail)) ||
        'تعذّر حفظ الحقل — تحقّق من القاعدة/الصلاحيّة أو صحّة الحدود.';
      toastStore.add('error', '⚠️ فشل حفظ الحقل', typeof msg === 'string' ? msg : 'خطأ غير متوقّع');
    }
  };

  // ── معالج التهيئة المتسلسل: نسخ تُرجِع سجلّ الحقل المُنشأ كي يلتقط المعالج
  //    field_id ويُكمل السلسلة (موسم/تربة/إنتاجيّة). نفس النقاط الحقيقيّة
  //    (POST /api/v1/fields و/fields/import). الخطأ يُرمى ليعرضه AddFieldWithMap.
  const handleWizardSaveField = async (data: any): Promise<Record<string, unknown>> => {
    const r = await kongApi.post('/api/v1/fields', {
      name: data.name, crop: data.crop,
      soil_type: data.soil_type ?? data.soil,
      manager: data.manager,
      field_code: data.field_code ?? null,
      water_source: data.water_source ?? null,
      ownership_type: data.ownership_type ?? null,
      country: data.country ?? null,
      region: data.region ?? null,
      geometry: data.geometry,
    });
    const rec = r.data as Record<string, unknown>;
    setFields(p => [...p, mapField(rec)]);
    toastStore.add('success', '✅ تم إضافة الحقل', `${data.name}`);
    return rec;
  };

  const handleWizardImportField = async (payload: any): Promise<Record<string, unknown>> => {
    const r = await kongApi.post('/api/v1/fields/import', payload);
    const rec = r.data as Record<string, unknown>;
    setFields(p => [...p, mapField(rec)]);
    toastStore.add('success', '✅ تم استيراد الحقل', `${payload.name}`);
    return rec;
  };

  // اكتمال المعالج → الانتقال إلى مساحة عمل الحقل (لوحة التفاصيل) للحقل المُنشأ.
  const handleWizardComplete = (fieldId: string) => {
    setShowWizard(false);
    const created = fields.find(f => f.field_id === fieldId);
    if (created) setShowDetail(created);
  };

  const handleImportField = async (payload: any) => {
    // استيراد حقيقيّ: POST /api/v1/fields/import يحلّل الملفّ → Polygon ثمّ نفس
    // مسار التحقّق/الحفظ. الفشل (400 تحليل / 422 هندسة / 503 DB) يُرمى رسالةً
    // عربيّةً صادقةً فيعرضها النموذج (لا ابتلاع، لا تلفيق).
    try {
      const r = await kongApi.post('/api/v1/fields/import', payload);
      setFields(p => [...p, mapField(r.data as Record<string, unknown>)]);
      setShowAddField(false);
      toastStore.add('success', '✅ تم استيراد الحقل', `${payload.name}`);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      const msg = (detail && (detail.message_ar || detail)) ||
        'تعذّر استيراد الحقل — تحقّق من صحّة الملفّ والحدود والصلاحيّة.';
      throw new Error(typeof msg === 'string' ? msg : 'خطأ غير متوقّع');
    }
  };

  const handleSaveSeason = async (data: any) => {
    // إنشاء حقيقيّ: POST /api/v1/fields/{id}/seasons (بدل /seasons المُبتلَع).
    // عند الفشل نرمي رسالة عربيّة فيعرضها النموذج (errors.general) ويبقى مفتوحاً.
    let seasonId: string | null = null;
    try {
      const r = await kongApi.post(`/api/v1/fields/${data.field_id}/seasons`, {
        crops: data.crops, cultivar: data.cultivar || null,
        irrigation_type: data.irrigation_type,
        seed_rate_kg_ha: data.seed_rate_kg_ha,
        land_leveling_date: data.land_leveling_date || null,
        plowing_date: data.plowing_date || null,
        sowing_date: data.sowing_date || null,
        season_end: data.season_end || null,
        custom_stages: data.custom_stages,
      });
      seasonId = (r?.data as { season_id?: string } | undefined)?.season_id ?? null;
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      throw new Error((detail && (detail.message_ar || detail)) ||
        'تعذّر حفظ الموسم — تحقّق من القاعدة/الصلاحيّة والتواريخ.');
    }
    setShowSeason(null);
    toastStore.add('success', '🌾 تم إنشاء الموسم', (data.crops || []).join('، '));
    // بعد الإنشاء: اعرض إجراء «تشغيل المحاكاة» على الموسم الجديد (إن عاد المعرّف).
    if (seasonId) setSimSeason({ seasonId, crops: data.crops || [] });
  };

  const handleDelete = async (id: string) => {
    if (!confirm('هل أنت متأكد من حذف هذا الحقل؟')) return;
    // حذف حقيقيّ: DELETE /api/v1/fields/{id} (كان محليّاً فقط ⇒ يعود عند التحديث).
    try {
      await kongApi.delete(`/api/v1/fields/${id}`);
    } catch (e) {
      toastStore.add('error', 'تعذّر حذف الحقل', asApiError(e).message || 'تحقّق من الصلاحيّة/القاعدة.');
      return;
    }
    setFields(p => p.filter(f => f.field_id !== id));
    refetch();
    toastStore.add('success', '🗑️ تم حذف الحقل', '');
  };

  const handleEditSave = async (data: any) => {
    if (!editField) return;
    // تعديل حقيقيّ: PATCH /api/v1/fields/{id} (الاسم/المحصول). area_ha مُشتقّة من
    // الهندسة (لا تُحفَظ يدويّاً)؛ refetch يُعيد القيمة الحقيقيّة من الخادم.
    try {
      await kongApi.patch(`/api/v1/fields/${editField.field_id}`, {
        name: data.name,
        crop: data.crop,
      });
    } catch (e) {
      throw new Error(asApiError(e).message ||
        'تعذّر حفظ التعديل — تحقّق من القاعدة/الصلاحيّة.');
    }
    setEditField(null);
    await refetch();
    toastStore.add('success', '✅ تم تعديل الحقل', data.name);
  };

  // ── المؤشّرات المدعومة في CDSE (Sentinel Hub) ──────────────────
  const CDSE_INDICES: { key: string; label: string }[] = [
    { key: 'ndvi',     label: 'NDVI — النباتات'     },
    { key: 'evi',      label: 'EVI — نبات معزّز'    },
    { key: 'ndwi',     label: 'NDWI — الماء'        },
    { key: 'ndmi',     label: 'NDMI — الرطوبة'      },
    { key: 'ndre',     label: 'NDRE — حافّة حمراء'  },
    { key: 'msavi',    label: 'MSAVI — تربة'        },
    { key: 'gndvi',    label: 'GNDVI — كلوروفيل'   },
    { key: 'ndsi',     label: 'NDSI — الملوحة'      },
  ];

  // يحوّل geometry GeoJSON (coordinates [lon,lat]) إلى [lat,lon][] لـLeaflet
  function geomToLatLng(geom: any): [number, number][] | undefined {
    try {
      let coords: [number, number][] | undefined;
      if (geom?.type === 'Feature') geom = geom.geometry;
      if (geom?.type === 'Polygon') coords = geom.coordinates[0];
      else if (geom?.type === 'MultiPolygon') coords = geom.coordinates[0][0];
      if (!coords || coords.length < 3) return undefined;
      return coords.map(([lng, lat]: [number, number]) => [lat, lng]);
    } catch { return undefined; }
  }

  // يحسب bbox [west, south, east, north] من geometry GeoJSON
  function geomToBbox(geom: any): [number, number, number, number] | undefined {
    try {
      let coords: [number, number][] | undefined;
      if (geom?.type === 'Feature') geom = geom.geometry;
      if (geom?.type === 'Polygon') coords = geom.coordinates[0];
      else if (geom?.type === 'MultiPolygon') coords = geom.coordinates[0][0];
      if (!coords || coords.length < 2) return undefined;
      const lons = coords.map(([lng]: [number, number]) => lng);
      const lats = coords.map(([, lat]: [number, number]) => lat);
      return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
    } catch { return undefined; }
  }

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
        {/* تفاصيل الحقل — متاح للجميع (قراءة؛ التحرير داخل اللوحة محكوم بالدور) */}
        <div className="px-4 pb-2 space-y-1.5">
          <button onClick={() => setShowDetail(f)}
            className="w-full flex items-center justify-center gap-1 py-1.5 rounded-lg text-xs text-sky-400 hover:text-sky-300 border"
            style={{ borderColor:'#0ea5e944', background:'#0c2a3a22' }}>
            <ClipboardList className="w-3 h-3" /> تفاصيل
          </button>
          <button onClick={() => { setSatelliteIdx('ndvi'); setShowSatellite(f); }}
            className="w-full flex items-center justify-center gap-1 py-1.5 rounded-lg text-xs text-violet-400 hover:text-violet-300 border"
            style={{ borderColor:'#7c3aed44', background:'#1e1b4b22' }}>
            <Satellite className="w-3 h-3" /> صور الأقمار (CDSE)
          </button>
        </div>
        {/* Actions — محكومة بالدور (المُشاهِد قراءة فقط) */}
        {mutateAllowed && (
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
        )}
      </div>
    );
  };

  if (isLoading && !seeded) return <LoadingState message="جارٍ تحميل الحقول…" />;
  if (isError && !seeded) return <ErrorState title="تعذّر تحميل الحقول" onRetry={() => refetch()} />;

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
          {mutateAllowed && (
            <>
              {/* المسار الأساسيّ: معالج التهيئة المتسلسل (حقل→موسم→تربة→إنتاجيّة→مساحة عمل) */}
              <button onClick={()=>setShowWizard(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white"
                style={{ background:'#16a34a' }}>
                <Plus className="w-4 h-4" /> تهيئة حقل جديد
              </button>
              {/* المسار البسيط (إضافة حقل فقط بلا سلسلة) — يبقى متاحاً كما كان */}
              <button onClick={()=>setShowAddField(true)}
                className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-300 border"
                style={{ borderColor:'#334155' }}>
                <Map className="w-4 h-4" /> رسم حقل فقط
              </button>
            </>
          )}
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
            <div className="col-span-full">
              <EmptyState icon={<Map className="w-10 h-10 text-slate-700" />}
                title={fields.length === 0 ? 'لا توجد حقول' : 'لا توجد حقول تطابق البحث'}
                hint={fields.length === 0 ? 'أضِف حقلاً للبدء' : undefined} />
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
                        <div className="flex gap-1.5 items-center">
                          <button onClick={()=>setShowDetail(f)} title="تفاصيل الحقل"
                            className="p-1.5 rounded hover:bg-sky-950 text-slate-400 hover:text-sky-400 transition-colors">
                            <ClipboardList className="w-3.5 h-3.5" />
                          </button>
                        {mutateAllowed ? (
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
                        ) : null}
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
      {showWizard && (
        <FieldSetupWizard
          onSaveField={handleWizardSaveField}
          onImportField={handleWizardImportField}
          onComplete={handleWizardComplete}
          onCancel={() => setShowWizard(false)}
        />
      )}
      {showAddField && (
        <AddFieldWithMap
          onSave={handleSaveField}
          onImport={handleImportField}
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
      {showDetail && (
        <FieldDetailPanel
          fieldId={showDetail.field_id}
          fieldName={showDetail.name}
          onClose={() => setShowDetail(null)}
        />
      )}
      {simSeason && (
        <SeasonSimModal
          seasonId={simSeason.seasonId}
          crops={simSeason.crops}
          onClose={() => setSimSeason(null)}
        />
      )}

      {/* ── مودال صور الأقمار CDSE ─────────────────────────────── */}
      {showSatellite && (
        <div className="fixed inset-0 z-50 flex items-start justify-center p-4 overflow-y-auto"
          style={{ background: 'rgba(0,0,0,0.72)' }}>
          <div className="w-full max-w-3xl rounded-2xl border mt-8 mb-8"
            style={{ background: '#0f172a', borderColor: '#334155' }}>
            {/* رأس المودال */}
            <div className="flex items-center justify-between px-5 py-4 border-b"
              style={{ borderColor: '#334155' }}>
              <div className="flex items-center gap-2">
                <Satellite className="w-4 h-4 text-violet-400" />
                <span className="font-semibold text-slate-100 text-sm">
                  صور الأقمار — {showSatellite.name}
                </span>
                <span className="text-[10px] text-slate-500 mr-2">
                  {showSatellite.area_ha} هـ · Sentinel-2 L2A · CDSE
                </span>
              </div>
              <button onClick={() => setShowSatellite(null)}
                className="text-slate-400 hover:text-slate-200 p-1">
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* شريط اختيار المؤشّر */}
            <div className="flex items-center gap-3 px-5 py-3 border-b"
              style={{ borderColor: '#1e293b' }}>
              <span className="text-xs text-slate-400 whitespace-nowrap">المؤشّر:</span>
              <div className="flex flex-wrap gap-1.5">
                {CDSE_INDICES.map(({ key, label }) => (
                  <button key={key} onClick={() => setSatelliteIdx(key)}
                    className="px-2.5 py-1 rounded-lg text-xs transition-colors"
                    style={{
                      background: satelliteIdx === key ? '#4c1d95' : '#1e293b',
                      color: satelliteIdx === key ? '#c4b5fd' : '#94a3b8',
                      border: `1px solid ${satelliteIdx === key ? '#7c3aed' : '#334155'}`,
                    }}>
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* الخريطة */}
            <div className="p-4">
              <FieldIndicatorMap
                fieldId={showSatellite.field_id}
                index={satelliteIdx}
                date=""
                tileSegment="cdse-tiles"
                fieldPolygon={geomToLatLng(showSatellite.geometry)}
                fieldBbox={geomToBbox(showSatellite.geometry)}
                fieldGeometry={showSatellite.geometry}
                fallbackBounds={
                  showSatellite.lon && showSatellite.lat
                    ? [showSatellite.lon - 0.01, showSatellite.lat - 0.01,
                       showSatellite.lon + 0.01, showSatellite.lat + 0.01]
                    : undefined
                }
                basemap="satellite"
                initialOpacity={0.85}
                height={420}
              />
              <p className="text-[11px] text-slate-500 mt-2 text-center">
                الصور تُجلَب مباشرةً من Sentinel Hub (CDSE) · أحدث مشهد أقلّ غيوماً
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── محاكاة الموسم (Crop-model simulation) — v39 ────────────────────
// إجراء صريح «تشغيل المحاكاة» بعد إنشاء الموسم. يعرض النتائج بصدق: نطاق الإنتاج
// (لا رقم قاطع) + GDD + LAI + احتياج الماء + الثقة + الافتراضات/التحذيرات كما
// عادت من الخادم. لا تلفيق: الخطأ (503 طقس/قاعدة، 404، 422) يُعرَض كما هو.
function SeasonSimModal({ seasonId, crops, onClose }: {
  seasonId: string; crops: string[]; onClose: () => void;
}) {
  const sim = useSimulateSeason();
  const r: SeasonSimResult | undefined = sim.data;
  const num = (v: number | null | undefined, d = 0) =>
    (typeof v === 'number' ? Math.round(v).toLocaleString('ar') : String(d));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.6)' }}>
      <div className="w-full max-w-lg rounded-xl border max-h-[88vh] overflow-y-auto"
        style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="flex items-center justify-between p-4 border-b" style={{ borderColor: '#334155' }}>
          <div className="font-semibold text-slate-100 text-sm flex items-center gap-2">
            <Sprout size={16} className="text-emerald-400" />
            محاكاة الموسم {crops.length ? `· ${crops.join('، ')}` : ''}
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200"><X size={18} /></button>
        </div>

        <div className="p-4 space-y-3">
          {!r && !sim.isError && (
            <p className="text-xs text-slate-400 leading-relaxed">
              تشغيل نموذج محصولي (RUE/FAO-56) يقدّر الإنتاج وتراكم الحرارة (GDD) ومؤشّر
              المساحة الورقيّة (LAI) واحتياج الماء من طقس الموسم. النتائج <b>تقديرات نموذجيّة</b>
              ضمن نطاق، لا قياسات ميدانيّة.
            </p>
          )}

          {sim.isError && (
            <div className="rounded-lg p-3 text-xs" style={{ background: '#3f1d1d', color: '#fca5a5' }}>
              تعذّرت المحاكاة: {asApiError(sim.error).response?.data?.detail as string | undefined ||
                (sim.error as Error)?.message || 'خطأ غير معروف (طقس/قاعدة غير متاحة).'}
            </div>
          )}

          {r && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <Stat label="الإنتاج المُقدَّر (kg/ha)"
                  value={`${num(r.yield_low_kg_ha)} – ${num(r.yield_high_kg_ha)}`} hint={`المركزي ≈ ${num(r.yield_kg_ha)}`} />
                <Stat label="GDD التراكمي (°C·day)"
                  value={`${num(r.gdd_total)} / ${num(r.gdd_to_maturity)}`} hint={r.maturity_reached ? 'بلغ النضج' : 'لم يبلغ النضج'} />
                <Stat label="أقصى LAI (m²/m²)" value={r.lai_max.toFixed(2)} hint="مؤشّر تقريبي" />
                <Stat label="احتياج الماء (mm)" value={num(r.water_need_mm)}
                  hint={r.water_supply_mm != null ? `العرض ≈ ${num(r.water_supply_mm)}` : 'العرض غير معروف'} />
              </div>

              <div className="rounded-lg p-2 text-[11px]" style={{ background: '#0f172a', color: '#94a3b8' }}>
                الكتلة الحيويّة ≈ {num(r.biomass_kg_ha)} kg/ha · الثقة {Math.round(r.confidence * 100)}٪
                {!r.crop_recognized && ' · المحصول غير مُعرّف (نموذج عامّ)'}
              </div>

              <p className="text-[11px] text-slate-400 leading-relaxed">{r.rationale_ar}</p>

              {r.assumptions_ar.length > 0 && (
                <ul className="text-[11px] text-slate-500 list-disc pr-4 space-y-0.5">
                  {r.assumptions_ar.map((a, i) => <li key={i}>{a}</li>)}
                </ul>
              )}
              {r.warnings_ar.length > 0 && (
                <ul className="text-[11px] list-disc pr-4 space-y-0.5" style={{ color: '#fbbf24' }}>
                  {r.warnings_ar.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 p-4 border-t" style={{ borderColor: '#334155' }}>
          <button onClick={onClose}
            className="px-3 py-1.5 rounded-lg text-xs text-slate-300 hover:bg-slate-700">
            إغلاق
          </button>
          <button onClick={() => sim.mutate(seasonId)} disabled={sim.isPending}
            className="px-3 py-1.5 rounded-lg text-xs font-medium text-white disabled:opacity-50"
            style={{ background: '#059669' }}>
            {sim.isPending ? 'جارٍ التشغيل…' : r ? 'إعادة التشغيل' : 'تشغيل المحاكاة'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg p-2" style={{ background: '#0f172a' }}>
      <div className="text-[10px] text-slate-400">{label}</div>
      <div className="text-sm font-semibold text-slate-100 mt-0.5">{value}</div>
      {hint && <div className="text-[10px] text-slate-500 mt-0.5">{hint}</div>}
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
