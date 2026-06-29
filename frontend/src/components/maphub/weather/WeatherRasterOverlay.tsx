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
  DEFAULT_LAYER,
} from './weatherLayerDefinitions';
import { createWeatherWindGridLayer } from './WeatherTileLayer';
import { createWeatherControl } from './WeatherLayerPanel';
import { registerWeatherProbePopup } from './WeatherProbePopup';

export function WeatherRasterOverlay({ marker }: { marker: WeatherMarker | null }) {
  const map = useMap();
  const [layer, setLayer] = useState<WeatherLayerKey>(DEFAULT_LAYER);
  const [time, setTime] = useState<WeatherTimeKey>('now');
  const [model, setModel] = useState('best_match');
  const [opacity, setOpacity] = useState(0.86);
  const [showWind, setShowWind] = useState(() => !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
  const [windDensity, setWindDensity] = useState<WindDensity>(() => (window.innerWidth < 760 ? 'medium' : 'high'));
  const [panelOpen, setPanelOpen] = useState(() => window.innerWidth >= 880);
  const stableMarker = useMemo(() => marker, [marker]);

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
