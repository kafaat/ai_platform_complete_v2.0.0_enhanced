import { describe, expect, it } from 'vitest';
import {
  dlqHealth,
  queueStatusChips,
  readinessCounters,
  type ReadinessReport,
} from './adminRuntime';

describe('readinessCounters — server statuses as-is, unknown counted as warn', () => {
  const report: ReadinessReport = {
    ready: false,
    is_production: true,
    blockers: ['b1'],
    warnings: ['w1'],
    checks: [
      { key: 'jwt', status: 'ok' },
      { key: 'db_role', status: 'block' },
      { key: 'redis', status: 'warn' },
      { key: 'weird', status: 'mystery' },
    ],
  };
  it('counts ok/warn/block with unknown as warn (fail-cautious)', () => {
    expect(readinessCounters(report)).toEqual({ ok: 1, warn: 2, block: 1 });
  });
  it('is all-zero for missing report', () => {
    expect(readinessCounters(null)).toEqual({ ok: 0, warn: 0, block: 0 });
  });
});

describe('dlqHealth — any dead letter demands attention (server guidance)', () => {
  const dl = (total: number) => ({ dead_letter: [], total });
  it('is healthy only when both queues are empty', () => {
    expect(dlqHealth(dl(0), dl(0))).toBe('healthy');
  });
  it('flags attention when either queue has dead letters', () => {
    expect(dlqHealth(dl(2), dl(0))).toBe('attention');
    expect(dlqHealth(dl(0), dl(1))).toBe('attention');
  });
  it('is unknown when nothing loaded yet', () => {
    expect(dlqHealth(null, undefined)).toBe('unknown');
  });
});

describe('queueStatusChips — shows only non-zero statuses, biggest first', () => {
  it('filters zeros and sorts desc', () => {
    const chips = queueStatusChips({
      tenant_id: 't1',
      total_in_queue: 7,
      by_status: { pending: 5, failed: 2, done: 0 },
    });
    expect(chips).toEqual([
      { status: 'pending', count: 5 },
      { status: 'failed', count: 2 },
    ]);
  });
  it('returns [] for missing queue', () => {
    expect(queueStatusChips(null)).toEqual([]);
  });
});
