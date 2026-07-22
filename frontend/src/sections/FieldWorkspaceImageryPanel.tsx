import { useQuery } from '@tanstack/react-query';
import { CalendarDays, Image as ImageIcon, Satellite } from 'lucide-react';
import { getFieldImageryAvailableDates, getFieldImageryTimeline, type FieldImageryDateOption, type FieldImageryTimelineItem } from '../services/api/fieldImagery';
import { EmptyState, ErrorState, LoadingState } from '../components/StateViews';
import { DegradedState } from '../components/product/DegradedState';
import SceneProvenanceCard from '../components/maphub/SceneProvenanceCard';

function apiStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } } | null | undefined)?.response?.status;
}

function ImageryState({ title, error, onRetry }: { title: string; error: unknown; onRetry: () => void }) {
  const status = apiStatus(error);
  if (status === 502 || status === 503 || status === 504) {
    return <DegradedState title={`${title} تعمل في وضع متدهور`} detail="raster/backend facade غير متاح حالياً. لا تعرض مساحة العمل تواريخ أو صور بديلة." onRetry={onRetry} />;
  }
  if (status === 404) return <EmptyState title={`${title} غير مربوطة بعد`} hint="endpoint الصور غير متاح في هذه البيئة." />;
  if (status === 401 || status === 403) return <ErrorState title="لا تملك صلاحية عرض صور الحقل" />;
  return <ErrorState title={`تعذّر تحميل ${title}`} detail="لم يتم استخدام fallback وهمي أو صور demo." onRetry={onRetry} />;
}

function formatAcquisition(item: Pick<FieldImageryDateOption, 'date' | 'acquisition_datetime'>) {
  return item.acquisition_datetime ? item.acquisition_datetime.replace('T', ' ').replace('Z', ' UTC') : item.date;
}

function DateRow({ item }: { item: FieldImageryDateOption }) {
  return (
    <li className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-slate-100">{formatAcquisition(item)}</p>
        <span className={`rounded-full border px-2 py-0.5 text-[11px] ${item.has_cog ? 'border-emerald-500/40 text-emerald-200' : 'border-amber-500/40 text-amber-200'}`}>
          {item.has_cog ? 'COG جاهز' : 'قابل للجلب'}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
        {typeof item.cloud_pct === 'number' && <span>cloud: {item.cloud_pct}%</span>}
        {item.scene_id && <span>scene: {item.scene_id}</span>}
        {item.indices?.length ? <span>indices: {item.indices.join(', ')}</span> : null}
      </div>
      <SceneProvenanceCard scene={item} compact />
    </li>
  );
}

function TimelineRow({ item }: { item: FieldImageryTimelineItem }) {
  return (
    <li className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-slate-100">{item.acquisition_datetime ? item.acquisition_datetime.replace('T', ' ').replace('Z', ' UTC') : item.date}</p>
        {item.quality_label && <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-400">{item.quality_label}</span>}
      </div>
      <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
        {typeof item.cloud_pct === 'number' && <span>cloud: {item.cloud_pct}%</span>}
        {typeof item.clear_pct === 'number' && <span>clear: {item.clear_pct}%</span>}
        {item.indices?.length ? <span>indices: {item.indices.join(', ')}</span> : null}
      </div>
      <SceneProvenanceCard scene={item} compact />
    </li>
  );
}

export default function FieldWorkspaceImageryPanel({ fieldId }: { fieldId: string }) {
  const datesQ = useQuery({
    queryKey: ['field-workspace', fieldId, 'imagery-available-dates', 'truecolor'],
    queryFn: () => getFieldImageryAvailableDates(fieldId, 'truecolor', 20),
    enabled: Boolean(fieldId),
    staleTime: 120_000,
  });
  const timelineQ = useQuery({
    queryKey: ['field-workspace', fieldId, 'imagery-timeline'],
    queryFn: () => getFieldImageryTimeline(fieldId, 24),
    enabled: Boolean(fieldId),
    staleTime: 120_000,
  });

  return (
    <section className="space-y-4" dir="rtl" aria-label="صور الحقل">
      <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
        <div className="mb-4 flex items-center gap-2">
          <Satellite className="h-5 w-5 text-emerald-300" aria-hidden="true" />
          <h2 className="text-base font-bold text-slate-100">الصور والمؤشرات</h2>
        </div>
        <p className="text-sm leading-relaxed text-slate-400">تعرض هذه اللوحة تواريخ الالتقاط الفعلية وملفات COG الجاهزة من backend فقط. لا يتم توليد صور أو تواريخ من الواجهة.</p>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
          <div className="mb-4 flex items-center gap-2">
            <CalendarDays className="h-5 w-5 text-emerald-300" aria-hidden="true" />
            <h3 className="text-sm font-bold text-slate-100">تواريخ TrueColor المتاحة</h3>
          </div>
          {datesQ.isLoading && <LoadingState message="جارٍ تحميل تواريخ الصور…" />}
          {datesQ.isError && <ImageryState title="تواريخ الصور" error={datesQ.error} onRetry={() => datesQ.refetch()} />}
          {datesQ.data && (datesQ.data.length ? <ol className="space-y-2">{datesQ.data.slice(0, 8).map(item => <DateRow key={`${item.date}-${item.scene_id ?? 'scene'}`} item={item} />)}</ol> : <EmptyState title="لا توجد تواريخ صور محفوظة" hint="لا يتم عرض تاريخ افتراضي قبل توفره من raster/platform." />)}
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
          <div className="mb-4 flex items-center gap-2">
            <ImageIcon className="h-5 w-5 text-emerald-300" aria-hidden="true" />
            <h3 className="text-sm font-bold text-slate-100">Timeline الصور</h3>
          </div>
          {timelineQ.isLoading && <LoadingState message="جارٍ تحميل Timeline الصور…" />}
          {timelineQ.isError && <ImageryState title="Timeline الصور" error={timelineQ.error} onRetry={() => timelineQ.refetch()} />}
          {timelineQ.data && (
            <div className="space-y-3">
              {timelineQ.data.degraded && <DegradedState title="Timeline الصور متدهور" detail={timelineQ.data.warning_ar ?? 'الخادم أعاد حالة متدهورة.'} />}
              {timelineQ.data.items?.length ? <ol className="space-y-2">{timelineQ.data.items.slice(0, 8).map(item => <TimelineRow key={`${item.date}-${item.scene_id ?? 'scene'}`} item={item} />)}</ol> : <EmptyState title="لا توجد صور في Timeline" hint="لا يتم عرض مصغرات demo داخل مساحة العمل." />}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
