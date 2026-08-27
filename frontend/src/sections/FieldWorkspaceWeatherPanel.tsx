import { useQuery } from '@tanstack/react-query';
import { CloudSun, ShieldAlert, Wind } from 'lucide-react';
import { getFieldDiseaseRisk, getFieldWeatherOperationWindows } from '../services/api/fieldWeather';
import { EmptyState, ErrorState, LoadingState } from '../components/StateViews';
import { DegradedState } from '../components/product/DegradedState';

function apiStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } } | null | undefined)?.response?.status;
}

function WeatherState({ title, error, onRetry }: { title: string; error: unknown; onRetry: () => void }) {
  const status = apiStatus(error);
  if (status === 502 || status === 503 || status === 504) return <DegradedState title={`${title} تعمل في وضع متدهور`} detail="خدمة الطقس غير متاحة. لا تعرض الواجهة توقعات بديلة." onRetry={onRetry} />;
  if (status === 404) return <EmptyState title={`${title} غير مربوطة بعد`} hint="weather facade غير متاح في هذه البيئة." />;
  if (status === 401 || status === 403) return <ErrorState title="لا تملك صلاحية عرض طقس الحقل" />;
  return <ErrorState title={`تعذّر تحميل ${title}`} detail="لا يوجد fallback من المتصفح." onRetry={onRetry} />;
}

export default function FieldWorkspaceWeatherPanel({ fieldId, seasonId }: { fieldId: string; seasonId?: string | null }) {
  const windowsQ = useQuery({
    queryKey: ['field-workspace', fieldId, seasonId, 'weather-operation-windows'],
    queryFn: () => getFieldWeatherOperationWindows(fieldId, { season_id: seasonId, horizon_hours: 72 }),
    enabled: Boolean(fieldId),
    staleTime: 60_000,
  });
  const diseaseQ = useQuery({
    queryKey: ['field-workspace', fieldId, 'weather-disease-risk'],
    queryFn: () => getFieldDiseaseRisk(fieldId),
    enabled: Boolean(fieldId),
    staleTime: 60_000,
  });

  return (
    <section className="space-y-4" dir="rtl" aria-label="طقس الحقل">
      <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
        <div className="mb-2 flex items-center gap-2">
          <CloudSun className="h-5 w-5 text-emerald-300" aria-hidden="true" />
          <h2 className="text-base font-bold text-slate-100">الطقس الزراعي</h2>
        </div>
        <p className="text-sm text-slate-400">يعرض نوافذ التشغيل ومخاطر الأمراض من عقود weather facade فقط. {seasonId ? <>season: <code>{seasonId}</code></> : 'لا يوجد season_id؛ تبقى النتائج غير موسمية عند الخادم.'}</p>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
          <div className="mb-4 flex items-center gap-2"><Wind className="h-5 w-5 text-emerald-300" /><h3 className="text-sm font-bold text-slate-100">نوافذ التشغيل</h3></div>
          {windowsQ.isLoading && <LoadingState message="جارٍ تحميل نوافذ التشغيل…" />}
          {windowsQ.isError && <WeatherState title="نوافذ التشغيل" error={windowsQ.error} onRetry={() => windowsQ.refetch()} />}
          {windowsQ.data && <div className="space-y-3">
            {windowsQ.data.degraded && <DegradedState title="نوافذ التشغيل متدهورة" detail={windowsQ.data.warning_ar ?? 'الخادم أعاد حالة متدهورة.'} />}
            {windowsQ.data.windows?.length ? <ol className="space-y-2">{windowsQ.data.windows.map((w, index) => (
              <li key={`${w.operation}-${w.start_at ?? index}`} className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-semibold text-slate-100">{w.operation}</p>{w.suitability && <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-400">{w.suitability}</span>}</div>
                {/* `start_at` صار طابعاً زمنيّاً أو `null` — وكان يحمل رمزاً (`"+72h"`)
                    فيُصيَّر «+72h → —». فحين يغيب الطابعُ تُعرَض الإزاحةُ **بوصفها إزاحة**،
                    ولا يُرسَم سهمُ مدىً لا نهايةَ له. */}
                <p className="mt-1 text-xs text-slate-500">{w.start_at ?? (typeof w.start_offset_hours === 'number' ? `بعد ${w.start_offset_hours} ساعة` : '—')}{w.end_at ? ` → ${w.end_at}` : ''}{typeof w.score === 'number' ? ` · score: ${w.score}` : ''}</p>
                {w.limiting_factors?.length ? <p className="mt-1 text-xs text-amber-200">العوامل المحددة: {w.limiting_factors.join(' · ')}</p> : null}
              </li>
            ))}</ol> : <EmptyState title="لا توجد نوافذ تشغيل" hint="الخادم لم يرجع windows؛ لا يتم تكوين نافذة من الواجهة." />}
          </div>}
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
          <div className="mb-4 flex items-center gap-2"><ShieldAlert className="h-5 w-5 text-emerald-300" /><h3 className="text-sm font-bold text-slate-100">مخاطر الأمراض</h3></div>
          {diseaseQ.isLoading && <LoadingState message="جارٍ تحميل مخاطر الأمراض…" />}
          {diseaseQ.isError && <WeatherState title="مخاطر الأمراض" error={diseaseQ.error} onRetry={() => diseaseQ.refetch()} />}
          {diseaseQ.data && <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-semibold text-slate-100">مستوى الخطر</p><span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-400">{diseaseQ.data.risk_level}</span></div>
            <p className="mt-2 text-sm text-slate-300">{diseaseQ.data.diseases_ar?.length ? diseaseQ.data.diseases_ar.join(' · ') : 'لا توجد أمراض معلنة من الخادم.'}</p>
            {diseaseQ.data.advice_ar && <p className="mt-2 text-xs leading-relaxed text-slate-400">{diseaseQ.data.advice_ar}</p>}
          </div>}
        </div>
      </div>
    </section>
  );
}
