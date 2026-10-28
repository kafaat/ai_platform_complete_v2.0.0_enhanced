// ═══════════════════════════════════════════════════════════════
// G-IMP-2 (تدقيق RS 2026-10-27) — استيراد Shapefile متعدّد المعالم
// ───────────────────────────────────────────────────────────────
// كان firstPolygonFeature يأخذ أوّل Polygon من ملفّ فيه عدّة معالم/طبقات ويُبلغ
// discardedParts=0، فيُستورَد حقل واحد بصمت وتضيع البقيّة بلا تنبيه. نقطة الاستيراد
// تُنشئ حقلاً واحداً، فالسلوك الصحيح رفضٌ صريح يذكر العدد (لا اختيار ضمنيّ للأوّل).
// shpjs مُظلَّل؛ FileReader حقيقيّ من jsdom؛ نمرّ بمسار handleFilePicked الفعليّ.
// ═══════════════════════════════════════════════════════════════
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';

const shpMock = vi.hoisted(() => ({ result: null as unknown }));
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  TileLayer: () => null,
  FeatureGroup: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  useMap: () => ({ invalidateSize: vi.fn(), on: vi.fn(), off: vi.fn(), getContainer: vi.fn(() => document.createElement('div')) }),
  useMapEvents: () => null,
}));
vi.mock('./maphub/DrawControl', () => ({ default: () => null }));
vi.mock('../lib/leafletSetup', () => ({}));
vi.mock('leaflet', () => ({ default: { latLng: (a: number, b: number) => ({ lat: a, lng: b }), divIcon: vi.fn((opts) => opts) } }));
vi.mock('shpjs', () => ({ default: vi.fn(async () => shpMock.result) }));

import AddFieldWithMap from './AddFieldWithMap';

const sq = (x: number): number[][][] => [[[x, 15], [x + 0.01, 15], [x + 0.01, 15.01], [x, 15.01], [x, 15]]];
const feat = (geometry: GeoJSON.Geometry): GeoJSON.Feature => ({ type: 'Feature', properties: {}, geometry });
const fc = (...features: GeoJSON.Feature[]): GeoJSON.FeatureCollection => ({ type: 'FeatureCollection', features });

function pick(result: unknown) {
  shpMock.result = result;
  render(<AddFieldWithMap onSave={async () => {}} onImport={async () => {}} onCancel={() => {}} />);
  fireEvent.click(screen.getByRole('button', { name: /استيراد ملف/ }));
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File([new Uint8Array([1, 2, 3, 4])], 'fields.zip', { type: 'application/zip' });
  fireEvent.change(input, { target: { files: [file] } });
}
const importButton = () => screen.getByRole('button', { name: /استيراد الحقل/ });

beforeEach(() => { shpMock.result = null; });

describe('G-IMP-2 — Shapefile import with several polygon features', () => {
  it('two Polygon features in one layer ⇒ explicit rejection naming the count, nothing staged', async () => {
    pick(fc(feat({ type: 'Polygon', coordinates: sq(44) }), feat({ type: 'Polygon', coordinates: sq(44.1) })));
    await screen.findByText(/2 معالم مضلّعة/);
    expect(importButton()).toBeDisabled();
  });

  it('polygons split across two layers (array of collections) ⇒ rejected too', async () => {
    pick([fc(feat({ type: 'Polygon', coordinates: sq(44) })), fc(feat({ type: 'MultiPolygon', coordinates: [sq(44.1)] }))]);
    await screen.findByText(/2 معالم مضلّعة/);
    expect(importButton()).toBeDisabled();
  });

  it('one Polygon feature (plus non-polygon features) ⇒ staged for import without warning', async () => {
    pick(fc(feat({ type: 'Point', coordinates: [44, 15] }), feat({ type: 'Polygon', coordinates: sq(44) })));
    await waitFor(() => expect(importButton()).not.toBeDisabled());
    expect(screen.queryByText(/معالم مضلّعة/)).toBeNull();
  });

  it('one multi-part MultiPolygon feature keeps the existing explicit first-part warning', async () => {
    pick(fc(feat({ type: 'MultiPolygon', coordinates: [sq(44), sq(44.1)] })));
    await screen.findByText(/متعدّدة الأجزاء \(2\)/);
    expect(importButton()).not.toBeDisabled();
  });
});
