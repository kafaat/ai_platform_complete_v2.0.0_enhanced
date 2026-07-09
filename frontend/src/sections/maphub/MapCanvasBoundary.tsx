import type { ReactNode } from 'react';

export type MapCanvasMode = 'leaflet' | 'maplibre' | 'compare' | 'terrain3d';

export type MapCanvasBoundaryProps = {
  mode: MapCanvasMode;
  fieldId: string | null | undefined;
  indicatorId: string | null | undefined;
  hasGeometry: boolean;
  children: ReactNode;
};

/**
 * UI-8 seam: isolates the central map canvas boundary before moving HubMap/HubMapGL.
 * It is intentionally thin: no rendering behavior is changed, but every map runtime now
 * sits behind a stable product boundary with explicit mode/field/layer metadata.
 */
export function MapCanvasBoundary({ mode, fieldId, indicatorId, hasGeometry, children }: MapCanvasBoundaryProps) {
  return (
    <section
      data-testid="maphub-map-canvas-boundary"
      data-sahool-region="map-canvas"
      data-map-canvas-mode={mode}
      data-field-id={fieldId ?? ''}
      data-indicator-id={indicatorId ?? ''}
      data-has-geometry={hasGeometry ? 'true' : 'false'}
      aria-label="Map canvas boundary"
    >
      {children}
    </section>
  );
}
