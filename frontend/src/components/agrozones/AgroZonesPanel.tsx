// ═══════════════════════════════════════════════════════════════
// SAHOOL — لوحة الأقاليم المناخيّة-الزراعيّة
// ───────────────────────────────────────────────────────────────
// تعرض الأقاليم الستّة (list) وعند اختيار إقليم تُظهر ملفّه (profile)
// ومحاصيله الملائمة (suited-crops). تستهلك hooks useAgroZones — تربط
// ٦ نقاط backend كانت بلا واجهة (دَين high×button). RTL · لا emojis.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  useAgroZonesList,
  useAgroZoneProfile,
  useAgroZoneSuitedCrops,
} from '../../hooks/useAgroZones';

export default function AgroZonesPanel() {
  const [selectedZone, setSelectedZone] = useState<string>('');
  const [irrigated, setIrrigated] = useState(true);

  const zonesQuery = useAgroZonesList();
  const profileQuery = useAgroZoneProfile(selectedZone, !!selectedZone);
  const suitedQuery = useAgroZoneSuitedCrops(selectedZone, irrigated, !!selectedZone);

  if (zonesQuery.isLoading) {
    return <div className="p-4 text-slate-400">جارٍ تحميل الأقاليم…</div>;
  }
  if (zonesQuery.isError) {
    return (
      <div className="p-4 text-red-400">
        تعذّر تحميل الأقاليم المناخيّة-الزراعيّة.
      </div>
    );
  }

  const zones = zonesQuery.data ?? [];

  return (
    <div dir="rtl" className="flex flex-col gap-4 p-4">
      <h2 className="text-lg font-semibold text-slate-100">
        الأقاليم المناخيّة-الزراعيّة
      </h2>

      {/* شريط اختيار الإقليم */}
      <div className="flex flex-wrap gap-2">
        {zones.map((z) => (
          <button
            key={z.zone}
            onClick={() => setSelectedZone(z.zone)}
            className={`rounded-lg px-3 py-2 text-sm transition ${
              selectedZone === z.zone
                ? 'bg-emerald-600 text-white'
                : 'bg-slate-800 text-slate-200 hover:bg-slate-700'
            }`}
          >
            {z.name_ar ?? z.zone}
          </button>
        ))}
      </div>

      {/* تفاصيل الإقليم المختار */}
      {selectedZone && (
        <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
          {profileQuery.isLoading ? (
            <div className="text-slate-400">جارٍ تحميل ملفّ الإقليم…</div>
          ) : profileQuery.isError ? (
            <div className="text-red-400">تعذّر تحميل ملفّ الإقليم.</div>
          ) : (
            <div className="flex flex-col gap-3">
              <h3 className="text-base font-medium text-emerald-300">
                {profileQuery.data?.name_ar ?? selectedZone}
              </h3>

              {/* مبدّل الريّ */}
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={irrigated}
                  onChange={(e) => setIrrigated(e.target.checked)}
                  className="accent-emerald-500"
                />
                محاصيل مرويّة
              </label>

              {/* المحاصيل الملائمة */}
              {suitedQuery.isLoading ? (
                <div className="text-slate-400">جارٍ حساب المحاصيل الملائمة…</div>
              ) : suitedQuery.data ? (
                <div className="grid gap-2 sm:grid-cols-2">
                  <div>
                    <div className="mb-1 text-xs text-slate-400">محاصيل ملائمة</div>
                    <ul className="list-inside list-disc text-sm text-slate-200">
                      {(suitedQuery.data.suited_crops_ar ?? []).map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div className="mb-1 text-xs text-slate-400">يُتجنّب</div>
                    <ul className="list-inside list-disc text-sm text-slate-400">
                      {(suitedQuery.data.avoid_ar ?? []).map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ul>
                  </div>
                  {suitedQuery.data.water_note_ar && (
                    <div className="sm:col-span-2 text-xs text-amber-300">
                      {suitedQuery.data.water_note_ar}
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
