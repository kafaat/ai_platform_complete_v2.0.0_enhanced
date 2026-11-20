import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const mapHub = fs.readFileSync(path.join(root, 'src/sections/MapHub.tsx'), 'utf8');
const api = fs.readFileSync(path.join(root, 'src/components/maphub/drawing/drawingFeatureApi.ts'), 'utf8');
const router = fs.readFileSync(path.join(root, '../services/sahool-platform/api/routers/drawing_features.py'), 'utf8');
const migration = fs.readFileSync(path.join(root, '../migrations/v230_drawing_features.sql'), 'utf8');
const migrationManifest = fs.readFileSync(path.join(root, '../migrations/MANIFEST.txt'), 'utf8');

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
    // Schema ownership belongs to the manifest migration; requests perform DML.
    expect(migrationManifest.split(/\r?\n/).map((line) => line.trim()))
      .toContain('v230_drawing_features.sql');
    expect(migration).toContain('CREATE TABLE IF NOT EXISTS drawing_features');
    expect(migration).toContain('ALTER TABLE drawing_features ENABLE ROW LEVEL SECURITY');
    expect(migration).toContain('ALTER TABLE drawing_features FORCE ROW LEVEL SECURITY');
    expect(migration).toContain('CREATE POLICY tenant_isolation ON drawing_features');
    expect(migration).toContain("USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))");
    expect(migration).toContain("WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))");
    expect(router).not.toContain('CREATE TABLE');
    expect(router).toContain('@router.get("/api/v1/fields/{field_id}/drawing-features"');
    expect(router).toContain('@router.post("/api/v1/drawing-features"');
    expect(router).toContain('@router.patch("/api/v1/drawing-features/{feature_id}"');
    expect(router).toContain('@router.delete("/api/v1/drawing-features/{feature_id}"');
    expect(router).toContain('tenant_id = $1::uuid');
    expect(router).toContain('require_permission(Permission.FIELD_EDIT)');
  });
});
