// ═══════════════════════════════════════════════════════════════
// SAHOOL — PrescriptionBuilderPage (منشئ وصفات المعدّل المتغيّر · يدويّ)
// ───────────────────────────────────────────────────────────────
// نظير FieldView "manual prescriptions". صدق أوّلاً: هذا منشئ **يدويّ** صرف —
// المستخدِم (١) يختار حقلاً فتظهر حدوده على خريطة Leaflet حقيقيّة، (٢) يرسم مناطق
// الإدارة (zones) بأداة الرسم (نفس leaflet-draw المستخدمة في القياس/إضافة الحقل)،
// (٣) يضبط لكلّ منطقة معدّلاً + وحدة (بذار seeds/m² أو تسميد kg/ha)، (٤) يسمّي
// الوصفة ويختار نوع المنتج {seed|fertility} ويحفظها (POST، tenant-scoped + RLS)،
// ثمّ يسرد المحفوظ (GET) ويُصدِّر المُختار إلى GeoJSON/CSV (client-side، Blob/URL).
//
// لا توليد agronomic آليّ هنا (الـGenerators في الخلفيّة api/prescriptions.py تبقى
// منفصلة)، ولا صيغة مُتحكِّم مُختلقة. التصدير = GeoJSON + CSV فقط؛ صيغ المُتحكِّمات
// (ISOXML/Shapefile) **مؤجّلة كـTODO موثَّق** — لا ندّعي إنتاج ما لا ننتجه فعلاً.
// المعدّلات/المناطق كلّها من إدخال المستخدِم — لا أرقام/مناطق مُفبركة.
//
// الحالات (تحميل/فراغ/خطأ) صريحة: قائمة فارغة ⇒ EmptyState صادق (note_ar من الخادم
// إن وُجد)؛ 503/403 ⇒ ErrorState. شارة النضج alpha صريحة. RTL · ds.
// ═══════════════════════════════════════════════════════════════
import { useCallback, useMemo, useState } from 'react';
import { MapContainer, TileLayer, Polygon, FeatureGroup } from 'react-leaflet';
import DrawControl from '../components/maphub/DrawControl'; // أداة رسم على leaflet-draw خام (بديل EditControl — توافق React 19)
import type * as GeoJSONNS from 'geojson';
import L from 'leaflet';
import '../lib/leafletSetup'; // CSS + أيقونات Leaflet + أداة الرسم (side-effect) — حاسم للتصيير
import {
  SlidersHorizontal, MapPin, Trash2, Download, Save, Plus,
} from 'lucide-react';
import { useSelectedField } from '../hooks/useSelectedField';
import { useFieldPrescriptions, useCreatePrescription } from '../hooks/useApi';
import { asApiError, exportPrescriptionShapefile } from '../services/api';
import type { SavedPrescription, SavedPrescriptionZone } from '../services/api';
import { geomToPolygon, areaSqMeters } from '../lib/geo';
import { T, Card, Pill, Badge, SectionLabel, Button } from '../components/ds';
import { Input, Select } from '../components/ds';
import { ErrorState, LoadingState, EmptyState } from '../components/StateViews';
import { useLocation } from 'react-router-dom';

// خرائط الأساس (نفس روابط FieldIndicatorMap / AddFieldWithMap).
const BASEMAP_SAT = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

// نوع المنتج → الوحدة الافتراضيّة (يدويّ: المستخدِم قد يغيّرها).
const DEFAULT_UNIT: Record<'seed' | 'fertility', string> = {
  seed: 'seeds/m2',
  fertility: 'kg/ha',
};

// منطقة في المُنشئ (محلّيّة): هندسة GeoJSON مرسومة + معدّل + وحدة + مساحة محسوبة.
interface DraftZone {
  id: number;             // L.stamp(layer) — مفتاح ثابت
  geometry: GeoJSONNS.Geometry;
  rate: string;           // إدخال نصّيّ (يُحوَّل عند الحفظ)
  unit: string;
  areaHa: number;         // محسوبة من turf (عرض فقط)
}

// مُعرّف عميل بسيط للوصفة (idempotency) — وقت + عشوائيّ، بلا اعتماديّة.
function makeId(): string {
  return `rx_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

// تنزيل نصّ كملفّ عبر Blob/URL (بلا اعتماديّة تصدير ثقيلة).
function downloadText(filename: string, mime: string, text: string): void {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// وصفة محفوظة → FeatureCollection (كلّ منطقة Feature بخصائص rate/unit). حقيقيّ.
function prescriptionToGeoJSON(rx: SavedPrescription): string {
  const fc: GeoJSONNS.FeatureCollection = {
    type: 'FeatureCollection',
    features: (rx.zones || []).map((z, i) => ({
      type: 'Feature',
      geometry: (z.geometry ?? null) as GeoJSONNS.Geometry,
      properties: {
        prescription: rx.name,
        product_type: rx.product_type,
        zone_index: i,
        rate: z.rate,
        unit: z.unit,
      },
    })),
  };
  return JSON.stringify(fc, null, 2);
}

// وصفة محفوظة → CSV (سطر لكلّ منطقة). الهندسة تُسلسَل JSON في عمود واحد (CSV-safe).
function prescriptionToCSV(rx: SavedPrescription): string {
  const head = 'zone_index,rate,unit,product_type,geometry_geojson';
  const rows = (rx.zones || []).map((z, i) => {
    const geom = JSON.stringify(z.geometry ?? null).replace(/"/g, '""');
    return `${i},${z.rate},${z.unit},${rx.product_type},"${geom}"`;
  });
  return [head, ...rows].join('\n');
}

export default function PrescriptionBuilderPage() {
  const location = useLocation();
  const routeFieldId = ((location.state as { fieldId?: string } | null)?.fieldId) ?? null;
  const {
    fieldId, field, options, isLoading: fieldsLoading, isError: fieldsError, setFieldId,
  } = useSelectedField({ routeFieldId });

  // حدود الحقل المُختار (مضلّع Leaflet) — من هندسة خيار الحقل.
  const polygon = useMemo(
    () => (field ? geomToPolygon(field.geometry) : undefined),
    [field],
  );

  // مناطق المسوّدة (يرسمها المستخدِم) + بياناتها — مصدر الحقيقة قبل الحفظ.
  const [fg, setFg] = useState<L.FeatureGroup | null>(null);
  const [zones, setZones] = useState<DraftZone[]>([]);
  const [name, setName] = useState('');
  const [productType, setProductType] = useState<'seed' | 'fertility'>('seed');
  const [saveError, setSaveError] = useState<string>('');

  // الوصفات المحفوظة + التصدير المُختار.
  const listQ = useFieldPrescriptions(fieldId, !!fieldId);
  const createM = useCreatePrescription(fieldId);
  const [selectedRxId, setSelectedRxId] = useState<string>('');

  // أعِد بناء المناطق من طبقات الرسم الحاليّة (created/edited/deleted) — turf للمساحة.
  const recompute = useCallback((group: L.FeatureGroup | null) => {
    if (!group) { setZones([]); return; }
    setZones((prev) => {
      const next: DraftZone[] = [];
      group.eachLayer((layer) => {
        const id = L.stamp(layer);
        const toGeoJSON = (layer as { toGeoJSON?: () => GeoJSONNS.Feature }).toGeoJSON;
        let gj: GeoJSONNS.Feature | null;
        try { gj = toGeoJSON?.() ?? null; } catch { gj = null; }
        const geom = gj?.geometry;
        if (!geom || (geom.type !== 'Polygon' && geom.type !== 'MultiPolygon')) return;
        const existing = prev.find((z) => z.id === id);
        next.push({
          id,
          geometry: geom,
          rate: existing?.rate ?? '',
          unit: existing?.unit ?? DEFAULT_UNIT[productType],
          areaHa: areaSqMeters(gj) / 10000,
        });
      });
      return next;
    });
  }, [productType]);

  const handleDrawn = useCallback(() => recompute(fg), [fg, recompute]);

  const setZoneRate = (id: number, rate: string) =>
    setZones((zs) => zs.map((z) => (z.id === id ? { ...z, rate } : z)));
  const setZoneUnit = (id: number, unit: string) =>
    setZones((zs) => zs.map((z) => (z.id === id ? { ...z, unit } : z)));

  const clearDraft = () => {
    if (fg) fg.clearLayers();
    setZones([]);
    setName('');
    setSaveError('');
  };

  // التحقّق قبل الحفظ: اسم + منطقة واحدة على الأقلّ بمعدّل رقميّ صالح.
  const ratesValid = zones.length > 0 && zones.every((z) => z.rate.trim() !== '' && Number.isFinite(Number(z.rate)));
  const canSave = !!fieldId && name.trim() !== '' && ratesValid && !createM.isPending;

  const handleSave = () => {
    setSaveError('');
    const payloadZones: SavedPrescriptionZone[] = zones.map((z) => ({
      geometry: z.geometry,
      rate: Number(z.rate),
      unit: z.unit.trim() || DEFAULT_UNIT[productType],
    }));
    createM.mutate(
      { prescription_id: makeId(), name: name.trim(), product_type: productType, zones: payloadZones },
      {
        onSuccess: () => clearDraft(),
        onError: (e) => {
          const status = asApiError(e).response?.status;
          setSaveError(
            status === 503 ? 'تعذّر الحفظ — قاعدة البيانات غير متاحة (503).'
            : status === 403 ? 'لا تملك صلاحيّة حفظ وصفة لهذا الحقل (403).'
            : status === 404 ? 'الحقل غير موجود ضمن مستأجِرك (404).'
            : 'تعذّر حفظ الوصفة — حاول لاحقاً.',
          );
        },
      },
    );
  };

  const saved = listQ.data?.prescriptions ?? [];
  const selectedRx = saved.find((r) => r.prescription_id === selectedRxId) ?? saved[0];

  // ── تصدير Shapefile (خادميّ، للمُتحكِّمات الزراعيّة — CultiWise) ──
  const [shpBusy, setShpBusy] = useState(false);
  const [shpError, setShpError] = useState<string | null>(null);
  async function exportShapefile(): Promise<void> {
    if (!selectedRx) return;
    setShpBusy(true);
    setShpError(null);
    try {
      const blob = await exportPrescriptionShapefile(selectedRx.field_id, selectedRx.prescription_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${selectedRx.name || 'prescription'}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      const detail = asApiError(e)?.response?.data?.detail;
      setShpError(typeof detail === 'string' ? detail : 'تعذّر تصدير Shapefile');
    } finally {
      setShpBusy(false);
    }
  }

  // ── حالات اختيار الحقل ──
  if (fieldsLoading) return <LoadingState message="جارٍ تحميل الحقول…" />;
  if (fieldsError) return <ErrorState title="تعذّر تحميل الحقول." />;

  const center: [number, number] = polygon && polygon.length ? polygon[0] : [15.35, 44.2];

  return (
    <div dir="rtl" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* الرأس + شارة النضج */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <SlidersHorizontal style={{ width: 20, height: 20, color: T.green }} />
        <h1 style={{ fontSize: 20, fontWeight: 900, color: T.ink, margin: 0 }}>
          منشئ وصفات المعدّل المتغيّر
        </h1>
        <Badge tone="warn">alpha</Badge>
        <Pill tone="neutral">يدويّ — أنت ترسم المناطق وتضبط المعدّلات</Pill>
      </div>

      {/* منتقي الحقل */}
      <Card>
        <SectionLabel>الحقل</SectionLabel>
        {options.length === 0 ? (
          <EmptyState title="لا حقول بعد — أنشئ حقلاً أوّلاً." />
        ) : (
          <Select<string>
            value={fieldId}
            onChange={(v) => { setFieldId(v); clearDraft(); setSelectedRxId(''); }}
            options={options.map((o) => ({
              value: o.id,
              label: `${o.name}${geomToPolygon(o.geometry) ? '' : ' (بلا حدود)'}`,
            }))}
            placeholder="اختر حقلاً"
          />
        )}
      </Card>

      {fieldId && (
        <>
          {/* الخريطة + أداة رسم المناطق */}
          <Card>
            <SectionLabel>
              ارسم مناطق الإدارة على حدّ الحقل (مضلّع لكلّ منطقة)
            </SectionLabel>
            {!polygon && (
              <div style={{ marginBottom: 8 }}>
                <Pill tone="warn">
                  <MapPin style={{ width: 12, height: 12 }} /> هذا الحقل بلا حدود مُخزَّنة — ارسم المناطق فوق الخريطة
                </Pill>
              </div>
            )}
            <div style={{ borderRadius: 12, overflow: 'hidden', border: `1px solid ${T.line}` }}>
              <MapContainer center={center} zoom={15} style={{ height: 420, width: '100%' }} scrollWheelZoom>
                <TileLayer
                  url={BASEMAP_SAT}
                  attribution="Esri World Imagery"
                />
                {polygon && polygon.length >= 3 && (
                  <Polygon positions={polygon} pathOptions={{ color: '#5cbf6e', weight: 2, fill: false }} />
                )}
                <FeatureGroup ref={(r: L.FeatureGroup | null) => setFg(r)}>
                  <DrawControl
                    position="topright"
                    onCreated={handleDrawn}
                    onEdited={handleDrawn}
                    onDeleted={handleDrawn}
                    draw={{
                      // مناطق فقط: مضلّع. showArea:false (نحسب المساحة من turf أدناه).
                      polygon: { allowIntersection: false, showArea: false, shapeOptions: { color: '#38bdf8' } },
                      polyline: false,
                      rectangle: { shapeOptions: { color: '#38bdf8' } },
                      circle: false,
                      marker: false,
                      circlemarker: false,
                    }}
                    edit={{ edit: {}, remove: {} }}
                  />
                </FeatureGroup>
              </MapContainer>
            </div>
          </Card>

          {/* المناطق المرسومة + معدّلاتها */}
          <Card>
            <SectionLabel action={zones.length > 0 ? (
              <button
                type="button"
                onClick={clearDraft}
                style={{ fontSize: 12, color: '#fca5a5', background: 'transparent', border: 'none', cursor: 'pointer' }}
              >
                <Trash2 style={{ width: 13, height: 13, verticalAlign: 'middle' }} /> مسح الكلّ
              </button>
            ) : undefined}>
              المناطق ({zones.length}) ومعدّلاتها
            </SectionLabel>

            {zones.length === 0 ? (
              <EmptyState title="لم تُرسم مناطق بعد — استخدم أداة الرسم (المضلّع) أعلى الخريطة." />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {zones.map((z, i) => (
                  <div
                    key={z.id}
                    style={{
                      display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10,
                      alignItems: 'end', padding: 10, borderRadius: 10,
                      background: T.card2, border: `1px solid ${T.line}`,
                    }}
                  >
                    <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Pill tone="neutral">منطقة {i + 1}</Pill>
                      <span style={{ fontSize: 12, color: T.muted }}>
                        المساحة ≈ {z.areaHa.toFixed(2)} هكتار
                      </span>
                    </div>
                    <Input
                      label="المعدّل"
                      type="number"
                      inputMode="decimal"
                      value={z.rate}
                      onChange={(v) => setZoneRate(z.id, v)}
                      placeholder={productType === 'seed' ? 'مثال 450' : 'مثال 120'}
                    />
                    <Input
                      label="الوحدة"
                      value={z.unit}
                      onChange={(v) => setZoneUnit(z.id, v)}
                      placeholder={DEFAULT_UNIT[productType]}
                    />
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* بيانات الوصفة + الحفظ */}
          <Card>
            <SectionLabel>تفاصيل الوصفة</SectionLabel>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Input
                label="اسم الوصفة"
                value={name}
                onChange={setName}
                placeholder="مثال: بذار قمح ٢٠٢٦"
                required
              />
              <Select<'seed' | 'fertility'>
                label="نوع المنتج"
                value={productType}
                onChange={(v) => {
                  setProductType(v);
                  // حدِّث وحدات المناطق الفارغة للوحدة الافتراضيّة للنوع الجديد.
                  setZones((zs) => zs.map((z) => (z.rate.trim() === '' ? { ...z, unit: DEFAULT_UNIT[v] } : z)));
                }}
                options={[
                  { value: 'seed', label: 'بذار (seed)' },
                  { value: 'fertility', label: 'تسميد (fertility)' },
                ]}
              />
            </div>
            {saveError && (
              <div style={{ marginTop: 10 }}>
                <Pill tone="warn">{saveError}</Pill>
              </div>
            )}
            {createM.isSuccess && !saveError && (
              <div style={{ marginTop: 10 }}>
                <Pill tone="ok">حُفِظت الوصفة.</Pill>
              </div>
            )}
            <div style={{ marginTop: 12, display: 'flex', gap: 10 }}>
              <Button onClick={handleSave} disabled={!canSave} full={false}>
                <Save style={{ width: 14, height: 14, verticalAlign: 'middle' }} />{' '}
                {createM.isPending ? 'جارٍ الحفظ…' : 'حفظ الوصفة'}
              </Button>
              {!ratesValid && zones.length > 0 && (
                <span style={{ fontSize: 12, color: T.muted, alignSelf: 'center' }}>
                  أدخِل معدّلاً رقميّاً صالحاً لكلّ منطقة
                </span>
              )}
              {zones.length === 0 && (
                <span style={{ fontSize: 12, color: T.muted, alignSelf: 'center' }}>
                  <Plus style={{ width: 12, height: 12, verticalAlign: 'middle' }} /> ارسم منطقة واحدة على الأقلّ
                </span>
              )}
            </div>
          </Card>

          {/* الوصفات المحفوظة + التصدير */}
          <Card>
            <SectionLabel>الوصفات المحفوظة</SectionLabel>
            {listQ.isLoading ? (
              <LoadingState message="جارٍ تحميل الوصفات…" />
            ) : listQ.isError ? (
              <ErrorState
                title={
                  asApiError(listQ.error).response?.status === 503
                    ? 'خدمة الوصفات غير متاحة (503).'
                    : 'تعذّر تحميل الوصفات.'
                }
              />
            ) : saved.length === 0 ? (
              <EmptyState title={listQ.data?.note_ar || 'لا وصفات محفوظة لهذا الحقل بعد.'} />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <Select<string>
                  label="اختر وصفة للتصدير"
                  value={selectedRx?.prescription_id ?? ''}
                  onChange={setSelectedRxId}
                  options={saved.map((r) => ({
                    value: r.prescription_id,
                    label: `${r.name} · ${r.product_type} · ${r.zones?.length ?? 0} منطقة`,
                  }))}
                />
                {selectedRx && (
                  <>
                    <div style={{ fontSize: 12, color: T.muted }}>
                      {selectedRx.zones?.length ?? 0} منطقة · {selectedRx.product_type}
                      {selectedRx.created_at ? ` · ${selectedRx.created_at.slice(0, 10)}` : ''}
                    </div>
                    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                      <Button
                        full={false}
                        tone="gold"
                        onClick={() =>
                          downloadText(
                            `${selectedRx.name || 'prescription'}.geojson`,
                            'application/geo+json',
                            prescriptionToGeoJSON(selectedRx),
                          )
                        }
                      >
                        <Download style={{ width: 14, height: 14, verticalAlign: 'middle' }} /> تصدير GeoJSON
                      </Button>
                      <Button
                        full={false}
                        tone="gold"
                        onClick={() =>
                          downloadText(
                            `${selectedRx.name || 'prescription'}.csv`,
                            'text/csv',
                            prescriptionToCSV(selectedRx),
                          )
                        }
                      >
                        <Download style={{ width: 14, height: 14, verticalAlign: 'middle' }} /> تصدير CSV
                      </Button>
                      <Button full={false} tone="gold" disabled={shpBusy} onClick={exportShapefile}>
                        <Download style={{ width: 14, height: 14, verticalAlign: 'middle' }} />{' '}
                        {shpBusy ? 'جارٍ التصدير…' : 'تصدير Shapefile'}
                      </Button>
                    </div>
                    {shpError && <Pill tone="warn">{shpError}</Pill>}
                    <Pill tone="neutral">
                      Shapefile جاهز للمُتحكِّمات (.shp/.shx/.dbf/.prj). تصدير ISOXML مؤجّل — TODO موثَّق (لا يُنتَج بعد).
                    </Pill>
                  </>
                )}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
