// ═══════════════════════════════════════════════════════════════
// SAHOOL — adapters/LeafletGeomanAdapter.ts
// مُحوِّل اختياريّ يلفّ Leaflet-Geoman خلف عقد DrawingAdapter المُوحَّد.
// ───────────────────────────────────────────────────────────────
// محرّك بديل يُختار بعلَم ميزة (VITE_DRAW_ENGINE). إضافيّ بحت — غير موصول
// بعد بأيّ شاشة حيّة (ADR-0031 المرحلة 2).
//
// هذا الملفّ هو المكان الوحيد المسموح فيه باستيراد @geoman-io/*، كي يبقى
// Geoman خارج الحزمة الافتراضيّة (tree-shaken) ما لم يُفعَّل العلَم.
// ═══════════════════════════════════════════════════════════════
import L from 'leaflet';
import '@geoman-io/leaflet-geoman-free';
import '@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css';

import type { DrawingAdapter, DrawingEvent, DrawingEventHandler } from '../drawingEvents';
import { createDrawingEvent } from '../drawingEvents';
import type {
  DrawFeature,
  DrawFeatureKind,
  DrawWorkflow,
  DrawingEngineId,
  GeoJsonGeometry,
} from '../drawingTypes';
import { measureDrawFeature } from '../drawingMeasurements';
import { validateDrawFeature } from '../drawingValidation';

const ENGINE_ID: DrawingEngineId = 'leaflet-geoman';

type GeomanShape = 'Polygon' | 'Rectangle' | 'Circle' | 'Line';

// خريطة سير العمل → أداة رسم Geoman.
function workflowShape(workflow: DrawWorkflow): GeomanShape {
  switch (workflow) {
    case 'measure-distance':
      return 'Line';
    case 'design-pivot':
      return 'Circle';
    case 'measure-area':
      return 'Rectangle';
    default:
      return 'Polygon';
  }
}

function workflowKind(workflow: DrawWorkflow): DrawFeatureKind {
  switch (workflow) {
    case 'design-pivot':
      return 'pivot';
    case 'create-management-zone':
      return 'management-zone';
    case 'create-prescription-zone':
      return 'prescription-zone';
    case 'create-exclusion-zone':
      return 'exclusion-zone';
    case 'measure-distance':
      return 'path';
    case 'measure-area':
      return 'measurement';
    default:
      return 'field';
  }
}

function newId(): string {
  return `gm-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

// تحويل طبقة Geoman → DrawFeature موحّدة عبر layer.toGeoJSON().
function layerToDrawFeature(layer: L.Layer, workflow: DrawWorkflow): DrawFeature {
  const gj = (layer as unknown as { toGeoJSON: () => { geometry: GeoJsonGeometry } }).toGeoJSON();
  const feature: DrawFeature = {
    id: newId(),
    kind: workflowKind(workflow),
    geometry: gj.geometry,
    properties: { engine: ENGINE_ID, workflow },
    version: 1,
    draft: true,
    createdAt: new Date().toISOString(),
  };
  feature.measurements = measureDrawFeature(feature);
  feature.validation = validateDrawFeature(feature);
  return feature;
}

// سطح map.pm الذي يُحقنه Geoman في L.Map.
interface GeomanMap {
  pm: {
    enableDraw(shape: GeomanShape, options?: Record<string, unknown>): void;
    disableDraw(shape?: GeomanShape): void;
    getGeomanLayers?: () => L.Layer[];
  };
}

export class LeafletGeomanAdapter implements DrawingAdapter {
  readonly id: DrawingEngineId = ENGINE_ID;
  readonly enabled = true;

  private readonly map: L.Map & GeomanMap;
  private readonly group: L.FeatureGroup;
  private readonly handlers = new Set<DrawingEventHandler>();
  private readonly featureIndex = new Map<L.Layer, DrawFeature>();
  private activeWorkflow: DrawWorkflow | null = null;

  constructor(map: L.Map, group: L.FeatureGroup) {
    this.map = map as L.Map & GeomanMap;
    this.group = group;
    // أحداث Geoman موحَّدة على مستوى الخريطة.
    this.map.on('pm:create', this.handlePmCreate as L.LeafletEventHandlerFn);
    this.map.on('pm:remove', this.handlePmRemove as L.LeafletEventHandlerFn);
  }

  // يُفعّل أداة الرسم المطابقة: pm.enableDraw('Polygon'|'Rectangle'|'Circle'|'Line').
  start(workflow: DrawWorkflow): void {
    this.activeWorkflow = workflow;
    this.map.pm.enableDraw(workflowShape(workflow));
    this.emit(createDrawingEvent('draw:start', this.id, workflow));
  }

  stop(): void {
    this.map.pm.disableDraw();
    this.activeWorkflow = null;
  }

  setFeatures(features: DrawFeature[]): void {
    this.group.clearLayers();
    this.featureIndex.clear();
    for (const feature of features) {
      const built = L.geoJSON({
        type: 'Feature',
        geometry: feature.geometry as unknown as GeoJSON.Geometry,
        properties: feature.properties,
      } as GeoJSON.Feature);
      built.eachLayer((child) => {
        this.group.addLayer(child);
        this.bindEdit(child, feature);
        this.featureIndex.set(child, feature);
      });
    }
  }

  getFeatures(): DrawFeature[] {
    return Array.from(this.featureIndex.values());
  }

  on(handler: DrawingEventHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  destroy(): void {
    this.stop();
    this.map.off('pm:create', this.handlePmCreate as L.LeafletEventHandlerFn);
    this.map.off('pm:remove', this.handlePmRemove as L.LeafletEventHandlerFn);
    this.handlers.clear();
    this.featureIndex.clear();
  }

  // pm:create → draw:created (+ measurement + validated). يربط أيضاً
  // مُعالِجات pm:edit / pm:vertexadded على الطبقة الجديدة.
  private handlePmCreate = (event: { layer: L.Layer }): void => {
    const workflow = this.activeWorkflow ?? 'create-field';
    const layer = event.layer;
    this.group.addLayer(layer);
    const feature = layerToDrawFeature(layer, workflow);
    this.featureIndex.set(layer, feature);
    this.bindEdit(layer, feature);

    this.emit(createDrawingEvent('draw:created', this.id, workflow, { feature }));
    this.emit(createDrawingEvent('draw:measurement-change', this.id, workflow, { feature }));
    this.emit(
      createDrawingEvent('draw:validated', this.id, workflow, {
        feature,
        validation: feature.validation,
      } as Partial<DrawingEvent>),
    );
  };

  // pm:edit → draw:edited ، pm:vertexadded → draw:vertex-change.
  private bindEdit(layer: L.Layer, feature: DrawFeature): void {
    const workflow = feature.properties.workflow ?? this.activeWorkflow ?? 'create-field';
    layer.on('pm:edit', () => {
      const updated = layerToDrawFeature(layer, workflow);
      updated.id = feature.id;
      updated.version = feature.version + 1;
      this.featureIndex.set(layer, updated);
      this.emit(createDrawingEvent('draw:edited', this.id, workflow, { feature: updated }));
      this.emit(createDrawingEvent('draw:measurement-change', this.id, workflow, { feature: updated }));
    });
    layer.on('pm:vertexadded', () => {
      const updated = layerToDrawFeature(layer, workflow);
      updated.id = feature.id;
      this.emit(createDrawingEvent('draw:vertex-change', this.id, workflow, { feature: updated }));
    });
  }

  // pm:remove → draw:deleted.
  private handlePmRemove = (event: { layer: L.Layer }): void => {
    const layer = event.layer;
    const feature = this.featureIndex.get(layer);
    const workflow = feature?.properties.workflow ?? this.activeWorkflow ?? 'create-field';
    this.featureIndex.delete(layer);
    this.emit(createDrawingEvent('draw:deleted', this.id, workflow, feature ? { feature } : {}));
  };

  private emit(event: DrawingEvent): void {
    for (const handler of this.handlers) handler(event);
  }
}
