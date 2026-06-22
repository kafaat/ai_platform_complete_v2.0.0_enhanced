// ═══════════════════════════════════════════════════════════════
// SAHOOL — تغطية علامات الطبقات التراكبيّة (OverlayMarkers) — F3
// ───────────────────────────────────────────────────────────────
// المكوّنات (AlertOverlay/DeviceOverlay/WeatherOverlay) تضع علامات Leaflet من
// {lat,lng} المُمرَّرة. jsdom بلا خريطة فعليّة ⇒ نُظلّل react-leaflet (Marker
// يلتقط position/zIndexOffset) وleaflet (divIcon no-op). نُثبت بصدق:
//   (أ) كلّ علامة صالحة تُوضَع عند [lat,lng] الصحيحة (لا اختراع/إزاحة).
//   (ب) الحارس الفارغ: مصفوفة فارغة / null ⇒ لا علامة (return null).
//   (ج) إسناد z-index الصحيح لكلّ طبقة (تنبيه/جهاز/طقس فوق المضلّعات).
//
// صدق النطاق: OverlayMarkers طبقة عرض صرفة — لا تُصفّي إحداثيّات NaN/Infinity
// بنفسها (تثق فيما يُمرَّر). تصفية الإحداثيّات غير الصالحة تقع *قبل* الوصول هنا
// في fieldRepresentativePoint (lib/geo) المُختبَرة في lib/geo.test.ts؛ لا نُكرّر
// ادّعاءها هنا كي لا نزعم سلوكاً لا تملكه طبقة العرض.
// ═══════════════════════════════════════════════════════════════
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';

// ── ظِلّ react-leaflet: Marker يلتقط position/zIndexOffset لكلّ إنشاء ──
const placed = vi.hoisted(() => [] as Array<{ position: [number, number]; z: number | undefined }>);
vi.mock('react-leaflet', () => ({
  Marker: ({ position, zIndexOffset, children }: { position: [number, number]; zIndexOffset?: number; children?: ReactNode }) => {
    placed.push({ position, z: zIndexOffset });
    return <div data-testid="marker">{children}</div>;
  },
  Tooltip: ({ children }: { children?: ReactNode }) => <div data-testid="tooltip">{children}</div>,
}));
vi.mock('leaflet', () => ({
  default: { divIcon: (o: unknown) => ({ icon: o }) },
}));

import { AlertOverlay, DeviceOverlay, WeatherOverlay } from './OverlayMarkers';
import type { AlertMarker, DeviceMarker, WeatherMarker } from './OverlayMarkers';

beforeEach(() => { placed.length = 0; });

describe('OverlayMarkers — وضع العلامات التراكبيّة (صدق الإحداثيّات/z) — F3', () => {
  // (أ) كلّ تنبيه صالح يُوضَع عند [lat,lng] الصحيحة + z التنبيه (800).
  it('(أ) AlertOverlay يضع علامة لكلّ تنبيه عند إحداثيّاته الصحيحة', () => {
    const markers: AlertMarker[] = [
      { id: 'a1', lat: 15.0, lng: 44.0, severity: 'critical', title: 'جفاف', fieldName: 'حقل أ' },
      { id: 'a2', lat: 15.5, lng: 44.5, severity: 'warning', title: 'آفة', fieldName: 'حقل ب' },
    ];
    render(<AlertOverlay markers={markers} />);
    expect(placed).toHaveLength(2);
    expect(placed[0].position).toEqual([15.0, 44.0]);
    expect(placed[1].position).toEqual([15.5, 44.5]);
    // z التنبيه ثابت (800) — فوق المضلّعات/البلاطات.
    expect(placed.every((p) => p.z === 800)).toBe(true);
  });

  // (ب) الحارس الفارغ: لا تنبيهات ⇒ لا علامة (return null).
  it('(ب) AlertOverlay بمصفوفة فارغة ⇒ لا علامة', () => {
    const { container } = render(<AlertOverlay markers={[]} />);
    expect(placed).toHaveLength(0);
    expect(container.querySelector('[data-testid="marker"]')).toBeNull();
  });

  // (ج) DeviceOverlay يضع علامة لكلّ جهاز عند إحداثيّاته + z الجهاز (750).
  it('(ج) DeviceOverlay يضع علامة لكلّ جهاز عند إحداثيّاته الصحيحة', () => {
    const markers: DeviceMarker[] = [
      { id: 'd1', lat: 15.1, lng: 44.1, name: 'مستشعر تربة', dtype: 'soil', online: true },
    ];
    render(<DeviceOverlay markers={markers} />);
    expect(placed).toHaveLength(1);
    expect(placed[0].position).toEqual([15.1, 44.1]);
    expect(placed[0].z).toBe(750);
  });

  it('(د) DeviceOverlay بمصفوفة فارغة ⇒ لا علامة', () => {
    render(<DeviceOverlay markers={[]} />);
    expect(placed).toHaveLength(0);
  });

  // (هـ) WeatherOverlay: علامة واحدة عند نقطة الحقل المختار + z الطقس (900).
  it('(هـ) WeatherOverlay يضع علامة واحدة عند نقطة الطقس الصحيحة', () => {
    const marker: WeatherMarker = { lat: 15.05, lng: 44.02, tempC: 30, humidityPct: 40, conditionAr: 'صحو' };
    render(<WeatherOverlay marker={marker} />);
    expect(placed).toHaveLength(1);
    expect(placed[0].position).toEqual([15.05, 44.02]);
    expect(placed[0].z).toBe(900);
  });

  // (و) الحارس الفارغ للطقس: marker = null ⇒ لا علامة.
  it('(و) WeatherOverlay بـnull ⇒ لا علامة', () => {
    const { container } = render(<WeatherOverlay marker={null} />);
    expect(placed).toHaveLength(0);
    expect(container.querySelector('[data-testid="marker"]')).toBeNull();
  });
});
