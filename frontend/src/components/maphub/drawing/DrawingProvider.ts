import type { DrawingAdapter, DrawingEventHandler } from './drawingEvents';
import type { DrawFeature, DrawWorkflow, DrawingEngineId } from './drawingTypes';
import { createDrawingEvent } from './drawingEvents';

export class NullDrawingAdapter implements DrawingAdapter {
  readonly id: DrawingEngineId;
  readonly enabled = false;
  private features: DrawFeature[] = [];
  private handlers = new Set<DrawingEventHandler>();

  constructor(id: DrawingEngineId = 'leaflet-draw') {
    this.id = id;
  }

  start(workflow: DrawWorkflow): void {
    this.emit(createDrawingEvent('draw:start', this.id, workflow));
  }

  stop(): void {
    // no-op: real adapters clean up map handlers here.
  }

  setFeatures(features: DrawFeature[]): void {
    this.features = [...features];
  }

  getFeatures(): DrawFeature[] {
    return [...this.features];
  }

  on(handler: DrawingEventHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  private emit(event: Parameters<DrawingEventHandler>[0]): void {
    for (const handler of this.handlers) handler(event);
  }
}

export function resolveDrawingEngine(value: string | undefined | null): DrawingEngineId {
  if (value === 'leaflet-geoman' || value === 'terra-draw' || value === 'maplibre-terra-draw') return value;
  return 'leaflet-draw';
}

export function getConfiguredDrawingEngine(): DrawingEngineId {
  const meta = import.meta as unknown as { env?: Record<string, string | undefined> };
  const envValue = meta.env?.VITE_DRAW_ENGINE;
  return resolveDrawingEngine(envValue);
}
