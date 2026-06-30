// ═══════════════════════════════════════════════════════════════
// SAHOOL Weather Graticule
// Subtle translucent lat/lon coordinate grid overlay (meteoblue-inspired).
// Adaptive integer-degree spacing by zoom, thin low-opacity lines + faint
// labels, drawn across the visible world bounds. Glass aesthetic, lightweight.
// ═══════════════════════════════════════════════════════════════
import L from 'leaflet';

// تباعد الشبكة بالدرجات حسب مستوى التكبير: شبكة أخشن عند الإبعاد، أدقّ عند التقريب.
// يبقى عدد الخطوط معقولاً (شبكة خفيفة) تفادياً لإثقال العرض.
function graticuleStepDegrees(zoom: number): number {
  if (zoom <= 2) return 30;
  if (zoom <= 3) return 20;
  if (zoom <= 4) return 10;
  if (zoom <= 5) return 5;
  if (zoom <= 7) return 2;
  if (zoom <= 9) return 1;
  if (zoom <= 11) return 0.5;
  return 0.25;
}

function formatDegrees(value: number): string {
  // عرض موجز يتجنّب أصفاراً عشريّة زائدة (مثلاً 30 بدل 30.00، و0.5 يبقى 0.5).
  const rounded = Math.round(value * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toString();
}

function snapDown(value: number, step: number): number {
  return Math.floor(value / step) * step;
}

const LINE_STYLE: L.PolylineOptions = {
  color: '#e2e8f0',
  weight: 0.5,
  opacity: 0.22,
  interactive: false,
  // خطوط متقطّعة رفيعة لإيحاء زجاجيّ خفيف يظهر الخريطة خلفه.
  dashArray: '2,6',
};

// يرسم/يعيد رسم خطوط الطول والعرض داخل الحدود المرئيّة مع تباعد متكيّف.
function redraw(map: L.Map, group: L.LayerGroup): void {
  group.clearLayers();
  const bounds = map.getBounds();
  const step = graticuleStepDegrees(map.getZoom());

  const south = Math.max(-85, bounds.getSouth());
  const north = Math.min(85, bounds.getNorth());
  const west = bounds.getWest();
  const east = bounds.getEast();
  if (north <= south || east <= west) return;

  // حدّ أعلى لعدد الخطوط حماية للأداء على الأجهزة الضعيفة.
  const MAX_LINES = 80;

  // خطوط العرض (أفقيّة): من الجنوب إلى الشمال على فواصل صحيحة من الدرجات.
  let drawn = 0;
  for (let lat = snapDown(south, step); lat <= north && drawn < MAX_LINES; lat += step) {
    if (lat < south) continue;
    group.addLayer(L.polyline([[lat, west], [lat, east]], LINE_STYLE));
    group.addLayer(
      L.marker([lat, west], {
        interactive: false,
        keyboard: false,
        icon: L.divIcon({
          className: 'sahool-weather-graticule-label',
          html: `<span>${formatDegrees(lat)}°</span>`,
          iconSize: [0, 0],
        }),
      }),
    );
    drawn += 1;
  }

  // خطوط الطول (عموديّة): من الغرب إلى الشرق على الفواصل نفسها.
  drawn = 0;
  for (let lon = snapDown(west, step); lon <= east && drawn < MAX_LINES; lon += step) {
    if (lon < west) continue;
    group.addLayer(L.polyline([[south, lon], [north, lon]], LINE_STYLE));
    group.addLayer(
      L.marker([south, lon], {
        interactive: false,
        keyboard: false,
        icon: L.divIcon({
          className: 'sahool-weather-graticule-label',
          html: `<span>${formatDegrees(lon)}°</span>`,
          iconSize: [0, 0],
        }),
      }),
    );
    drawn += 1;
  }
}

let stylesInjected = false;
function ensureStyles(): void {
  if (stylesInjected || typeof document === 'undefined') return;
  const style = document.createElement('style');
  style.dataset.sahoolGraticule = '1';
  // تسميات شبه شفّافة باهتة تطابق الجماليّة الزجاجيّة دون حجب الخريطة.
  style.textContent = `
    .sahool-weather-graticule-label{pointer-events:none}
    .sahool-weather-graticule-label span{display:inline-block;transform:translate(4px,-50%);color:rgba(226,232,240,.55);font:10px/1 system-ui,-apple-system,Segoe UI,sans-serif;text-shadow:0 1px 2px rgba(2,6,23,.7);white-space:nowrap}
  `;
  document.head.appendChild(style);
  stylesInjected = true;
}

/**
 * يُنشئ مجموعة طبقات الشبكة فارغة (بدون ربط بالخريطة). متاحة للاستهلاك المباشر
 * كما تطلب الواجهة `createGraticuleLayer(): L.LayerGroup`.
 */
export function createGraticuleLayer(): L.LayerGroup {
  return L.layerGroup([], { pane: 'overlayPane' });
}

/**
 * يُنشئ طبقة الشبكة الإحداثيّة (graticule) ويربطها بالخريطة مع دورة حياة نظيفة.
 * تُعيد الرسم عند التحريك/التكبير، وتُزال بالكامل عند `map.removeLayer(group)`.
 */
export function addGraticule(map: L.Map): L.LayerGroup {
  ensureStyles();
  const group = createGraticuleLayer();
  group.addTo(map);

  const onChange = () => redraw(map, group);
  map.on('moveend zoomend', onChange);
  redraw(map, group);

  // إزالة مستمعي الأحداث تلقائيّاً عند فصل الطبقة عن الخريطة.
  group.on('remove', () => {
    map.off('moveend zoomend', onChange);
  });

  return group;
}
