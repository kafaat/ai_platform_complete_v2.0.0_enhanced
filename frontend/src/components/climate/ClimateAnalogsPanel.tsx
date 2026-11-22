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
import ReferenceQueryState from '../ReferenceQueryState';

export default function ClimateAnalogsPanel() {
  const [region, setRegion] = useState<string>('');
  const [category, setCategory] = useState<string>('');

  const listQuery = useClimateAnalogsList();
  const detailQuery = useClimateAnalogDetail(region, !!region);
  const cropsQuery = useDesertCrops(category || undefined);
  const tiersQuery = useStrategicTiers();

  return (
    <div dir="rtl" className="flex flex-col gap-4 p-4">
      <h2 className="text-lg font-semibold text-sahool-text">النظائر المناخيّة</h2>
      <p className="text-xs text-sahool-muted">
        مناطق عالميّة مشابهة مناخيّاً لليمن — تُرشد لمحاصيل مُجرّبة في ظروف مماثلة.
      </p>

      {/* قائمة المناطق النظيرة */}
      <ReferenceQueryState
        query={listQuery}
        loadingText="جارٍ تحميل المناطق النظيرة…"
        errorText="تعذّر تحميل النظائر المناخيّة."
        emptyText="لا مناطق نظيرة متاحة."
      >
        {(regions) => (
          <div className="flex flex-wrap gap-2">
            {regions.map((r) => (
              <button
                key={r.region}
                onClick={() => setRegion(r.region)}
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
      </ReferenceQueryState>

      {/* تفصيل المنطقة المختارة */}
      {region && (
        <ReferenceQueryState
          query={detailQuery}
          loadingText="جارٍ تحميل تفصيل المنطقة…"
          errorText="تعذّر تحميل تفصيل المنطقة."
          emptyText="لا تفصيل لهذه المنطقة."
        >
          {(detail) =>
            detail.supported === false ? (
              <div className="text-ops-warning">{detail.message_ar ?? 'المنطقة غير معروفة.'}</div>
            ) : (
              <div className="rounded-xl border border-sahool-border bg-sahool-surface/60 p-4 text-sm text-sahool-text">
                <h3 className="mb-2 text-base font-medium text-ops-warning">
                  {detail.region_ar ?? region}
                </h3>
                <pre className="whitespace-pre-wrap text-xs text-sahool-text">
                  {JSON.stringify(detail, null, 2)}
                </pre>
              </div>
            )
          }
        </ReferenceQueryState>
      )}

      {/* محاصيل صحراويّة */}
      <details className="rounded-xl border border-sahool-border bg-sahool-surface/40 p-3">
        <summary className="cursor-pointer text-sm text-sahool-green-dark">
          محاصيل صحراويّة مُوصى بها
        </summary>
        <div className="mt-2">
          <input
            type="text"
            placeholder="تصفية بالفئة (اختياريّ)"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="mb-2 rounded-sm bg-sahool-surface px-2 py-1 text-sm text-sahool-text"
          />
          <ReferenceQueryState
            query={cropsQuery}
            loadingText="جارٍ التحميل…"
            errorText="تعذّر تحميل المحاصيل الصحراويّة."
            emptyText="لا محاصيل لهذه الفئة."
          >
            {(crops) => (
              <ul className="grid gap-1 sm:grid-cols-2 md:grid-cols-3">
                {crops.map((c) => (
                  <li key={`${c.category ?? ''}:${c.crop}`} className="text-xs text-sahool-text">
                    {c.name_ar}
                    {c.rating ? ` · ${c.rating}` : ''}
                    {c.category ? ` (${c.category})` : ''}
                  </li>
                ))}
              </ul>
            )}
          </ReferenceQueryState>
        </div>
      </details>

      {/* الطبقات الاستراتيجيّة */}
      <details className="rounded-xl border border-sahool-border bg-sahool-surface/40 p-3">
        <summary className="cursor-pointer text-sm text-sahool-green-dark">الطبقات الاستراتيجيّة</summary>
        <ReferenceQueryState
          query={tiersQuery}
          loadingText="جارٍ التحميل…"
          errorText="تعذّر تحميل الطبقات الاستراتيجيّة."
          emptyText="لا طبقات متاحة."
        >
          {(tiers) => (
            <pre className="mt-2 whitespace-pre-wrap text-xs text-sahool-text">
              {JSON.stringify(tiers, null, 2)}
            </pre>
          )}
        </ReferenceQueryState>
      </details>
    </div>
  );
}
