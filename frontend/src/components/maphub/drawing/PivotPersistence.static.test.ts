import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const mapHub = fs.readFileSync(path.join(root, 'src/sections/MapHub.tsx'), 'utf8');
const api = fs.readFileSync(path.join(root, 'src/components/maphub/drawing/drawingFeatureApi.ts'), 'utf8');
const router = fs.readFileSync(path.join(root, '../services/sahool-platform/api/routers/drawing_features.py'), 'utf8');

describe('v37/v38 pivot persistence contract', () => {
  it('links pivot drafts to the selected field and active season before saving', () => {
    expect(mapHub).toContain('selectedActiveSeasonId');
    expect(mapHub).toContain("seasonId: selectedActiveSeasonId ?? undefined");
    expect(mapHub).toContain("workflow: 'design-pivot'");
    expect(mapHub).toContain('btn-save-pivot-drafts');
  });

  it('loads and saves drawing features through the API client', () => {
    expect(api).toContain('listDrawingFeatures');
    expect(api).toContain('createDrawingFeature');
    expect(api).toContain('/api/v1/drawing-features');
    expect(api).toContain('/api/v1/fields/${fieldId}/drawing-features');
  });

  it('adds tenant-scoped backend CRUD routes for drawing features', () => {
    expect(router).toContain('CREATE TABLE IF NOT EXISTS drawing_features');
    expect(router).toContain('@router.get("/api/v1/fields/{field_id}/drawing-features"');
    expect(router).toContain('@router.post("/api/v1/drawing-features"');
    expect(router).toContain('@router.patch("/api/v1/drawing-features/{feature_id}"');
    expect(router).toContain('@router.delete("/api/v1/drawing-features/{feature_id}"');
    expect(router).toContain('tenant_id = $1::uuid');
    expect(router).toContain('require_permission(Permission.FIELD_EDIT)');
  });
});
