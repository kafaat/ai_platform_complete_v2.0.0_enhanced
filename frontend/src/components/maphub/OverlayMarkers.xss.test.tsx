// S10: علامة الطقس في محرّك Leaflet تبني divIcon.html (يُسنَد إلى innerHTML) من weather_ar
// القادم من الخادم. النصّ يجب أن يُعرَض حرفيّاً لا وسماً.
import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';

const icons = vi.hoisted(() => [] as Array<{ html?: string }>);
vi.mock('react-leaflet', () => ({
  Marker: ({ icon, children }: { icon: { icon: { html?: string } }; children?: ReactNode }) => {
    icons.push(icon.icon);
    return <div>{children}</div>;
  },
  Tooltip: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));
vi.mock('leaflet', () => ({ default: { divIcon: (o: unknown) => ({ icon: o }) } }));
vi.mock('./weather/WeatherRasterOverlay', () => ({ WeatherRasterOverlay: () => null }));

import { WeatherOverlay } from './OverlayMarkers';

describe('WeatherOverlay (Leaflet) — weather_ar is escaped in divIcon html (S10)', () => {
  it('renders a hostile condition as text', () => {
    const hostile = '<img src=x onerror="window.__pwned=1">';
    render(<WeatherOverlay marker={{ lat: 15, lng: 44, tempC: 31, humidityPct: 40, conditionAr: hostile }} />);
    const host = document.createElement('div');
    host.innerHTML = icons[0]?.html ?? '';
    expect(host.querySelectorAll('img')).toHaveLength(0);
    expect(host.textContent).toContain(hostile);
    expect(host.textContent).toContain('31°م');
  });
});
