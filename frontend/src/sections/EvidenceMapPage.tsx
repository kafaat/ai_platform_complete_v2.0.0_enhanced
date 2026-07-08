// ═══════════════════════════════════════════════════════════════
// SAHOOL — EvidenceMapPage (خريطة الدليل) — يستهلك GET /api/v1/evidence/map
// قراءة فقط: خريطة 2D حقيقيّة + قائمة تُظهر لكلّ حقل **مستوى الدليل** خلف قراراته
// (مؤكَّد ميدانيّاً / مدعوم أوّليّ / إرشاديّ / يحتاج بيانات) — لا مجرّد النتيجة بل
// مستوى الدليل. صدق: مستوى الدليل من القرارات/القياسات المُدامة فقط؛ عتبة التحقّق
// الميدانيّ تقديريّة (بانر كهرمانيّ). الحقول بلا إحداثيّات (has_coords=false) لا
// تُرسَم (لا إحداثيّات مُختلَقة) — تظهر في القائمة فقط بوسم «بلا إحداثيّات».
// needs_data «لا دليل بعد» صادق (رماديّ) لا حالة إيجابيّة خضراء.
//
// العلم مُطفأً (FEATURE_EVIDENCE_MAP) ⇒ 404 ⇒ «الميزة غير مُفعَّلة» (لا انهيار).
// 503 ⇒ القاعدة غير متاحة (ErrorState صادقة). fields:[] ⇒ «لا حقول».
// ═══════════════════════════════════════════════════════════════
import { useMemo } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import { ShieldCheck, MapPinned, AlertTriangle, MapPinOff } from 'lucide-react';
import '../lib/leafletSetup'; // CSS + أيقونات Leaflet (side-effect حاسم للتصيير)
import { useEvidenceMap } from '../hooks/useApi';
import type { EvidenceMapField, EvidenceMapColor } from '../services/api';
import { LoadingState } from '../components/StateViews';
import { AdvancedServiceState } from '../components/product/AdvancedServiceState';

// مركز اليمن وتكبير معقول (نفس نمط OperationCenterWall لكن نطاق وطنيّ).
const YEMEN_CENTER: [number, number] = [15.5, 45.5];
const YEMEN_ZOOM = 6;
const BASEMAP_SAT =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

// ربط لون الخادم (green|amber|blue|gray) بألوان CSS/علامات محدّدة في الواجهة.
// لا فئات إضافيّة: أيّ لون مجهول ⇒ رماديّ محايد (fail-safe، لا حالة إيجابيّة مُختلَقة).
const COLOR_HEX: Record<EvidenceMapColor, string> = {
  green: '#16a34a',
  amber: '#d97706',
  blue:  '#2563eb',
  gray:  '#9ca3af',
};
function hexFor(color: string): string {
  return COLOR_HEX[color as EvidenceMapColor] ?? COLOR_HEX.gray;
}
// خلفيّة شارة خفيفة مشتقّة من نفس اللون (تباين مقروء على سطح داكن).
const BADGE_BG: Record<EvidenceMapColor, string> = {
  green: '#0c2a1a',
  amber: '#2a1a00',
  blue:  '#0a1f2e',
  gray:  '#1e293b',
};
function badgeBgFor(color: string): string {
  return BADGE_BG[color as EvidenceMapColor] ?? BADGE_BG.gray;
}

// نسبة النجاح كنصّ — null ⇒ «—» (لا تلفيق).
function successRateText(rate: number | null): string {
  return rate != null ? `${(rate * 100).toFixed(0)}%` : '—';
}

// شارة فئة ملوّنة (tier_ar) — لونها من color الخادم.
function TierBadge({ field }: { field: EvidenceMapField }) {
  const hex = hexFor(field.color);
  return (
    <span
      className="text-[11px] px-2 py-0.5 rounded-full font-semibold whitespace-nowrap"
      style={{ background: badgeBgFor(field.color), color: hex }}
    >
      {field.tier_ar}
    </span>
  );
}

export default function EvidenceMapPage() {
  const query = useEvidenceMap();
  const data = query.data;

  // الحقول القابلة للرسم فقط (has_coords + إحداثيّات رقميّة) — لا إحداثيّات مُختلَقة.
  const plottable = useMemo(
    () =>
      (data?.fields ?? []).filter(
        (f) => f.has_coords && typeof f.lat === 'number' && typeof f.lon === 'number',
      ),
    [data],
  );

  return (
    <div className="space-y-6 max-w-6xl mx-auto" dir="rtl">
      {/* ── الترويسة ── */}
      <div className="flex items-center gap-2">
        <ShieldCheck className="w-5 h-5 text-emerald-400" aria-hidden="true" />
        <h2 className="text-xl font-bold text-slate-100">خريطة الدليل</h2>
      </div>
      <p className="text-sm text-slate-400">
        خريطة تُظهر لكلّ حقل لا مجرّد النتيجة بل <span className="text-emerald-300">مستوى الدليل</span> خلف
        قراراته (مؤكَّد ميدانيّاً / مدعوم أوّليّ / إرشاديّ / يحتاج بيانات).
        الحقول <span className="text-amber-300">بلا إحداثيّات</span> لا تُرسَم — تظهر في القائمة فقط (لا إحداثيّات مُختلَقة).
      </p>

      {/* ── الحالات ── */}
      {query.isLoading && <LoadingState message="جارٍ جلب خريطة الدليل…" />}

      {query.isError && (
        <AdvancedServiceState
          page="evidence-map"
          error={query.error}
          resourceName="خريطة الدليل"
          onRetry={() => query.refetch()}
        />
      )}

      {/* fields:[] — لا حقول */}
      {data && data.fields.length === 0 && (
        <div
          className="rounded-xl border p-4 text-sm text-slate-400"
          style={{ background: '#1e293b', borderColor: '#334155' }}
          role="status"
        >
          لا حقول مُسجّلة لهذا المستأجِر — لا تتوفّر بيانات لخريطة الدليل.
        </div>
      )}

      {data && data.fields.length > 0 && (
        <div className="space-y-6">
          {/* ── بانر الصدق/المصدر (provenance) — كهرمانيّ ── */}
          <div
            className="rounded-xl border p-4 flex items-start gap-3"
            style={{ background: '#1a1400', borderColor: '#f59e0b33' }}
          >
            <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
            <div className="space-y-1">
              <div className="text-sm font-semibold text-amber-200">
                🟡 مستوى الدليل من القرارات/القياسات المُدامة فقط — عتبة التحقّق الميدانيّ تقديريّة
              </div>
              <div className="text-[12px] text-amber-300/80">{data.provenance.note_ar}</div>
              <div className="text-[11px] text-slate-400">
                عتبة التحقّق: <span className="text-slate-300 font-medium">{data.verified_threshold}</span> عيّنة
                {' · '}آخر تحديث: <span className="text-slate-300">{data.generated_at}</span>
                {' · '}قابل للرسم: <span className="text-slate-300 font-medium">{data.plottable_count}</span> / {data.field_count}
              </div>
            </div>
          </div>

          {/* ── الأسطورة (legend) مع العدّ من totals_by_tier ── */}
          <section className="space-y-2">
            <div className="text-sm font-semibold text-slate-200">مفتاح مستوى الدليل</div>
            <div className="flex flex-wrap gap-2">
              {data.legend.map((item) => {
                const hex = hexFor(item.color);
                const count = data.totals_by_tier?.[item.tier] ?? 0;
                return (
                  <div
                    key={item.tier}
                    className="flex items-center gap-2 rounded-lg px-3 py-1.5 border"
                    style={{ background: '#1e293b', borderColor: '#334155' }}
                  >
                    <span
                      className="w-3 h-3 rounded-full flex-shrink-0"
                      style={{ background: hex }}
                      aria-hidden="true"
                    />
                    <span className="text-[12px] text-slate-200">{item.tier_ar}</span>
                    <span
                      className="text-[12px] font-bold px-1.5 rounded-full"
                      style={{ background: badgeBgFor(item.color), color: hex }}
                    >
                      {count}
                    </span>
                  </div>
                );
              })}
            </div>
          </section>

          {/* ── الخريطة 2D (Leaflet) — علامة دائريّة ملوّنة لكلّ حقل قابل للرسم ── */}
          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <MapPinned className="w-4 h-4 text-emerald-400" aria-hidden="true" />
              <h3 className="text-base font-bold text-slate-100">الخريطة</h3>
            </div>
            {plottable.length === 0 ? (
              <div
                className="rounded-xl border p-4 text-sm text-slate-400"
                style={{ background: '#1e293b', borderColor: '#334155' }}
                role="status"
              >
                لا حقول بإحداثيّات حقيقيّة لرسمها على الخريطة (تظهر في القائمة أدناه فقط).
              </div>
            ) : (
              <div style={{ height: 460, borderRadius: 12, overflow: 'hidden' }}>
                <MapContainer center={YEMEN_CENTER} zoom={YEMEN_ZOOM} style={{ height: '100%', width: '100%' }}>
                  <TileLayer url={BASEMAP_SAT} attribution="Tiles &copy; Esri — World Imagery" />
                  {plottable.map((f) => {
                    const hex = hexFor(f.color);
                    return (
                      <CircleMarker
                        key={f.field_id}
                        center={[f.lat as number, f.lon as number]}
                        radius={8}
                        pathOptions={{ color: hex, fillColor: hex, fillOpacity: 0.85, weight: 1.5 }}
                      >
                        <Popup>
                          <div dir="rtl" style={{ minWidth: 180 }}>
                            <div style={{ fontWeight: 700 }}>{f.name}</div>
                            <div style={{ fontSize: 12, color: '#475569' }}>
                              {f.crop} · {f.gov}
                            </div>
                            <div style={{ fontSize: 12, fontWeight: 600, color: hex, marginTop: 4 }}>
                              {f.tier_ar}
                            </div>
                            <div style={{ fontSize: 12, marginTop: 4 }}>
                              قرارات: {f.decisions} · نتائج: {f.outcomes}
                            </div>
                            <div style={{ fontSize: 12 }}>
                              معدّل النجاح: {successRateText(f.success_rate)}
                            </div>
                            {f.tier !== 'field_verified' && (
                              <div style={{ fontSize: 12, color: '#b45309' }}>
                                تبقّى {f.samples_to_verified} عيّنة للتحقّق
                              </div>
                            )}
                          </div>
                        </Popup>
                      </CircleMarker>
                    );
                  })}
                </MapContainer>
              </div>
            )}
          </section>

          {/* ── قائمة الحقول (كلّها — بما فيها غير القابلة للرسم) ── */}
          <section className="space-y-2">
            <div className="text-sm font-semibold text-slate-200">
              كلّ الحقول ({data.field_count})
            </div>
            <div className="overflow-x-auto rounded-xl border" style={{ borderColor: '#334155' }}>
              <table className="w-full text-sm" style={{ background: '#1e293b' }}>
                <thead>
                  <tr className="text-[11px] text-slate-400 text-right">
                    <th className="px-3 py-2 font-medium">الحقل</th>
                    <th className="px-3 py-2 font-medium">المحصول</th>
                    <th className="px-3 py-2 font-medium">المحافظة</th>
                    <th className="px-3 py-2 font-medium">مستوى الدليل</th>
                    <th className="px-3 py-2 font-medium">قرارات</th>
                    <th className="px-3 py-2 font-medium">نتائج</th>
                    <th className="px-3 py-2 font-medium">معدّل النجاح</th>
                  </tr>
                </thead>
                <tbody>
                  {data.fields.map((f) => (
                    <tr
                      key={f.field_id}
                      className="border-t text-slate-200"
                      style={{ borderColor: '#25303f' }}
                    >
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium truncate">{f.name}</span>
                          {!f.has_coords && (
                            <span
                              className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full"
                              style={{ background: '#1e293b', color: '#94a3b8', border: '1px solid #334155' }}
                              title="بلا إحداثيّات — لا تُرسَم على الخريطة"
                            >
                              <MapPinOff className="w-3 h-3" aria-hidden="true" />
                              بلا إحداثيّات
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-slate-300">{f.crop}</td>
                      <td className="px-3 py-2 text-slate-300">{f.gov}</td>
                      <td className="px-3 py-2"><TierBadge field={f} /></td>
                      <td className="px-3 py-2 text-slate-300">{f.decisions}</td>
                      <td className="px-3 py-2 text-slate-300">{f.outcomes}</td>
                      <td className="px-3 py-2 text-slate-300">{successRateText(f.success_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
