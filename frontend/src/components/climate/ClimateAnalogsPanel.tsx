// ═══════════════════════════════════════════════════════════════
// SAHOOL — لوحة النظائر المناخيّة
// ───────────────────────────────────────────────────────────────
// تعرض المناطق النظيرة مناخيّاً وعند اختيار منطقة تُظهر تفصيلها، مع محاصيل
// صحراويّة والطبقات الاستراتيجيّة. يفيد الجوف الصحراويّ. RTL · لا emojis.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  useClimateAnalogsList,
  useClimateAnalogDetail,
  useDesertCrops,
  useStrategicTiers,
} from '../../hooks/useClimateAnalogs';

export default function ClimateAnalogsPanel() {
  const [region, setRegion] = useState<string>('');
  const [category, setCategory] = useState<string>('');

  const listQuery = useClimateAnalogsList();
  const detailQuery = useClimateAnalogDetail(region, !!region);
  const cropsQuery = useDesertCrops(category || undefined);
  const tiersQuery = useStrategicTiers();

  return (
    <div dir="rtl" className="flex flex-col gap-4 p-4">
      <h2 className="text-lg font-semibold text-slate-100">النظائر المناخيّة</h2>
      <p className="text-xs text-slate-400">
        مناطق عالميّة مشابهة مناخيّاً لليمن — تُرشد لمحاصيل مُجرّبة في ظروف مماثلة.
      </p>

      {/* قائمة المناطق النظيرة */}
      {listQuery.isLoading ? (
        <div className="text-slate-400">جارٍ تحميل المناطق النظيرة…</div>
      ) : listQuery.isError ? (
        <div className="text-red-400">تعذّر تحميل النظائر المناخيّة.</div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {(listQuery.data ?? []).map((r) => (
            <button
              key={r.region ?? r.name_ar}
              onClick={() => setRegion(r.region ?? '')}
              className={`rounded-lg px-3 py-2 text-sm transition ${
                region === r.region
                  ? 'bg-amber-600 text-white'
                  : 'bg-slate-800 text-slate-200 hover:bg-slate-700'
              }`}
            >
              {r.name_ar ?? r.region}
              {typeof r.similarity === 'number' ? ` · ${Math.round(r.similarity * 100)}%` : ''}
            </button>
          ))}
        </div>
      )}

      {/* تفصيل المنطقة المختارة */}
      {region && detailQuery.data && (
        <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4 text-sm text-slate-200">
          <h3 className="mb-2 text-base font-medium text-amber-300">
            {detailQuery.data.name_ar ?? region}
          </h3>
          <pre className="whitespace-pre-wrap text-xs text-slate-300">
            {JSON.stringify(detailQuery.data, null, 2)}
          </pre>
        </div>
      )}

      {/* محاصيل صحراويّة */}
      <details className="rounded-xl border border-slate-700 bg-slate-900/40 p-3">
        <summary className="cursor-pointer text-sm text-emerald-300">
          محاصيل صحراويّة مُوصى بها
        </summary>
        <div className="mt-2">
          <input
            type="text"
            placeholder="تصفية بالفئة (اختياريّ)"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="mb-2 rounded bg-slate-800 px-2 py-1 text-sm text-slate-100"
          />
          {cropsQuery.isLoading ? (
            <div className="text-slate-400">جارٍ التحميل…</div>
          ) : (
            <ul className="grid gap-1 sm:grid-cols-2 md:grid-cols-3">
              {(cropsQuery.data ?? []).map((c, i) => (
                <li key={c.crop ?? i} className="text-xs text-slate-300">
                  {c.name_ar ?? c.crop}
                  {c.category ? ` · ${c.category}` : ''}
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>

      {/* الطبقات الاستراتيجيّة */}
      {tiersQuery.data && (
        <details className="rounded-xl border border-slate-700 bg-slate-900/40 p-3">
          <summary className="cursor-pointer text-sm text-emerald-300">
            الطبقات الاستراتيجيّة
          </summary>
          <pre className="mt-2 whitespace-pre-wrap text-xs text-slate-300">
            {JSON.stringify(tiersQuery.data, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
