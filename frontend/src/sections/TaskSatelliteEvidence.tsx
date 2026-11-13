import { useEffect, useState } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { kongApi, rasterApi } from '../services/api/client';
import { getFieldTasks, type FieldTaskSummary, type SatelliteSource, type TerrainSource } from '../services/api/fieldTasks';
import { useAuthStore } from '../hooks/useAuth';
import { normalizeRole } from '../lib/permissions';
import { taskTypeLabel } from '../lib/taskTypeLabels';

function Preview({ field, source }: { field: string; source: SatelliteSource }) {
  const { tenantId } = useAuthStore();
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState('');
  const preview = useQuery({
    queryKey: ['task-preview', tenantId, field, source.asset_id],
    enabled: open,
    queryFn: async () => {
      const res = await rasterApi.get<Blob>(`/v1/fields/${encodeURIComponent(field)}/cdse-thumbnail.png`, {
        params: { source: 'persisted', asset_id: source.asset_id, index: source.index_name, date: source.acquisition_date, size: 320 },
        responseType: 'blob',
      });
      if (res.headers['x-raster-asset-id'] !== source.asset_id || res.data.type !== 'image/png')
        throw new Error('تعذّر مطابقة المعاينة بالأصل');
      return {blob: res.data, style: res.headers['x-preview-style']};
    },
  });
  useEffect(() => {
    if (!open || !preview.data) { setUrl(''); return; }
    const objectUrl = URL.createObjectURL(preview.data.blob);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [open, preview.data]);
  return <div className="my-2 text-sm">
    <div><b>{source.index_name.toUpperCase()}</b> · {source.acquisition_date} · <bdi>{source.scene_id}</bdi></div>
    {source.index_name.toLowerCase() === 'et_inputs' ? <p>حزمة مدخلات التبخر والنتح</p> :
    <button type="button" className="underline" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? 'إخفاء المعاينة' : 'عرض صورة المؤشر'}</button>}
    {open && preview.data?.style === 'relative' && <p>التدرج الرمادي نسبي داخل هذه المعاينة، من أدنى قيمة إلى أعلاها.</p>}
    {open && (preview.isError ? <p role="status">تعذر عرض صورة هذا الأصل.</p> : url ? <img src={url} alt={`مؤشر ${source.index_name} للمشهد ${source.scene_id}`} /> : <p>جارٍ تحميل الصورة…</p>)}
  </div>;
}

const terrainLabels: Record<string,string> = {
  slope_deg: 'الميل (درجة)', tpi: 'الموضع الطبوغرافي (م)', twi: 'مؤشر الرطوبة الطبوغرافي التقريبي',
  plan_curvature: 'لابلاسيان الارتفاع المحلي', profile_curvature: 'المشتقة الثانية على محور الصفوف',
  elevation_laplacian_per_m: 'لابلاسيان الارتفاع (١/م)', row_second_derivative_per_m: 'المشتقة الثانية على محور الصفوف (١/م)',
  higher_neighbor_count: 'عدد الخلايا المجاورة الأعلى ارتفاعاً', local_wetness_proxy: 'مؤشر بلل محلي تقريبي',
  flow_accumulation: 'عدد الجيران الأعلى ارتفاعاً مضافاً إليه واحد', relative_elevation: 'الارتفاع النسبي',
};

function TerrainDetails({source}: {source: TerrainSource}) {
  const metrics = Object.entries(source.summaries).filter(([key]) => key !== 'wadi_distance_m');
  return <details className="my-2 text-sm"><summary>{source.kind === 'field_record'
    ? 'تضاريس مسجلة في الحقل' : `مشتقات نموذج الارتفاع · ${source.dem_version ?? ''}`}</summary>
    {source.elevation_m != null && <p>الارتفاع: {source.elevation_m} م</p>}
    {source.slope_pct != null && <p>الميل: {source.slope_pct}%</p>}
    {source.aspect && <p>اتجاه المنحدر: {source.aspect}</p>}
    {source.cell_size_m != null && <p>حجم خلية النموذج: {source.cell_size_m} م</p>}
    {source.generated_at && <p>تاريخ اشتقاق المنتج: <bdi>{source.generated_at}</bdi></p>}
    {source.product_id && <p>مرجع المنتج: <bdi>{source.product_id}</bdi> · {source.algorithm_version}</p>}
    {source.geometry_hash && <p>بصمة حدود الحقل: <bdi>{source.geometry_hash}</bdi></p>}
    {source.kind === 'dem_product' && (source.algorithm_version === 'terrain-v2' || 'wadi_distance_m' in source.summaries) && <p>المسافة إلى الوادي وتراكم الجريان غير محسوبين.</p>}
    {metrics.length > 0 && <table><thead><tr>
      <th>المشتق</th><th>أدنى</th><th>متوسط</th><th>أعلى</th></tr></thead><tbody>
      {metrics.map(([key,v]) => <tr key={key}><td>{terrainLabels[key] ?? key}</td>
        <td>{v.min ?? '—'}</td><td>{v.mean ?? '—'}</td><td>{v.max ?? '—'}</td></tr>)}
    </tbody></table>}
  </details>;
}

export function TaskSatelliteEvidence({ field, sources, terrain }: { field: string; sources?: SatelliteSource[]; terrain?: TerrainSource[] }) {
  return <>{sources?.map(source => <Preview key={source.asset_id} field={field} source={source} />)}
    {terrain?.map(source => <TerrainDetails key={source.source_key} source={source} />)}</>;
}

export function SatelliteTaskPicker({ field }: { field: string }) {
  const { tenantId, user } = useAuthStore();
  const role = normalizeRole(user?.role);
  if (role !== 'owner' && role !== 'manager') return null;
  return <Picker key={JSON.stringify([tenantId,field])} tenant={tenantId} field={field} />;
}

function Picker({ field, tenant }: { field: string; tenant: string | null }) {
  const qc = useQueryClient();
  const [kind, setKind] = useState<'imagery'|'terrain'>('imagery');
  const [index, setIndex] = useState('');
  const [asset, setAsset] = useState('');
  const [task, setTask] = useState('');
  const [before, setBefore] = useState<string[]>([]);
  const path = `/api/v1/fields/${encodeURIComponent(field)}/task-imagery`;
  const terrainPath = path.replace('/task-imagery', '/task-terrain');
  const terrain = useQuery({queryKey: ['task-terrain',tenant,field], enabled: kind === 'terrain',
    queryFn: () => kongApi.get<TerrainSource[]>(terrainPath).then(r => r.data)});
  const products = useQuery({
    enabled: kind === 'imagery',
    queryKey: ['task-products', tenant, field, before, index],
    queryFn: () => kongApi.get<SatelliteSource[]>(path, {params: {index: index.trim() || undefined, before_id: before[before.length - 1]}}).then(r => r.data),
  });
  const tasks = useQuery({queryKey: ['task-link-targets', tenant, field], queryFn: () => getFieldTasks(field)});
  const link = useMutation({
    mutationFn: () => kongApi.post<FieldTaskSummary>(kind === 'terrain' ? terrainPath : path, {
      ...(kind === 'terrain' ? {source_key: asset} : {asset_id: asset}), task_id: task || null}).then(r => r.data),
    onSuccess: () => {
      void qc.invalidateQueries({queryKey: ['field-workspace', field, 'tasks']});
      void qc.invalidateQueries({queryKey: ['tasks', tenant]});
      void qc.invalidateQueries({queryKey: ['task-link-targets', tenant, field]});
    },
  });
  const lastAsset = products.data?.length === 100 ? products.data[99].asset_id : null;
  function page(cursors: string[]) { setBefore(cursors); setAsset(''); link.reset(); }
  return <section className="space-y-3 rounded-xl border border-slate-700 p-4">
    <h3>تكليف ميداني من مشهد أو تضاريس</h3>
    <fieldset disabled={link.isPending} className="flex flex-wrap items-center gap-2">
      <label>مصدر التكليف <select value={kind} onChange={e => {setKind(e.target.value as typeof kind); page([]);}}>
        <option value="imagery">مشهد أو مؤشر</option><option value="terrain">تضاريس الحقل</option></select></label>
      {kind === 'imagery' ? <>
      <label>تصفية برمز المؤشر <input value={index} placeholder="مثل NDRE" onChange={e => {setIndex(e.target.value); page([]);}} /></label>
      <label>صورة المؤشر <select value={asset} onChange={e => {setAsset(e.target.value); link.reset();}}>
        <option value="">اختر الأصل المعالج</option>
        {products.data?.map(s => <option key={s.asset_id} value={s.asset_id}>{s.acquisition_date} · {s.index_name} · {s.scene_id} · #{s.asset_id}</option>)}
      </select></label>
      {before.length > 0 && <button onClick={() => page(before.slice(0,-1))}>أحدث</button>}
      {lastAsset && <button onClick={() => page([...before,lastAsset])}>أقدم</button>}
      </> : <label>مصدر التضاريس <select value={asset} onChange={e => {setAsset(e.target.value); link.reset();}}>
        <option value="">اختر المصدر</option>
        {terrain.data?.map(s => <option value={s.source_key} key={s.source_key}>{s.kind === 'field_record'
          ? 'الارتفاع والميل والاتجاه المسجلة في الحقل' : `أحدث مشتقات DEM · ${s.dem_version} · ${s.generated_at}`}</option>)}
      </select></label>}
      <label>المهمة <select value={task} onChange={e => {setTask(e.target.value); link.reset();}}>
        <option value="">مهمة استكشاف لهذا الأصل</option>
        {tasks.data?.tasks.filter(t => t.task_id).map(t => <option key={t.task_id} value={t.task_id}>{taskTypeLabel(t.task_type)} · {t.status} · {t.task_id}</option>)}
      </select></label>
      <button disabled={!asset || (kind === 'terrain' ? terrain.isError : products.isError)} onClick={() => link.mutate()}>ربط بالمهمة</button>
    </fieldset>
    {kind === 'terrain' && terrain.data?.length === 0 && <p>لا توجد تضاريس مسجلة أو مشتقات DEM محفوظة لهذا الحقل.</p>}
    {kind === 'terrain' && terrain.isError && <p>تعذر تحميل تضاريس الحقل.</p>}
    {kind === 'imagery' && products.data?.length === 0 && <p>لا توجد أصول جاهزة في هذه الصفحة.</p>}
    {kind === 'imagery' && products.isError && <p>تعذّر تحميل أصول الحقل.</p>}
    {tasks.isError && <p>تعذّر تحميل المهام السابقة.</p>}
    {link.isError && <p role="alert">تعذّر الربط. حدّث المصادر ثم أعد الاختيار. <button onClick={() => {page([]); void terrain.refetch(); void products.refetch();}}>تحديث المصادر</button></p>}
    {link.isSuccess && <p role="status">حُفظ المصدر في المهمة <bdi>{link.data.task_id}</bdi></p>}
  </section>;
}
