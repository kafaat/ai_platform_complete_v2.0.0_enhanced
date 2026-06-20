// ═══════════════════════════════════════════════════════════════
// SAHOOL — AgronomicTimelinePage (مثل Git history للحقل)
// قراءة فقط: خطّ زمنيّ موحّد لحقل واحد (دورة حياة/عمليّات/مشاهدات/معايرة/طقس/نظام)
// مرتّباً (الأحدث أوّلاً)، بأيقونات/فئات وفلترة بالفئة + إحصاءات لكلّ فئة. تستهلك
// GET /api/v1/fields/{id}/unified-timeline (assemble_timeline). صدق: لا أحداث ⇒
// EmptyState، وتعطّل القاعدة ⇒ note_ar معروض (حالة فارغة صادقة لا تاريخ مخترَع).
// (يطابق أنماط LineagePage/FieldWorkspaceMapCard بصريّاً ولونيّاً.)
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  GitCommitHorizontal, Sprout, Droplets, Eye, FlaskConical, CloudRain,
  Settings as Cog, MapPin, AlertTriangle, Clock,
} from 'lucide-react';
import { useUnifiedTimeline } from '../hooks/useApi';
import { useSelectedField } from '../hooks/useSelectedField';
import type { UnifiedTimelineEvent } from '../services/api';
import { ErrorState, LoadingState, EmptyState } from '../components/StateViews';

// فئات الخطّ الزمنيّ (تطابق TimelineCategory الخلفيّ) — أيقونة + لون + تسمية عربيّة.
const CATEGORY_META: Record<
  string,
  { ar: string; icon: React.ReactNode; color: string }
> = {
  lifecycle:   { ar: 'دورة الحياة', icon: <Sprout className="w-4 h-4" />, color: '#4ade80' },
  operation:   { ar: 'عمليّات', icon: <Droplets className="w-4 h-4" />, color: '#38bdf8' },
  observation: { ar: 'مشاهدات', icon: <Eye className="w-4 h-4" />, color: '#fbbf24' },
  calibration: { ar: 'معايرة', icon: <FlaskConical className="w-4 h-4" />, color: '#a78bfa' },
  weather:     { ar: 'طقس', icon: <CloudRain className="w-4 h-4" />, color: '#60a5fa' },
  system:      { ar: 'نظام', icon: <Cog className="w-4 h-4" />, color: '#94a3b8' },
};

function catMeta(category: string) {
  return CATEGORY_META[category] ?? { ar: category, icon: <Cog className="w-4 h-4" />, color: '#94a3b8' };
}

// عنصر حدث واحد في الخطّ (نقطة على المحور + بطاقة).
function TimelineRow({ ev }: { ev: UnifiedTimelineEvent }) {
  const meta = catMeta(ev.category);
  return (
    <li className="relative pr-8">
      {/* نقطة المحور */}
      <span className="absolute right-[7px] top-3 w-3 h-3 rounded-full border-2"
        style={{ background: '#0f1117', borderColor: meta.color }} aria-hidden="true" />
      <div className="rounded-xl border p-3 space-y-1.5" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold flex items-center gap-1"
            style={{ background: `${meta.color}1a`, color: meta.color }}>
            {meta.icon}{meta.ar}
          </span>
          <span className="text-[11px] text-slate-500 flex items-center gap-1" dir="ltr">
            <Clock className="w-3 h-3" />{ev.timestamp || '—'}
          </span>
        </div>
        <div className="text-sm text-slate-200">{ev.summary_ar || ev.event_type}</div>
        <div className="flex items-center gap-2 text-[10px] text-slate-500">
          <span className="font-mono" dir="ltr">{ev.event_type}</span>
          {ev.actor_id && <span>· بواسطة {ev.actor_id}</span>}
        </div>
      </div>
    </li>
  );
}

export default function AgronomicTimelinePage() {
  const { options, fieldId, setFieldId, isLoading: fieldsLoading, isError: fieldsError } = useSelectedField();
  const [category, setCategory] = useState<string>('');
  const tl = useUnifiedTimeline(fieldId, { category: category || undefined });

  const data = tl.data;
  // الفئات المتاحة فعلاً (من إحصاءات الخادم) لبناء أزرار الفلترة — لا فئات مُختلقة.
  const availableCats = data ? Object.keys(data.category_counts) : [];

  return (
    <div className="space-y-6 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <GitCommitHorizontal className="w-5 h-5 text-emerald-400" />
        <h2 className="text-xl font-bold text-slate-100">الخطّ الزمنيّ الأغرونوميّ</h2>
      </div>
      <p className="text-sm text-slate-400">
        تاريخ الحقل الموحّد كسجلّ <span className="text-emerald-300">Git history</span>: دورة الحياة والعمليّات والمشاهدات
        والمعايرة والطقس وأحداث النظام — مرتّباً (الأحدث أوّلاً) بفئات قابلة للفلترة. صدق: تُعرَض الأحداث المسجَّلة فقط،
        ولا تاريخ مخترَع.
      </p>

      {/* اختيار الحقل */}
      <div className="rounded-xl border p-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <label className="flex flex-col gap-1 max-w-xs">
          <span className="text-xs text-slate-400 flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5 text-emerald-400" /> الحقل
          </span>
          {fieldsLoading ? (
            <span className="text-[12px] text-slate-500">جارٍ جلب الحقول…</span>
          ) : fieldsError ? (
            <span className="text-[12px] text-amber-300/80">تعذّر جلب قائمة الحقول.</span>
          ) : (
            <select value={fieldId} onChange={e => setFieldId(e.target.value)}
              className="px-3 py-2 rounded-lg text-sm"
              style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
              <option value="">— اختر حقلاً —</option>
              {options.map(o => <option key={o.id} value={o.id}>{o.name || o.id}</option>)}
            </select>
          )}
        </label>
      </div>

      {!fieldId && (
        <EmptyState
          icon={<GitCommitHorizontal className="w-8 h-8" />}
          title="اختر حقلاً لعرض خطّه الزمنيّ"
          hint="يجمع الخطّ كلّ ما حدث على الحقل عبر أنواع الكيانات (مرتّباً ومُصنّفاً)." />
      )}

      {fieldId && tl.isLoading && <LoadingState message="جارٍ جلب الخطّ الزمنيّ…" />}
      {fieldId && tl.isError && (
        <ErrorState title="تعذّر جلب الخطّ الزمنيّ"
          detail="قد تكون القاعدة غير متاحة (503) أو الحقل ليس لمستأجِرك (404)."
          onRetry={() => tl.refetch()} />
      )}

      {data && (
        <div className="space-y-4">
          {/* فلترة بالفئة (من الفئات المتاحة فعلاً) + إحصاءات */}
          {availableCats.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <button onClick={() => setCategory('')}
                className="text-[11px] px-2.5 py-1 rounded-full font-medium transition-colors"
                style={{
                  background: category === '' ? '#16a34a' : '#0f1117',
                  color: category === '' ? '#fff' : '#cbd5e1',
                  border: '1px solid #25303f',
                }}>
                الكلّ ({data.total_events})
              </button>
              {availableCats.map(cat => {
                const meta = catMeta(cat);
                const active = category === cat;
                return (
                  <button key={cat} onClick={() => setCategory(active ? '' : cat)}
                    className="text-[11px] px-2.5 py-1 rounded-full font-medium flex items-center gap-1 transition-colors"
                    style={{
                      background: active ? meta.color : '#0f1117',
                      color: active ? '#0f1117' : meta.color,
                      border: '1px solid #25303f',
                    }}>
                    {meta.icon}{meta.ar} ({data.category_counts[cat]})
                  </button>
                );
              })}
            </div>
          )}

          {/* تعطّل القاعدة ⇒ note_ar معروض (حالة فارغة صادقة) */}
          {data.note_ar && (
            <div className="rounded-xl border p-3 flex items-start gap-3"
              style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
              <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div className="text-[12px] text-amber-200">{data.note_ar}</div>
            </div>
          )}
          {data.error && (
            <div className="rounded-xl border p-3 flex items-start gap-3"
              style={{ background: '#2a0d0d', borderColor: '#f8717133' }}>
              <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <div className="text-[12px] text-red-200">{data.error}</div>
            </div>
          )}

          {/* الخطّ الزمنيّ أو حالة فارغة */}
          {data.events.length === 0 ? (
            <EmptyState
              icon={<Clock className="w-8 h-8" />}
              title="لا أحداث في الخطّ الزمنيّ"
              hint={category ? 'لا أحداث ضمن هذه الفئة — جرّب «الكلّ».' : 'لم تُسجَّل أحداث لهذا الحقل بعد. لا تاريخ مخترَع.'} />
          ) : (
            <ol className="relative space-y-3 border-r-2 mr-[1px]" style={{ borderColor: '#25303f' }}>
              {data.events.map((ev, i) => <TimelineRow key={`${ev.event_type}-${ev.timestamp}-${i}`} ev={ev} />)}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
