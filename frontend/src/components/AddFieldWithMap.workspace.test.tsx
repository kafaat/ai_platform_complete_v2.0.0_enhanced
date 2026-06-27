// ═══════════════════════════════════════════════════════════════
// Regression — محرّر حدود الحقل بعد de-modal (مساحة عمل GIS لا مودال مركزيّ)
// ───────────────────────────────────────────────────────────────
// يحرس تحويل AddFieldWithMap من مودال مركزيّ (max-w-4xl) إلى مساحة عمل ملء
// الشاشة (fixed inset-0 flex-col: درج تحكّم + خريطة flex-1). jsdom لا يصيّر
// خريطة فعليّة، فنُظلّل react-leaflet/DrawControl/leaflet (نفس نهج
// PrescriptionBuilderPage.test). نتحقّق بصدق من البنية لا من التفاعل البصريّ
// (سحب الرؤوس/الإزاحة الفعليّة تتطلّب متصفّحاً حيّاً — موثّق في مصفوفة الإغلاق).
// ═══════════════════════════════════════════════════════════════
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children?: ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => <div data-testid="tile" />,
  FeatureGroup: ({ children }: { children?: ReactNode }) => <div data-testid="fg">{children}</div>,
  useMap: () => ({ invalidateSize: vi.fn() }),
  useMapEvents: () => null,
  CircleMarker: () => <div data-testid="pivot-center-marker" />,
  Polyline: () => <div data-testid="pivot-radius-line" />,
}));
vi.mock('./maphub/DrawControl', () => ({ default: () => <div data-testid="draw" /> }));
vi.mock('../lib/leafletSetup', () => ({}));
vi.mock('leaflet', () => ({ default: { latLng: (a: number, b: number) => ({ lat: a, lng: b }) } }));
vi.mock('shpjs', () => ({ default: vi.fn() }));

import AddFieldWithMap from './AddFieldWithMap';

const noop = async () => {};

describe('AddFieldWithMap — مساحة عمل GIS (de-modal)', () => {
  it('الحاوية الجذر ملء الشاشة (fixed inset-0 flex-col) لا بطاقة مودال مركزيّة', () => {
    const { container } = render(
      <AddFieldWithMap onSave={noop} onImport={noop} onCancel={() => {}} />,
    );
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toContain('fixed');
    expect(root.className).toContain('inset-0');
    expect(root.className).toContain('flex-col');
    // لم تعُد بطاقة مودال مركزيّة محدودة العرض.
    expect(container.innerHTML).not.toContain('max-w-4xl');
    expect(container.innerHTML).not.toContain('items-center justify-center');
  });

  it('يعرض ترويسة الرسم + الخريطة + أداة الرسم في مرحلة الرسم', () => {
    render(<AddFieldWithMap onSave={noop} onImport={noop} onCancel={() => {}} />);
    // العنوان في الشريط العلويّ (heading) — لا الخلط مع نصّ الإرشاد المطابق في الدرج.
    expect(screen.getByRole('heading', { name: /ارسم حدود الحقل/ })).toBeInTheDocument();
    expect(screen.getByTestId('map')).toBeInTheDocument();
    expect(screen.getByTestId('draw')).toBeInTheDocument();
  });

  it('درج التحكّم يحوي أدوات الرسم: التقاط الحدود + إنشاء دائرة بنصف قطر + مركز/محيط للمحور', () => {
    render(<AddFieldWithMap onSave={noop} onImport={noop} onCancel={() => {}} />);
    expect(screen.getByText(/التقاط للحدود/)).toBeInTheDocument();
    expect(screen.getByText(/إنشاء دائرة/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /حدّد المركز/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /نقطة على المحيط/ })).toBeDisabled();
  });

  it('تبويبا رسم/استيراد يظهران حين تُوفَّر onImport (وإلّا فلا)', () => {
    const { rerender } = render(
      <AddFieldWithMap onSave={noop} onImport={noop} onCancel={() => {}} />,
    );
    // التبويب زرّ (button) — يتمايز عن رقاقة «أو استيراد ملفّ» (span) في الدرج.
    expect(screen.getByRole('button', { name: /استيراد ملفّ/ })).toBeInTheDocument();
    // بلا onImport: لا تبويب استيراد (الرسم فقط).
    rerender(<AddFieldWithMap onSave={noop} onCancel={() => {}} />);
    expect(screen.queryByRole('button', { name: /استيراد ملفّ/ })).not.toBeInTheDocument();
  });
});
