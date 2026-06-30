import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(__dirname, '../../../..');
const offline = readFileSync(resolve(root, 'src/components/maphub/drawing/drawingOfflineSync.ts'), 'utf8');
const api = readFileSync(resolve(root, 'src/components/maphub/drawing/drawingFeatureApi.ts'), 'utf8');
const mapHub = readFileSync(resolve(root, 'src/sections/MapHub.tsx'), 'utf8');
const barrel = readFileSync(resolve(root, 'src/components/maphub/drawing/index.ts'), 'utf8');

describe('v41 offline drawing sync static contract', () => {
  it('ships local draft storage and an idempotent sync queue contract', () => {
    expect(offline).toContain('DRAWING_DRAFTS_STORAGE_KEY');
    expect(offline).toContain('DRAWING_SYNC_QUEUE_STORAGE_KEY');
    expect(offline).toContain('operationId');
    expect(offline).toContain('enqueueDrawingCreate');
    expect(offline).toContain('syncDrawingQueue');
    expect(offline).toContain('compactSyncedDrawingQueue');
  });

  it('keeps offline-first behavior behind drawingFeatureApi wrappers', () => {
    expect(api).toContain('listDrawingFeaturesWithOfflineQueue');
    expect(api).toContain('createDrawingFeatureOfflineFirst');
    expect(api).toContain('updateDrawingFeatureOfflineFirst');
    expect(api).toContain('deleteDrawingFeatureOfflineFirst');
    expect(api).toContain('syncOfflineDrawingFeatures');
    expect(api).toContain('isLikelyOfflineError');
  });

  it('wires MapHub to offline-aware list/create aliases without changing button workflows', () => {
    expect(mapHub).toContain('createDrawingFeatureOfflineFirst as createDrawingFeature');
    expect(mapHub).toContain('listDrawingFeaturesWithOfflineQueue as listDrawingFeatures');
    expect(mapHub).toContain('createDrawingFeature(feature)');
    expect(mapHub).toContain('btn-zone-designer');
    expect(mapHub).toContain('btn-pivot-designer');
  });

  it('exports offline sync utilities from DrawingCore', () => {
    expect(barrel).toContain("export * from './drawingOfflineSync'");
  });
});
