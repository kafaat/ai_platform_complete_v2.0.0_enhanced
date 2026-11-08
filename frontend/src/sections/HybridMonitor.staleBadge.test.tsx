import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { TelemetryPoint } from '../services/api';
import { StaleBadge, staleTitle } from './HybridMonitor';

const point = (over: Partial<TelemetryPoint>): TelemetryPoint => ({
  sensor_type: 'soil_moisture',
  value: 21.5,
  unit: '%',
  recorded_at: '2026-11-01T08:00:00Z',
  ...over,
});

describe('StaleBadge renders from the server freshness fields', () => {
  it('shows the age and the server window on a stale reading', () => {
    render(<StaleBadge p={point({ stale: true, age_sec: 2 * 86400, stale_after_sec: 900 })} />);
    const badge = screen.getByTestId('telemetry-stale-badge');
    expect(badge.textContent).toContain('قديمة');
    expect(badge.textContent).toContain('منذ 2 يوم');
    expect(badge.getAttribute('title')).toContain('(15 دقيقة)');
  });

  it('follows a different server window instead of a hard-coded one', () => {
    render(<StaleBadge p={point({ stale: true, age_sec: 7200, stale_after_sec: 3600 })} />);
    expect(screen.getByTestId('telemetry-stale-badge').getAttribute('title')).toContain('(60 دقيقة)');
  });

  it('renders nothing for a fresh reading', () => {
    const { container } = render(<StaleBadge p={point({ stale: false, age_sec: 60, stale_after_sec: 900 })} />);
    expect(container.textContent).toBe('');
    expect(screen.queryByTestId('telemetry-stale-badge')).toBeNull();
  });

  it('does not invent a window the server did not send', () => {
    expect(staleTitle(undefined)).not.toMatch(/\d+ دقيقة/);
  });
});
