// ═══════════════════════════════════════════════════════════════
// SAHOOL — MapHub Weather Engine
// Open-Meteo is the data source; SAHOOL renders GridLayer tiles, animation,
// layer controls, legend, time selector, and agronomic probe popups.
// ═══════════════════════════════════════════════════════════════
import { useMap } from 'react-leaflet';
import { useEffect, useMemo, useState } from 'react';
import type { WeatherMarker } from '../OverlayMarkers';

import {
  type WeatherLayerKey,
  type WeatherTimeKey,
  type WindDensity,
} from './weatherLayerDefinitions';
import { readWeatherPreferences, writeWeatherPreferences } from './weatherPreferences';
import { createWeatherWindGridLayer } from './WeatherTileLayer';
import { createWeatherControl } from './WeatherLayerPanel';
import { registerWeatherProbePopup } from './WeatherProbePopup';

export function WeatherRasterOverlay({ marker }: { marker: WeatherMarker | null }) {
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
  const stableMarker = useMemo(() => marker, [marker]);

  useEffect(() => {
    writeWeatherPreferences({ layer, time, model, opacity, showWind, windDensity, panelOpen });
  }, [layer, time, model, opacity, showWind, windDensity, panelOpen]);

  useEffect(() => {
    if (!stableMarker) return undefined;
    const grid = createWeatherWindGridLayer(stableMarker, layer, time, model, opacity, showWind, windDensity).addTo(map);
    const container = grid.getContainer();
    container?.classList.add('sahool-weather-wind-grid-layer');
    if (container) {
      container.style.mixBlendMode = 'screen';
      container.style.pointerEvents = 'none';
      container.style.zIndex = '450';
      container.style.opacity = String(opacity);
    }
    return () => { grid.remove(); };
  }, [map, stableMarker, layer, time, model, opacity, showWind, windDensity]);

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
    ).addTo(map);
    return () => { control.remove(); };
  }, [map, stableMarker, layer, time, model, opacity, showWind, windDensity, panelOpen]);

  useEffect(() => {
    if (!stableMarker) return undefined;
    return registerWeatherProbePopup(map, layer, time, model, stableMarker.fieldId ?? null);
  }, [map, stableMarker, time, model, layer]);

  return null;
}
