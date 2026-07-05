// ═══════════════════════════════════════════════════════════════
// SAHOOL — مركز الخرائط الموحّد (Field Map Center) · شاشة دمج ثانية
// ───────────────────────────────────────────────────────────────
// تصهر «الأقمار الصناعيّة/المؤشّرات المكانيّة» (FieldView) مع نمط طبقات
// «Operations Center · Analyze» في كابينة واحدة: خريطة Leaflet حقيقيّة
// ببلاطات مؤشّر من raster-service، مبدّل طبقات (NDVI/NDMI/الملوحة)، مفتاح
// ألوان مطابق للطبقة، ووضع مقارنة جنباً لجنب (SideBySide) لطبقتين حقيقيّتين.
// يستهلك لبنات الدمج: LayerSwitcher · ColormapLegend · SideBySide ·
// MachineMarker. تجسيد UI_DESIGN_SPEC_UNIFIED.md §3 (الخريطة متعدّدة الطبقات).
//
// صدق البيانات: كلّ طبقة بلاطات حقيقيّة من raster-service فوق حدود الحقل
// الحقيقيّة (geometry/lat/lon من useFields). لا مواقع آليّات ملفّقة —
// المعدّات بلا إحداثيّات (فجوة موثّقة ⛔)، والأجهزة (useDevices) تُعرَض
// كمؤشّرات حالة (MachineMarker) منسوبة للحقل لا كإحداثيّات مزعومة. الحالات
// (تحميل/فراغ/خطأ) صريحة عبر StateViews الضمنيّة. شاشة قراءة فقط (معاينة دمج).
// ═══════════════════════════════════════════════════════════════
import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Layers, Satellite, Droplets, FlaskConical, Cpu, Columns2, Square } from 'lucide-react';
import { useDevices } from '../hooks/useApi';
import { useFieldOptions } from '../hooks/useFieldOptions';
import { useFieldContextStore } from '../hooks/useFieldContext';
import { fetchFieldImageryAvailableDates, type FieldImageryDateOption } from '../services/api';
import { geomToPolygon } from '../lib/geo';
import FieldIndicatorMap from '../components/FieldIndicatorMap';
import {
  T, Card, Pill, Badge, SectionLabel, Row,
  LayerSwitcher, ColormapLegend, SideBySide, MachineMarker, FieldCabin,
} from '../components/ds';
import type { CmapId } from '../components/ds';
import { layersOfKind } from '../lib/layerRegistry';

// ── المؤشّرات (طبقات) — مُشتقّة من سجلّ الطبقات (Layer Registry) ──
// قائمة المؤشّرات لم تعد ثابتة محلّيّاً: تُستمدّ من layersOfKind('index') في
// lib/layerRegistry.ts (المصدر الوحيد). من السجلّ نأخذ: المعرّف (id = ما يقبله
// raster-service) ولوحة الألوان (colormap → cmap لمفتاح DS). أمّا تفاصيل العرض
// التي لا يحملها السجلّ (التسمية المختصرة، الأيقونة، حدّا المفتاح low/high،
// التلميح) فتبقى هنا مفهرسةً بالمعرّف — فيظلّ الظاهر (الطبقات/التسميات/اللوحات)
// مطابقاً تماماً لما كان، مع تحويل اختيار الطبقات إلى بيانات.
type LayerId = 'ndvi' | 'ndmi' | 'salinity';

// عرض الطبقة (ما لا يحمله السجلّ) — مفهرس بمعرّف الطبقة.
const LAYER_PRESENTATION: Record<LayerId, {
  label: string; icon: ReactNode; low: string; high: string; hint: string;
}> = {
  ndvi: { label: 'NDVI', icon: <Satellite style={{ width: 13, height: 13 }} />, low: 'إجهاد', high: 'كثيف', hint: 'صحّة الغطاء النباتيّ' },
  ndmi: { label: 'NDMI', icon: <Droplets style={{ width: 13, height: 13 }} />, low: 'جافّ', high: 'رطب', hint: 'رطوبة المحتوى' },
  salinity: { label: 'الملوحة', icon: <FlaskConical style={{ width: 13, height: 13 }} />, low: 'منخفضة', high: 'مرتفعة', hint: 'مؤشّر الملوحة' },
};
const isSupportedLayerId = (id: string): id is LayerId => id in LAYER_PRESENTATION;

// المؤشّرات المعروضة مُشتقّة من السجلّ: نمرّ على طبقات kind:'index' ونُبقي فقط
// ما تدعمه هذه الشاشة (عرض + لوحة DS موجودة) — فلا تُسقَط/تُضاف طبقة بصمت.
// النتيجة (المعرّفات + التسميات + اللوحات) مطابقة للقائمة الثابتة السابقة.
const LAYERS: {
  id: LayerId; label: string; icon: ReactNode; cmap: CmapId;
  low: string; high: string; hint: string;
}[] = layersOfKind('index')
  .filter((l) => isSupportedLayerId(l.id) && l.colormap != null)
  .map((l) => {
    const id = l.id as LayerId;
    const p = LAYER_PRESENTATION[id];
    return { id, label: p.label, icon: p.icon, cmap: l.colormap as CmapId, low: p.low, high: p.high, hint: p.hint };
  });
const layerOf = (id: LayerId) => LAYERS.find((l) => l.id === id) ?? LAYERS[0];
// خيارات LayerSwitcher مشتقّة مرّة واحدة (LAYERS ثابتة) — هويّة مصفوفة مستقرّة.
const LAYER_OPTS = LAYERS.map((l) => ({ id: l.id, label: l.label, icon: l.icon }));

interface MapField { id: string; name: string; lat: number | null; lon: number | null; geometry: unknown }

// نغمة/حالة مؤشّر الجهاز — online→يعمل، غير ذلك→غير متّصل (alert إن غير متّصل).
function deviceMarkerStatus(online?: boolean): 'working' | 'offline' {
  return online ? 'working' : 'offline';
}

// لوحة خريطة واحدة (خريطة حقيقيّة + مفتاح ألوان فوقها). تُعاد استخدامها مفردةً
// وداخل SideBySide. height قابل للضبط (مفرد أطول، مقارنة أقصر).
function MapPanel({
  field, polygon, fallbackBounds, layerId, height, date,
}: {
  field: MapField;
  polygon?: [number, number][];
  fallbackBounds?: [number, number, number, number];
  layerId: LayerId;
  height: number;
  date: string;
}) {
  const ly = layerOf(layerId);
  return (
    <div style={{ position: 'relative' }}>
      <FieldIndicatorMap
        // المفتاح على الحقل فقط: FieldIndicatorMap يبدّل طبقة بلاطات المؤشّر
        // داخليّاً عند تغيّر index (مفتاحها fieldId-index-date)، فلا داعي لهدم
        // الخريطة/الأساس بالكامل عند تبديل الطبقة (يطابق نمط SatellitePage).
        key={field.id}
        fieldId={field.id}
        index={layerId}
        date={date}
        fieldPolygon={polygon}
        fallbackBounds={fallbackBounds}
        basemap="satellite"
        height={height}
      />
      <div style={{ position: 'absolute', insetInlineStart: 8, bottom: 8, zIndex: 500, pointerEvents: 'none' }}>
        <ColormapLegend cmap={ly.cmap} title={ly.label} lowLabel={ly.low} highLabel={ly.high} />
      </div>
    </div>
  );
}

export default function FieldMapCenter() {
  const fieldsQ = useFieldOptions();
  const devicesQ = useDevices();

  const fields = fieldsQ.options;

  // «الحقل النشط» المشترك (متجر useFieldContext) — يتبع المستخدم عبر الشاشات.
  // نقرأ الاختيار مباشرةً (لا useSelectedField) كي نُبقي الافتراض الخاصّ بالخريطة:
  // أوّل حقل ذي هندسة (فتُظهر مضلّعاً لا مستطيل حدود) بدل أوّل حقل مطلقاً.
  const selectedFieldId = useFieldContextStore((s) => s.selectedFieldId);
  const setFieldId = useFieldContextStore((s) => s.setSelectedField);
  const fieldId = selectedFieldId && fields.some((f) => f.id === selectedFieldId) ? selectedFieldId : '';
  const [compare, setCompare] = useState(false);
  const [leftLayer, setLeftLayer] = useState<LayerId>('ndvi');
  const [rightLayer, setRightLayer] = useState<LayerId>('ndmi');
  const [imageryDates, setImageryDates] = useState<FieldImageryDateOption[]>([]);
  const [selectedDate, setSelectedDate] = useState('latest');

  // لا اختيار صالح بعد (أوّل تحميل/حُذف المُختار) ⇒ ثبّت أوّل حقل ذي هندسة (يفضَّل)
  // في المتجر المشترك، فيراه باقي الشاشات.
  useEffect(() => {
    if (fieldId || !fields.length) return;
    const withGeom = fields.find((f) => geomToPolygon(f.geometry)) ?? fields[0];
    setFieldId(withGeom.id);
  }, [fields, fieldId, setFieldId]);

  const field = fields.find((f) => f.id === fieldId) ?? fields[0];
  const polygon = field ? geomToPolygon(field.geometry) : undefined;
  const fallbackBounds: [number, number, number, number] | undefined =
    field && field.lat != null && field.lon != null
      ? [field.lon - 0.01, field.lat - 0.01, field.lon + 0.01, field.lat + 0.01]
      : undefined;

  // أجهزة الحقل المختار (نسبة لـfield_id) — مؤشّرات حالة لا إحداثيّات مزعومة.
  const allDevices = Array.isArray(devicesQ.data) ? devicesQ.data : [];
  const fieldDevices = field ? allDevices.filter((d) => d.field_id === field.id) : [];
  const onlineDevices = fieldDevices.filter((d) => d.online).length;

  // تاريخ الصورة المختار: لا نثبت مركز الخرائط على latest إذا كانت raster-service
  // تعرف تواريخ COG جاهزة للحقل. هذا يغلق drift بين شاشات MapHub/Satellite ومركز الخرائط.
  useEffect(() => {
    if (!field?.id) { setImageryDates([]); setSelectedDate('latest'); return; }
    let cancelled = false;
    // v11-F8: مرّر المؤشّر المعروض (leftLayer) كي لا تُخلَط تواريخ مؤشّرات أخرى في المُنتقي.
    fetchFieldImageryAvailableDates(field.id, leftLayer)
      .then((dates) => {
        if (cancelled) return;
        const ready = dates.filter((d) => d.date && d.has_cog !== false);
        setImageryDates(ready);
        setSelectedDate((prev) => (prev !== 'latest' && ready.some((d) => d.date === prev)) ? prev : (ready[0]?.date ?? 'latest'));
      })
      .catch(() => {
        if (!cancelled) { setImageryDates([]); setSelectedDate('latest'); }
      });
    return () => { cancelled = true; };
  }, [field?.id, leftLayer]);

  return (
    <FieldCabin
      eyebrow="مركز الخرائط"
      title="طبقات الحقل"
      subtitle="بلاطات مؤشّر حقيقيّة من خدمة الراستر — فوق حدود الحقل"
      headerRight={
        <Pill tone="info" icon={<Layers style={{ width: 12, height: 12 }} />}>
          {LAYERS.length} طبقات
        </Pill>
      }
      note={
        <>
          مركز الخرائط الموحّد — بلاطات <code>/raster</code> الحقيقيّة فوق حدود <code>/fields</code>.
          مؤشّرات الأجهزة من <code>/devices</code> (حالة اتّصال، لا إحداثيّات). لا مواقع معدّات
          ملفّقة (فجوة موثّقة). الحالات صادقة.
        </>
      }
    >
      {/* ── اختيار الحقل + تبديل وضع المقارنة ── */}
          <Card pad={14} style={{ marginBottom: 10 }}>
            <SectionLabel
              action={<Badge tone={fieldsQ.isLoading ? 'neutral' : fieldsQ.isError ? 'danger' : 'ok'}>
                {fieldsQ.isLoading ? 'تحميل…' : fieldsQ.isError ? 'خطأ' : `${fields.length} حقل`}
              </Badge>}
            >
              الحقل
            </SectionLabel>

            {fieldsQ.isLoading ? (
              <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل الحقول…</div>
            ) : fieldsQ.isError ? (
              <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل الحقول.</div>
            ) : fields.length === 0 ? (
              <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا حقول مُسجّلة.</div>
            ) : (
              <>
                <select
                  value={field?.id ?? ''}
                  onChange={(e) => setFieldId(e.target.value)}
                  style={{
                    width: '100%', padding: '9px 10px', borderRadius: 10,
                    border: `1px solid ${T.line}`, background: T.card, color: T.ink,
                    fontSize: 14, fontWeight: 600, marginBottom: 10,
                  }}
                >
                  {fields.map((f) => (
                    <option key={f.id} value={f.id}>{f.name}{geomToPolygon(f.geometry) ? '' : ' (بلا حدود)'}</option>
                  ))}
                </select>
                <div style={{ marginBottom: 10 }}>
                  <span style={{ display: 'block', fontSize: 12, color: T.muted, marginBottom: 4 }}>تاريخ الصورة</span>
                  <select
                    value={selectedDate}
                    onChange={(e) => setSelectedDate(e.target.value)}
                    style={{
                      width: '100%', padding: '8px 10px', borderRadius: 10,
                      border: `1px solid ${T.line}`, background: T.card2, color: T.ink,
                      fontSize: 13, fontWeight: 600,
                    }}
                  >
                    <option value="latest">الأحدث</option>
                    {imageryDates.map((d) => (
                      <option key={d.date} value={d.date}>{d.date}{d.cloud_pct != null ? ` · غيوم ${Math.round(d.cloud_pct)}%` : ''}</option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center justify-between">
                  <span style={{ fontSize: 12, color: T.muted }}>وضع العرض</span>
                  <button
                    type="button"
                    onClick={() => setCompare((v) => !v)}
                    className="inline-flex items-center gap-1"
                    style={{
                      padding: '6px 12px', borderRadius: 999, border: 'none', cursor: 'pointer',
                      fontSize: 12, fontWeight: 700,
                      background: compare ? T.green : T.card2, color: compare ? '#fff' : T.ink,
                    }}
                  >
                    {compare ? <Columns2 style={{ width: 13, height: 13 }} /> : <Square style={{ width: 13, height: 13 }} />}
                    {compare ? 'مقارنة جنباً لجنب' : 'طبقة واحدة'}
                  </button>
                </div>
              </>
            )}
          </Card>

          {/* ── الخريطة / الخرائط ── */}
          {field && (polygon || fallbackBounds) ? (
            compare ? (
              <Card pad={12} style={{ marginBottom: 10 }}>
                <SectionLabel>مقارنة الطبقات</SectionLabel>
                <SideBySide
                  leftLabel={
                    <LayerSwitcher layers={LAYER_OPTS} active={leftLayer} onChange={setLeftLayer} />
                  }
                  rightLabel={
                    <LayerSwitcher layers={LAYER_OPTS} active={rightLayer} onChange={setRightLayer} />
                  }
                  left={<MapPanel field={field} polygon={polygon} fallbackBounds={fallbackBounds} layerId={leftLayer} height={220} date={selectedDate} />}
                  right={<MapPanel field={field} polygon={polygon} fallbackBounds={fallbackBounds} layerId={rightLayer} height={220} date={selectedDate} />}
                />
                <div style={{ fontSize: 11, color: T.muted, marginTop: 8 }}>
                  طبقتان حقيقيّتان لنفس الحقل والتاريخ المختار — للموازنة البصريّة.
                </div>
              </Card>
            ) : (
              <Card pad={12} style={{ marginBottom: 10 }}>
                <div style={{ marginBottom: 10 }}>
                  <LayerSwitcher layers={LAYER_OPTS} active={leftLayer} onChange={setLeftLayer} />
                </div>
                <MapPanel field={field} polygon={polygon} fallbackBounds={fallbackBounds} layerId={leftLayer} height={320} date={selectedDate} />
                <div style={{ fontSize: 11, color: T.muted, marginTop: 8 }}>
                  {layerOf(leftLayer).hint} — طبقة <b>{layerOf(leftLayer).label}</b> فوق {field.name}.
                </div>
              </Card>
            )
          ) : field ? (
            <Card pad={14} style={{ marginBottom: 10 }}>
              <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>
                لا حدود ولا إحداثيّات لهذا الحقل — تعذّر عرض الخريطة. اختر حقلاً ذا هندسة.
              </div>
            </Card>
          ) : null}

          {/* ── أجهزة الحقل (مؤشّرات حالة — لا مواقع ملفّقة) ── */}
          <Card pad={14} style={{ marginBottom: 4 }}>
            <SectionLabel
              action={<Badge tone={fieldDevices.length ? (onlineDevices ? 'ok' : 'warn') : 'neutral'}>
                {fieldDevices.length ? `${onlineDevices}/${fieldDevices.length} متّصل` : '—'}
              </Badge>}
            >
              <span className="inline-flex items-center gap-1">
                <Cpu style={{ width: 13, height: 13 }} /> أجهزة الحقل
              </span>
            </SectionLabel>
            {devicesQ.isLoading ? (
              <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل الأجهزة…</div>
            ) : devicesQ.isError ? (
              <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل الأجهزة.</div>
            ) : fieldDevices.length === 0 ? (
              <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا أجهزة منسوبة لهذا الحقل.</div>
            ) : (
              fieldDevices.map((d, i) => (
                <Row
                  key={d.device_id || i}
                  label={d.name || 'جهاز'}
                  value={<Pill tone={d.online ? 'ok' : 'neutral'}>{d.online ? 'متّصل' : 'غير متّصل'}</Pill>}
                  icon={
                    <MachineMarker
                      icon={<Cpu style={{ width: 14, height: 14, color: '#fff' }} />}
                      status={deviceMarkerStatus(d.online)}
                      alert={!d.online}
                      style={{ transform: 'scale(0.7)' }}
                    />
                  }
                />
              ))
            )}
          </Card>
    </FieldCabin>
  );
}
