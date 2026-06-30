// ═══════════════════════════════════════════════════════════════
// SAHOOL — adapters/LeafletDrawAdapter.ts
// مُحوِّل (adapter) يلفّ leaflet-draw الخام خلف عقد DrawingAdapter المُوحَّد.
// ───────────────────────────────────────────────────────────────
// المحرّك الافتراضيّ. لا يُغيّر شيئاً في DrawControl.tsx الحيّ — هذا طبقة عقد
// إضافيّة بحتة (ADR-0031 المرحلة 2)، غير موصولة بعد بـMapHub/AddFieldWithMap.
//
// يعكس سلوك DrawControl: يستخدم L.Draw الخام مباشرةً (لا الغلاف المهجور)،
// يُضيف الشكل المرسوم إلى FeatureGroup عند L.Draw.Event.CREATED، ثمّ يحوّله
// إلى DrawFeature (GeoJSON) ويُطلق الأحداث الموحَّدة.
// ═══════════════════════════════════════════════════════════════
import L from 'leaflet';
import 'leaflet-draw'; // أثر جانبيّ: يُعزّز L.Control.Draw / L.Draw / L.Draw.Event
import 'leaflet-draw/dist/leaflet.draw.css';

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

const ENGINE_ID: DrawingEngineId = 'leaflet-draw';

// خريطة سير العمل → نوع شكل الميزة (kind) — لتغذية القياس/التحقّق الزراعيّ.
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
  return `ld-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

// تحويل طبقة Leaflet مرسومة → DrawFeature موحّدة عبر toGeoJSON.
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

export class LeafletDrawAdapter implements DrawingAdapter {
  readonly id: DrawingEngineId = ENGINE_ID;
  readonly enabled = true;

  private readonly map: L.Map;
  private readonly group: L.FeatureGroup;
  private readonly handlers = new Set<DrawingEventHandler>();
  private readonly featureIndex = new Map<L.Layer, DrawFeature>();
  private activeWorkflow: DrawWorkflow | null = null;
  private activeHandler: L.Draw.Feature | null = null;

  constructor(map: L.Map, group: L.FeatureGroup) {
    this.map = map;
    this.group = group;
    this.map.on(L.Draw.Event.CREATED, this.handleCreated);
  }

  // يُفعّل مُعالِج L.Draw المطابق لسير العمل (مضلّع/مستطيل/دائرة/خطّ).
  start(workflow: DrawWorkflow): void {
    this.stopActiveHandler();
    this.activeWorkflow = workflow;
    this.activeHandler = this.createHandler(workflow);
    this.activeHandler?.enable();
    this.emit(createDrawingEvent('draw:start', this.id, workflow));
  }

  stop(): void {
    this.stopActiveHandler();
    this.activeWorkflow = null;
  }

  setFeatures(features: DrawFeature[]): void {
    this.group.clearLayers();
    this.featureIndex.clear();
    for (const feature of features) {
      const layer = L.geoJSON({
        type: 'Feature',
        geometry: feature.geometry as unknown as GeoJSON.Geometry,
        properties: feature.properties,
      } as GeoJSON.Feature);
      layer.eachLayer((child) => {
        this.group.addLayer(child);
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

  // تنظيف كامل: يُفصل عند تفكيك الخريطة.
  destroy(): void {
    this.stopActiveHandler();
    this.map.off(L.Draw.Event.CREATED, this.handleCreated);
    this.handlers.clear();
    this.featureIndex.clear();
  }

  private createHandler(workflow: DrawWorkflow): L.Draw.Feature {
    switch (workflow) {
      case 'measure-distance':
        return new L.Draw.Polyline(this.map, {} as L.DrawOptions.PolylineOptions);
      case 'design-pivot':
        return new L.Draw.Circle(this.map, {} as L.DrawOptions.CircleOptions);
      case 'measure-area':
        return new L.Draw.Rectangle(this.map, {} as L.DrawOptions.RectangleOptions);
      case 'create-field':
      case 'split-field':
      case 'merge-fields':
      case 'create-management-zone':
      case 'create-prescription-zone':
      case 'create-exclusion-zone':
      default:
        // showArea:false يتفادى عطل readableArea المعروف (مطابق DrawControl).
        return new L.Draw.Polygon(this.map, { showArea: false } as L.DrawOptions.PolygonOptions);
    }
  }

  private stopActiveHandler(): void {
    if (this.activeHandler) {
      this.activeHandler.disable();
      this.activeHandler = null;
    }
  }

  // عند الإنشاء: أضف الطبقة للمجموعة، حوّلها لـDrawFeature، أطلق
  // draw:created + draw:measurement-change + draw:validated.
  private handleCreated = (event: L.LeafletEvent): void => {
    const workflow = this.activeWorkflow ?? 'create-field';
    const evt = event as unknown as L.DrawEvents.Created;
    const layer = evt.layer;
    this.group.addLayer(layer);
    const feature = layerToDrawFeature(layer, workflow);
    this.featureIndex.set(layer, feature);

    this.emit(createDrawingEvent('draw:created', this.id, workflow, { feature }));
    this.emit(createDrawingEvent('draw:measurement-change', this.id, workflow, { feature }));
    this.emit(
      createDrawingEvent('draw:validated', this.id, workflow, {
        feature,
        validation: feature.validation,
      } as Partial<DrawingEvent>),
    );
  };

  private emit(event: DrawingEvent): void {
    for (const handler of this.handlers) handler(event);
  }
}
