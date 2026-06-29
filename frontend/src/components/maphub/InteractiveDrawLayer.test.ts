// هندسة نقيّة + حارس مصدر — لا DOM ولا استيراد leaflet وقت التشغيل، فيعمل بثبات
// (CI يعتمد tsc لا vitest على أيّ حال). نمذجة النقاط/الإحداثيّات ككائنات عاديّة.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type L from 'leaflet';
import { rectangleCorners } from './drawGeometry';

// خريطة وهميّة بلا leaflet: نطابق نقطة الطبقة بـ(x=lng, y=lat) وعكسها — كافٍ لاختبار
// هندسة المستطيل المُدار (الحساب يجري في فضاء البكسل ثمّ يُعاد لإحداثيّات).
const ll = (lat: number, lng: number) => ({ lat, lng }) as L.LatLng;
const mockMap = {
  latLngToLayerPoint: (p: L.LatLng) => ({ x: p.lng, y: p.lat }),
  layerPointToLatLng: (p: { x: number; y: number }) => ({ lat: p.y, lng: p.x }),
} as unknown as L.Map;

describe('rectangleCorners — مستطيل مُدار من ضلع أساس + مؤشّر', () => {
  it('returns a right-angled rectangle from base edge A→B and cursor C', () => {
    const corners = rectangleCorners(mockMap, ll(0, 0), ll(0, 10), ll(5, 5));
    expect(corners).toHaveLength(4);
    expect(corners[0].lat).toBeCloseTo(0);
    expect(corners[0].lng).toBeCloseTo(0);
    expect(corners[1].lat).toBeCloseTo(0);
    expect(corners[1].lng).toBeCloseTo(10);
    expect(corners[2].lat).toBeCloseTo(5);
    expect(corners[2].lng).toBeCloseTo(10);
    expect(corners[3].lat).toBeCloseTo(5);
    expect(corners[3].lng).toBeCloseTo(0);
  });

  it('keeps right angles for a rotated (diagonal) base edge', () => {
    const corners = rectangleCorners(mockMap, ll(0, 0), ll(10, 10), ll(0, 10));
    const ab = { x: corners[1].lng - corners[0].lng, y: corners[1].lat - corners[0].lat };
    const bc = { x: corners[2].lng - corners[1].lng, y: corners[2].lat - corners[1].lat };
    expect(ab.x * bc.x + ab.y * bc.y).toBeCloseTo(0); // التعامد
  });
});

describe('AddFieldWithMap — تكامل أدوات الرسم التفاعليّة', () => {
  const src = readFileSync(join(process.cwd(), 'src/components/AddFieldWithMap.tsx'), 'utf8');

  it('wires InteractiveDrawLayer for circle and rectangle', () => {
    expect(src).toContain('import InteractiveDrawLayer');
    expect(src).toContain('onCircle={handleInteractiveCircle}');
    expect(src).toContain('onRectangle={handleInteractiveRectangle}');
  });

  it('keeps polygon on leaflet-draw but delegates circle/rectangle', () => {
    expect(src).toContain('rectangle: false');
    expect(src).toContain('circle: false');
    expect(src).toMatch(/polygon:\s*\{/);
  });

  it('exposes on-map circle/rectangle tool buttons (discoverable where users look)', () => {
    // حارس انحدار: أداتا الدائرة/المستطيل يجب أن تظهرا على الخريطة (z-[1000])، لا في
    // اللوحة الجانبيّة فقط — وإلّا «أداة الدائرة غير موجودة» كما في تقرير المستخدم.
    expect(src).toContain('z-[1000]');
    expect(src).toMatch(/setDrawTool\(t => \(t === 'circle' \? null : 'circle'\)\)/);
    expect(src).toMatch(/setDrawTool\(t => \(t === 'rectangle' \? null : 'rectangle'\)\)/);
  });

  it('makes the drawn shape movable by a draggable center handle', () => {
    // مقبض مركز قابل للسحب ينقل الشكل كاملاً (إمساك من الوسط).
    expect(src).toContain('centerHandleRef');
    expect(src).toContain('CENTER_HANDLE_ICON');
    expect(src).toContain('ringCentroid');
    expect(src).toContain('draggable: true');
  });

  it('uses fewer circle vertices so individual points are grabbable', () => {
    // 24 رأساً (خطوة 15°) بدل 72 المتلاصقة — ليُمسِك المستخدم رأساً بعينه.
    expect(src).toMatch(/radiusM: number, n = 24/);
  });

  it('exposes on-map undo and cancel controls during editing', () => {
    expect(src).toContain('onClick={handleUndo}');
    expect(src).toMatch(/تراجع/);
    expect(src).toMatch(/إلغاء/);
  });
});
