// ═══════════════════════════════════════════════════════════════
// SAHOOL — MapHub Weather Engine
// Open-Meteo is the data source; SAHOOL renders GridLayer tiles, animation,
// layer controls, legend, time selector, and agronomic probe popups.
// ═══════════════════════════════════════════════════════════════
import { useMap } from 'react-leaflet';
import { useEffect, useMemo, useState } from 'react';
import L from 'leaflet';
import type { WeatherMarker } from '../OverlayMarkers';

import {
  type WeatherLayerKey,
  type WeatherTimeKey,
  type WindDensity,
  type WeatherPalette,
  WEATHER_TIMES,
} from './weatherLayerDefinitions';
import { readWeatherPreferences, writeWeatherPreferences } from './weatherPreferences';
import { createWeatherWindGridLayer } from './WeatherTileLayer';
import { createWeatherControl } from './WeatherLayerPanel';
import { registerWeatherProbePopup } from './WeatherProbePopup';
import { registerWeatherHoverReadout } from './WeatherHoverReadout';
import { addGraticule } from './WeatherGraticule';

// قصّ حاوية طبقة الطقس على حدّ الحقل (مثل مؤشّرات الأقمار المقصوصة خادميّاً): نُسقِط
// رؤوس المضلّع إلى بكسلات طبقة الخريطة (نسبةً لإزاحة الحاوية) ونضبط clip-path. يُعاد
// الحساب مع كل تحريك/تكبير. فراغ المضلّع ⇒ إزالة القصّ (سلوك العرض الكامل القديم).
function applyPolygonClip(map: L.Map, container: HTMLElement, polygon?: [number, number][]) {
  if (!polygon || polygon.length < 3) {
    container.style.clipPath = '';
    (container.style as unknown as { webkitClipPath: string }).webkitClipPath = '';
    return;
  }
  const offset = L.DomUtil.getPosition(container) ?? L.point(0, 0);
  const pts = polygon.map(([lat, lng]) => {
    const p = map.latLngToLayerPoint(L.latLng(lat, lng));
    return `${(p.x - offset.x).toFixed(1)}px ${(p.y - offset.y).toFixed(1)}px`;
  });
  const clip = `polygon(${pts.join(', ')})`;
  container.style.clipPath = clip;
  (container.style as unknown as { webkitClipPath: string }).webkitClipPath = clip;
}

export function WeatherRasterOverlay({ marker, fieldPolygon }: { marker: WeatherMarker | null; fieldPolygon?: [number, number][] }) {
  const map = useMap();
  // تفضيلات المستخدم (v27): تُقرأ من localStorage عند التركيب وتُحفَظ عند أيّ تغيير،
  // فتبقى الطبقة/الزمن/النموذج/الشفافيّة/الرياح بين الجلسات (سقوط آمن للقيم الافتراضيّة).
  const [initialPreferences] = useState(() => readWeatherPreferences());
  const [layer, setLayer] = useState<WeatherLayerKey>(initialPreferences.layer);
  const [time, setTime] = useState<WeatherTimeKey>(initialPreferences.time);
  const [model, setModel] = useState(initialPreferences.model);
  const [opacity, setOpacity] = useState(initialPreferences.opacity);
  const [showWind, setShowWind] = useState(initialPreferences.showWind);
  const [windDensity, setWindDensity] = useState<WindDensity>(initialPreferences.windDensity);
  const [panelOpen, setPanelOpen] = useState(initialPreferences.panelOpen);
  const [palette, setPalette] = useState<WeatherPalette>(initialPreferences.palette);
  // شبكة الإحداثيّات (graticule) على نمط meteoblue: خطوط طول/عرض شفّافة قابلة للتبديل.
  const [graticule, setGraticule] = useState(initialPreferences.graticule);
  // تشغيل/إيقاف العرض الزمني (شريط التمرير السفليّ على نمط meteoblue): يتقدّم عبر WEATHER_TIMES بشكل دوريّ.
  const [playing, setPlaying] = useState(false);
  const stableMarker = useMemo(() => marker, [marker]);

  useEffect(() => {
    writeWeatherPreferences({ layer, time, model, opacity, showWind, windDensity, panelOpen, palette, graticule });
  }, [layer, time, model, opacity, showWind, windDensity, panelOpen, palette, graticule]);

  // محرّك العرض الزمني: عند التشغيل يتقدّم الزمن كل 1200ms إلى المفتاح التالي ويعود للبداية بعد الأخير؛
  // يُلغى المؤقّت عند الإيقاف/التفكيك. يحترم تفضيل تقليل الحركة فلا يبدأ تلقائيّاً عند تفعيله.
  useEffect(() => {
    if (!playing) return undefined;
    if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setPlaying(false);
      return undefined;
    }
    const id = window.setInterval(() => {
      setTime((current) => {
        const idx = Math.max(0, WEATHER_TIMES.findIndex((t) => t.key === current));
        return WEATHER_TIMES[(idx + 1) % WEATHER_TIMES.length].key;
      });
    }, 1200);
    return () => window.clearInterval(id);
  }, [playing]);

  useEffect(() => {
    if (!stableMarker) return undefined;
    const grid = createWeatherWindGridLayer(stableMarker, layer, time, model, opacity, showWind, windDensity, palette);
    // حصر البلاطات ضمن مربّع الحقل المحيط: لا تُحمَّل/تُرسَم بلاطات الطقس خارج الحقل
    // (يمنع تغطية الخريطة كاملةً)؛ والقصّ بـclip-path يضبطها على شكل المضلّع بالضبط.
    if (fieldPolygon && fieldPolygon.length >= 3) {
      (grid.options as unknown as { bounds: L.LatLngBounds }).bounds = L.latLngBounds(
        fieldPolygon.map(([lat, lng]) => L.latLng(lat, lng)),
      );
    }
    grid.addTo(map);
    const container = grid.getContainer();
    container?.classList.add('sahool-weather-wind-grid-layer');
    if (container) {
      container.style.mixBlendMode = 'screen';
      container.style.pointerEvents = 'none';
      container.style.zIndex = '450';
      container.style.opacity = String(opacity);
    }
    // قصّ على حدّ الحقل + إعادة الحساب مع حركة/تكبير الخريطة (يتبع المضلّع كالأقمار).
    const reclip = () => { if (container) applyPolygonClip(map, container, fieldPolygon); };
    reclip();
    map.on('move zoom moveend zoomend viewreset', reclip);
    grid.on('load', reclip);
    return () => {
      map.off('move zoom moveend zoomend viewreset', reclip);
      grid.remove();
    };
  }, [map, stableMarker, layer, time, model, opacity, showWind, windDensity, palette, fieldPolygon]);

  useEffect(() => {
    if (!stableMarker) return undefined;
    const control = createWeatherControl(
      layer,
      stableMarker,
      time,
      model,
      opacity,
      showWind,
      windDensity,
      panelOpen,
      setLayer,
      setTime,
      setModel,
      setOpacity,
      setShowWind,
      setWindDensity,
      () => setPanelOpen((v) => !v),
      palette,
      setPalette,
      playing,
      () => setPlaying((v) => !v),
      graticule,
      setGraticule,
    ).addTo(map);
    return () => { control.remove(); };
  }, [map, stableMarker, layer, time, model, opacity, showWind, windDensity, panelOpen, palette, playing, graticule]);

  // طبقة شبكة الإحداثيّات: تُضاف عند التفعيل وتُزال بالكامل عند الإيقاف/التفكيك.
  useEffect(() => {
    if (!graticule) return undefined;
    const layerGroup = addGraticule(map);
    return () => { map.removeLayer(layerGroup); };
  }, [map, graticule]);

  useEffect(() => {
    if (!stableMarker) return undefined;
    return registerWeatherProbePopup(map, layer, time, model, stableMarker.fieldId ?? null);
  }, [map, stableMarker, time, model, layer]);

  // قراءة بالتحويم (مستوحاة من meteoblue): تمرير المؤشّر يُظهر قيمة الطبقة عند النقطة.
  useEffect(() => {
    if (!stableMarker) return undefined;
    return registerWeatherHoverReadout(map, layer, time, model);
  }, [map, stableMarker, time, model, layer]);

  return null;
}
