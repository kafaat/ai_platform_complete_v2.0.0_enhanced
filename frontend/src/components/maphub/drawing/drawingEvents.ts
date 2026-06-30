import type { DrawFeature, DrawWorkflow, DrawingEngineId, DrawValidationResult } from './drawingTypes';

export type DrawingEventType =
  | 'draw:start'
  | 'draw:vertex-change'
  | 'draw:created'
  | 'draw:edited'
  | 'draw:deleted'
  | 'draw:validated'
  | 'draw:measurement-change'
  | 'draw:draft-save'
  | 'draw:commit'
  | 'draw:cancel';

export interface DrawingEventBase {
  type: DrawingEventType;
  engine: DrawingEngineId;
  workflow: DrawWorkflow;
  timestamp: string;
  operationId?: string;
}

export interface DrawingFeatureEvent extends DrawingEventBase {
  feature: DrawFeature;
}

export interface DrawingValidationEvent extends DrawingEventBase {
  feature: DrawFeature;
  validation: DrawValidationResult;
}

export type DrawingEvent = DrawingEventBase | DrawingFeatureEvent | DrawingValidationEvent;

export type DrawingEventHandler = (event: DrawingEvent) => void;

export interface DrawingAdapter {
  readonly id: DrawingEngineId;
  readonly enabled: boolean;
  start(workflow: DrawWorkflow): void;
  stop(): void;
  setFeatures(features: DrawFeature[]): void;
  getFeatures(): DrawFeature[];
  on(handler: DrawingEventHandler): () => void;
}

export function createDrawingEvent(
  type: DrawingEventType,
  engine: DrawingEngineId,
  workflow: DrawWorkflow,
  extra: Partial<DrawingFeatureEvent> = {},
): DrawingEvent {
  return {
    type,
    engine,
    workflow,
    timestamp: new Date().toISOString(),
    ...extra,
  } as DrawingEvent;
}
