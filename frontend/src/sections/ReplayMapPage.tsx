// ═══════════════════════════════════════════════════════════════
// SAHOOL — ReplayMapPage (إعادة تشغيل الموسم / Agronomic Replay)
// قراءة فقط: يعيد تشغيل موسم حقل واحد كاملاً على خطّ زمنيّ واحد (NDVI/طقس/ريّ/
// قرار/نتيجة ميدانيّة) قابل للـscrub. كلّ مسار صفّ ملوّن، وكلّ حدث نقطة موضوعة
// بكسر تاريخه عبر span. منزلق (scrubber) يُرشِّح الأحداث حتى التاريخ المختار
// (إعادة تشغيل تدريجيّة). يستهلك GET /api/v1/fields/{id}/agronomic-replay.
//
// صدق: العلم مُطفأً (FEATURE_REPLAY_MAP) ⇒ 404 ⇒ «الميزة غير مُفعَّلة» (لا انهيار).
// 503/خطأ آخر ⇒ ErrorState صادقة. span=null أو event_count=0 ⇒ حالة فارغة صادقة
// (لا خطّ زمنيّ مخترَع). المسارات الفارغة تُعرَض «0 — لا أحداث» بصدق. value متغايرة
// (رقم/منطقيّ/كائن/null) تُصيَّر دفاعيّاً. يطابق أنماط AgronomicTimeline/EvidenceMap
// بصريّاً ولونيّاً (RTL، StateViews، بانر كهرمانيّ).
// ═══════════════════════════════════════════════════════════════
import { useMemo, useState } from 'react';
import {
  History, MapPin, AlertTriangle, ShieldAlert, Clock, Sliders,
  Leaf, CloudRain, Droplets, GitCommitHorizontal, CheckCircle2,
} from 'lucide-react';
import { useAgronomicReplay } from '../hooks/useApi';
import { useSelectedField } from '../hooks/useSelectedField';
import { asApiError } from '../services/api';
import type { ReplayTrackKey, ReplayEvent, AgronomicReplayResult } from '../services/api';
import { ErrorState, LoadingState, EmptyState } from '../components/StateViews';

// لون + أيقونة + خلفيّة شارة لكلّ مسار (يطابق مواصفة الألوان: ndvi=أخضر/weather=
// سماويّ/irrigation=أزرق/decision=بنفسجيّ/outcome=كهرمانيّ). أيّ مفتاح مجهول ⇒ رماديّ.
const TRACK_META: Record<ReplayTrackKey, { color: string; badgeBg: string; icon: React.ReactNode }> = {
  ndvi:       { color: '#22c55e', badgeBg: '#0c2a1a', icon: <Leaf className="w-3.5 h-3.5" /> },
  weather:    { color: '#38bdf8', badgeBg: '#0a2230', icon: <CloudRain className="w-3.5 h-3.5" /> },
  irrigation: { color: '#3b82f6', badgeBg: '#0a1830', icon: <Droplets className="w-3.5 h-3.5" /> },
  decision:   { color: '#a855f7', badgeBg: '#1e0f2e', icon: <GitCommitHorizontal className="w-3.5 h-3.5" /> },
  outcome:    { color: '#f59e0b', badgeBg: '#2a1a00', icon: <CheckCircle2 className="w-3.5 h-3.5" /> },
};
const FALLBACK_META = { color: '#94a3b8', badgeBg: '#1e293b', icon: <Clock className="w-3.5 h-3.5" /> };
function trackMeta(track: string) {
  return TRACK_META[track as ReplayTrackKey] ?? FALLBACK_META;
}

// زمن الحدث بالميلّي ثانية — يتحمّل تواريخ فقط (YYYY-MM-DD) أو طوابع كاملة. NaN ⇒ 0.
function ms(date: string): number {
  const t = Date.parse(date);
  return Number.isFinite(t) ? t : 0;
}

// كسر موضع الحدث على المحور [0..1] من span (RTL: نُعالج الكسر، والاتّجاه بصريّ فقط).
function fractionOf(date: string, startMs: number, endMs: number): number {
  if (endMs <= startMs) return 0; // span بطول صفر (حدث واحد) ⇒ في البداية
  const f = (ms(date) - startMs) / (endMs - startMs);
  return Math.min(1, Math.max(0, f));
}

// تصيير value المتغايرة كنصّ عربيّ مقروء (رقم/منطقيّ/كائن/null) — دفاعيّ، لا تلفيق.
function valueText(value: ReplayEvent['value']): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? 'نعم' : 'لا';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
  // كائن (مثل طقس) — ملخّص مختصر بلا افتراض حقول بعينها.
  try {
    return JSON.stringify(value);
  } catch {
    return '—';
  }
}

// التاريخ كنصّ يوميّ قصير (أوّل 10 محارف ISO) — عرضٌ ثابت بلا منطقة زمنيّة مُضلِّلة.
function dayOf(date: string): string {
  return date ? date.slice(0, 10) : '—';
}

// ── شارة مسار ملوّنة (للأسطورة وقائمة الأحداث) ──
function TrackBadge({ track, track_ar }: { track: string; track_ar: string }) {
  const meta = trackMeta(track);
  return (
    <span
      className="text-[11px] px-2 py-0.5 rounded-full font-semibold inline-flex items-center gap-1 whitespace-nowrap"
      style={{ background: meta.badgeBg, color: meta.color }}
    >
      {meta.icon}
      {track_ar}
    </span>
  );
}

export default function ReplayMapPage() {
  const { options, fieldId, setFieldId, isLoading: fieldsLoading, isError: fieldsError } = useSelectedField();
  const query = useAgronomicReplay(fieldId);
  const data = query.data;

  // كشف 404 (العلم FEATURE_REPLAY_MAP مُطفأ) عبر شكل خطأ أكسيوس الموحّد.
  const featureOff = query.isError && asApiError(query.error).response?.status === 404;

  // موضع المنزلق: كسر [0..1] على span. القيمة 1 (النهاية) = عرض كلّ الأحداث.
  const [scrub, setScrub] = useState(1);

  const span = data?.span ?? null;
  const startMs = span ? ms(span.start) : 0;
  const endMs = span ? ms(span.end) : 0;

  // التاريخ المختار حاليّاً (من كسر المنزلق) — لتسمية «حتى …» وترشيح الأحداث.
  const cutoffMs = span ? startMs + scrub * (endMs - startMs) : 0;

  // الأحداث المعروضة: حتى cutoff (مُدامة مسبقاً تصاعديّاً، نُرشّح فقط) — «إعادة تشغيل».
  const shownEvents = useMemo<ReplayEvent[]>(() => {
    if (!data || !span) return [];
    return data.events.filter((e) => ms(e.date) <= cutoffMs + 1); // +1ms هامش حدّ
  }, [data, span, cutoffMs]);

  const cutoffLabel = span ? new Date(cutoffMs).toISOString().slice(0, 10) : '—';

  return (
    <div className="space-y-6 max-w-5xl mx-auto" dir="rtl">
      {/* ── الترويسة ── */}
      <div className="flex items-center gap-2">
        <History className="w-5 h-5 text-emerald-400" aria-hidden="true" />
        <h2 className="text-xl font-bold text-slate-100">إعادة تشغيل الموسم</h2>
      </div>
      <p className="text-sm text-slate-400">
        أعِد تشغيل موسم الحقل كاملاً على <span className="text-emerald-300">خطّ زمنيّ واحد</span>: مؤشّر NDVI والطقس والريّ
        والقرارات والنتائج الميدانيّة، مرتّبةً زمنيّاً. حرّك <span className="text-emerald-300">المنزلق</span> لتشغيلها تدريجيّاً.
        صدق: تُعرَض الأحداث المُدامة فقط — لا تاريخ مخترَع.
      </p>

      {/* ── اختيار الحقل ── */}
      <div className="rounded-xl border p-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <label className="flex flex-col gap-1 max-w-xs">
          <span className="text-xs text-slate-400 flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" /> الحقل
          </span>
          {fieldsLoading ? (
            <span className="text-[12px] text-slate-500">جارٍ جلب الحقول…</span>
          ) : fieldsError ? (
            <span className="text-[12px] text-amber-300/80">تعذّر جلب قائمة الحقول.</span>
          ) : (
            <select
              value={fieldId}
              onChange={(e) => setFieldId(e.target.value)}
              aria-label="اختيار الحقل"
              className="px-3 py-2 rounded-lg text-sm"
              style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}
            >
              <option value="">— اختر حقلاً —</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name || o.id}
                </option>
              ))}
            </select>
          )}
        </label>
      </div>

      {/* ── لا حقل مُختار ── */}
      {!fieldId && (
        <EmptyState
          icon={<History className="w-8 h-8" />}
          title="اختر حقلاً لإعادة تشغيل موسمه"
          hint="يجمع الخطّ كلّ أحداث الموسم المُدامة (مؤشّر/طقس/ريّ/قرار/نتيجة) على محور واحد."
        />
      )}

      {/* ── الحالات ── */}
      {fieldId && query.isLoading && <LoadingState message="جارٍ جلب إعادة التشغيل…" />}

      {/* الميزة غير مُفعَّلة (404 — العلم مُطفأ) */}
      {fieldId && featureOff && (
        <div
          className="rounded-xl border p-4 flex items-start gap-3"
          style={{ background: '#1e293b', borderColor: '#334155' }}
          role="status"
        >
          <ShieldAlert className="w-5 h-5 text-slate-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
          <div className="space-y-1">
            <div className="text-sm font-semibold text-slate-200">الميزة غير مُفعَّلة (FEATURE_REPLAY_MAP)</div>
            <div className="text-[12px] text-slate-400">
              إعادة تشغيل الموسم خلف علم تشغيل (FEATURE_REPLAY_MAP) لم يُفعَّل بعد على الخادم. تواصل مع المسؤول لتفعيله.
            </div>
          </div>
        </div>
      )}

      {/* 503/أيّ خطأ آخر — حالة خطأ صادقة */}
      {fieldId && query.isError && !featureOff && (
        <ErrorState
          title="تعذّر جلب إعادة التشغيل"
          detail="قد تكون قاعدة البيانات غير متاحة (503) أو الحقل ليس لمستأجِرك."
          onRetry={() => query.refetch()}
        />
      )}

      {data && <ReplayBody data={data} scrub={scrub} setScrub={setScrub} shownEvents={shownEvents} cutoffLabel={cutoffLabel} />}
    </div>
  );
}

// جسم النتيجة (data موجود) — يفصل المنطق الفارغ عن العرض كي يبقى المكوّن الأعلى نظيفاً.
function ReplayBody({
  data,
  scrub,
  setScrub,
  shownEvents,
  cutoffLabel,
}: {
  data: AgronomicReplayResult;
  scrub: number;
  setScrub: (v: number) => void;
  shownEvents: ReplayEvent[];
  cutoffLabel: string;
}) {
  const span = data.span;
  const startMs = span ? ms(span.start) : 0;
  const endMs = span ? ms(span.end) : 0;
  const hasTimeline = !!span && data.event_count > 0;

  return (
    <div className="space-y-6">
      {/* ── بانر الصدق/المصدر (provenance) — كهرمانيّ ── */}
      <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
        <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
        <div className="space-y-1">
          <div className="text-sm font-semibold text-amber-200">🟡 خطّ زمنيّ من سجلّات مُدامة فقط — لا تاريخ مخترَع</div>
          <div className="text-[12px] text-amber-300/80">{data.provenance.note_ar}</div>
          <div className="text-[11px] text-slate-400">
            أحداث: <span className="text-slate-300 font-medium">{data.event_count}</span>
            {' · '}آخر تحديث: <span className="text-slate-300" dir="ltr">{data.generated_at}</span>
            {span ? (
              <>
                {' · '}المدى: <span className="text-slate-300" dir="ltr">{dayOf(span.start)} → {dayOf(span.end)}</span>
              </>
            ) : (
              <>
                {' · '}المدى: <span className="text-slate-300">—</span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ── الأسطورة + العدّ لكلّ مسار (من tracks + counts_by_track) ── */}
      <section className="space-y-2">
        <div className="text-sm font-semibold text-slate-200">المسارات</div>
        <div className="flex flex-wrap gap-2">
          {data.tracks.map((t) => {
            const count = data.counts_by_track?.[t.track] ?? 0;
            const meta = trackMeta(t.track);
            return (
              <div
                key={t.track}
                className="flex items-center gap-2 rounded-lg px-3 py-1.5 border"
                style={{ background: '#1e293b', borderColor: '#334155' }}
              >
                <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: meta.color }} aria-hidden="true" />
                <span className="text-[12px] text-slate-200">{t.track_ar}</span>
                <span className="text-[11px] text-slate-400">
                  {count > 0 ? `${count}` : '0 — لا أحداث'}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── حالة فارغة صادقة (span=null أو event_count=0) — لا خطّ زمنيّ مخترَع ── */}
      {!hasTimeline ? (
        <EmptyState
          icon={<Clock className="w-8 h-8" />}
          title="لا أحداث مُدامة لهذا الحقل بعد"
          hint="لم تُسجَّل بعدُ أحداث NDVI/طقس/ريّ/قرار/نتيجة لهذا الحقل — لا خطّ زمنيّ يُعرَض (لا تاريخ مخترَع)."
        />
      ) : (
        <>
          {/* ── المنزلق (scrubber): يُرشِّح الأحداث حتى التاريخ المختار ── */}
          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <Sliders className="w-4 h-4 text-emerald-400" aria-hidden="true" />
              <h3 className="text-base font-bold text-slate-100">المنزلق الزمنيّ</h3>
              <span className="text-[12px] text-slate-400">
                حتى <span className="text-emerald-300 font-medium" dir="ltr">{cutoffLabel}</span>
                {' · '}
                <span className="text-slate-300 font-medium">{shownEvents.length}</span> / {data.event_count} حدث
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.001}
              value={scrub}
              onChange={(e) => setScrub(Number(e.target.value))}
              aria-label="منزلق إعادة التشغيل الزمنيّ"
              className="w-full accent-emerald-500"
            />
            <div className="flex justify-between text-[11px] text-slate-500" dir="ltr">
              <span>{dayOf(span.start)}</span>
              <span>{dayOf(span.end)}</span>
            </div>
          </section>

          {/* ── الخطّ الزمنيّ (SVG/divs، صفّ لكلّ مسار، نقطة لكلّ حدث بكسر تاريخه) ── */}
          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <History className="w-4 h-4 text-emerald-400" aria-hidden="true" />
              <h3 className="text-base font-bold text-slate-100">الخطّ الزمنيّ</h3>
            </div>
            <div className="rounded-xl border p-4 space-y-3" style={{ background: '#0f1117', borderColor: '#334155' }}>
              {data.tracks.map((t) => {
                const meta = trackMeta(t.track);
                const trackEvents = data.events.filter((e) => e.track === t.track);
                return (
                  <div key={t.track} className="flex items-center gap-3">
                    {/* تسمية المسار (ثابتة العرض) */}
                    <span className="text-[11px] w-24 flex-shrink-0 flex items-center gap-1" style={{ color: meta.color }}>
                      {meta.icon}
                      <span className="truncate">{t.track_ar}</span>
                    </span>
                    {/* مسار النقاط — موضع كلّ نقطة بكسر تاريخها؛ RTL ⇒ نضع right بالكسر */}
                    <div className="relative flex-1 h-6 rounded" style={{ background: '#1e293b' }}>
                      {trackEvents.length === 0 ? (
                        <span className="absolute inset-0 flex items-center justify-center text-[10px] text-slate-600">
                          لا أحداث
                        </span>
                      ) : (
                        trackEvents.map((ev, i) => {
                          const frac = fractionOf(ev.date, startMs, endMs);
                          const active = ms(ev.date) <= startMs + scrub * (endMs - startMs) + 1;
                          return (
                            <span
                              key={`${ev.track}-${ev.ref_id ?? ''}-${ev.date}-${i}`}
                              className="absolute top-1/2 -translate-y-1/2 rounded-full border-2 transition-opacity"
                              style={{
                                right: `calc(${frac * 100}% - 5px)`,
                                width: 10,
                                height: 10,
                                background: active ? meta.color : '#0f1117',
                                borderColor: meta.color,
                                opacity: active ? 1 : 0.35,
                              }}
                              title={`${dayOf(ev.date)} · ${ev.track_ar} · ${ev.label_ar} · ${valueText(ev.value)}`}
                              aria-label={`${ev.track_ar} ${ev.label_ar} ${dayOf(ev.date)}`}
                            />
                          );
                        })
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {/* ── قائمة الأحداث (رفيقة/احتياط) — مُرشَّحة بموضع المنزلق ── */}
          <section className="space-y-2">
            <div className="text-sm font-semibold text-slate-200">
              الأحداث المعروضة ({shownEvents.length})
            </div>
            {shownEvents.length === 0 ? (
              <div className="rounded-xl border p-4 text-sm text-slate-400" style={{ background: '#1e293b', borderColor: '#334155' }} role="status">
                لا أحداث حتى هذا التاريخ — حرّك المنزلق نحو النهاية.
              </div>
            ) : (
              <ol className="space-y-2 max-h-80 overflow-auto">
                {shownEvents.map((ev, i) => (
                  <li
                    key={`${ev.track}-${ev.ref_id ?? ''}-${ev.date}-${i}`}
                    className="flex items-center gap-3 rounded-lg border p-2.5 text-sm"
                    style={{ background: '#1e293b', borderColor: '#25303f' }}
                  >
                    <span className="text-[11px] text-slate-500 w-24 flex-shrink-0 flex items-center gap-1" dir="ltr">
                      <Clock className="w-3 h-3" aria-hidden="true" />
                      {dayOf(ev.date)}
                    </span>
                    <TrackBadge track={ev.track} track_ar={ev.track_ar} />
                    <span className="text-slate-200 flex-1 min-w-0 truncate">{ev.label_ar}</span>
                    <span className="text-[12px] text-slate-400 font-mono flex-shrink-0" dir="ltr">{valueText(ev.value)}</span>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </div>
  );
}
