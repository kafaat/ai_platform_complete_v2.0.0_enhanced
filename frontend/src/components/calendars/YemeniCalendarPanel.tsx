// ═══════════════════════════════════════════════════════════════
// SAHOOL — لوحة التقويم اليمنيّ التراثيّ
// ───────────────────────────────────────────────────────────────
// تعرض المنازل القمريّة والشهور الحميريّة والجسر الزمنيّ لتاريخ مختار.
// معرفة تراثيّة (عرض فقط). تستهلك useYemeniCalendars — تربط ٤ نقاط backend
// كانت دَينًا (high×button). RTL · لا emojis.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  useLunarMansions,
  useHimyariteMonths,
  useCalendarContext,
} from '../../hooks/useYemeniCalendars';

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function YemeniCalendarPanel() {
  const [dateIso, setDateIso] = useState<string>(todayIso());
  const [governorate, setGovernorate] = useState<string>('');

  const mansionsQuery = useLunarMansions();
  const monthsQuery = useHimyariteMonths();
  const contextQuery = useCalendarContext(dateIso, governorate || undefined, !!dateIso);

  return (
    <div dir="rtl" className="flex flex-col gap-4 p-4">
      <h2 className="text-lg font-semibold text-slate-100">التقويم اليمنيّ التراثيّ</h2>

      {/* الجسر الزمنيّ: تاريخ → منزلة + شهر حميريّ */}
      <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-slate-300">
            التاريخ
            <input
              type="date"
              value={dateIso}
              onChange={(e) => setDateIso(e.target.value)}
              className="rounded bg-slate-800 px-2 py-1 text-slate-100"
            />
          </label>
          <input
            type="text"
            placeholder="المحافظة (اختياريّ)"
            value={governorate}
            onChange={(e) => setGovernorate(e.target.value)}
            className="rounded bg-slate-800 px-2 py-1 text-sm text-slate-100"
          />
        </div>

        {contextQuery.isLoading ? (
          <div className="text-slate-400">جارٍ حساب السياق الزمنيّ…</div>
        ) : contextQuery.isError ? (
          <div className="text-red-400">تعذّر حساب السياق.</div>
        ) : contextQuery.data ? (
          <div className="grid gap-2 text-sm text-slate-200 sm:grid-cols-3">
            <div>
              <div className="text-xs text-slate-400">المنزلة النشطة</div>
              {contextQuery.data.active_mansion?.name_ar ?? '—'}
            </div>
            <div>
              <div className="text-xs text-slate-400">الشهر الحميريّ</div>
              {contextQuery.data.himyarite_month?.name_ar ?? '—'}
            </div>
            <div>
              <div className="text-xs text-slate-400">المنطقة</div>
              {contextQuery.data.regional_profile?.region_ar ?? '—'}
            </div>
          </div>
        ) : null}
      </div>

      {/* المنازل القمريّة الـ٢٨ */}
      <details className="rounded-xl border border-slate-700 bg-slate-900/40 p-3">
        <summary className="cursor-pointer text-sm text-emerald-300">
          المنازل القمريّة الـ٢٨ (نجوم الزراعة)
        </summary>
        {mansionsQuery.isLoading ? (
          <div className="mt-2 text-slate-400">جارٍ التحميل…</div>
        ) : (
          <ul className="mt-2 grid gap-1 sm:grid-cols-2 md:grid-cols-4">
            {(mansionsQuery.data ?? []).map((m, i) => (
              <li key={m.index ?? i} className="text-xs text-slate-300">
                {m.name_ar ?? `منزلة ${i + 1}`}
              </li>
            ))}
          </ul>
        )}
      </details>

      {/* الشهور الحميريّة */}
      <details className="rounded-xl border border-slate-700 bg-slate-900/40 p-3">
        <summary className="cursor-pointer text-sm text-emerald-300">
          الشهور الحميريّة الـ١٢
        </summary>
        {monthsQuery.isLoading ? (
          <div className="mt-2 text-slate-400">جارٍ التحميل…</div>
        ) : (
          <ul className="mt-2 grid gap-1 sm:grid-cols-2 md:grid-cols-3">
            {(monthsQuery.data ?? []).map((mo, i) => (
              <li key={mo.index ?? i} className="text-xs text-slate-300">
                {mo.name_ar ?? `شهر ${i + 1}`}
                {mo.gregorian_approx ? ` · ${mo.gregorian_approx}` : ''}
              </li>
            ))}
          </ul>
        )}
      </details>
    </div>
  );
}
