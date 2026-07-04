import { describe, expect, it } from 'vitest';
import { buildOperationsSnapshot, type OperationsSnapshotInput } from './fieldOperations';

const NOW = Date.parse('2026-07-04T00:00:00Z');

const base: OperationsSnapshotInput = {
  fieldId: 'F-1',
  tasks: [
    { field_id: 'F-1', task_type: 'irrigation', priority: 3, recommended_date: '2026-07-01', status: 'pending' }, // overdue
    { field_id: 'F-1', task_type: 'scouting', priority: 5, recommended_date: '2026-07-06', status: 'pending' },
    { field_id: 'F-1', task_type: 'harvest', priority: 1, recommended_date: '2026-08-01', status: 'completed' },
    { field_id: 'F-2', task_type: 'spraying', priority: 4, recommended_date: '2026-07-05', status: 'pending' }, // other field
  ],
  equipment: [{ status: 'active' }, { status: 'broken' }, { status: 'active' }],
  alerts: [
    { field_id: 'F-1', status: 'active' },
    { field_id: 'F-1', status: 'resolved' },
    { field_id: 'F-2', status: 'active' },
  ],
};

describe('buildOperationsSnapshot', () => {
  it('filters tasks/alerts to the active field and counts equipment fleet-wide', () => {
    const s = buildOperationsSnapshot(base, NOW);
    expect(s.openTasks).toBe(2); // two pending on F-1 (completed + other field excluded)
    expect(s.overdueTasks).toBe(1); // irrigation on 07-01
    expect(s.equipment).toEqual({ total: 3, ready: 2, down: 1 });
    expect(s.activeAlerts).toBe(1); // only F-1 active
  });

  it('picks the highest-priority open task as next', () => {
    const s = buildOperationsSnapshot(base, NOW);
    expect(s.nextTask?.label).toBe('استكشاف ميدانيّ'); // scouting priority 5 > irrigation 3
  });

  it('escalates severity with a down machine + overdue task', () => {
    const s = buildOperationsSnapshot(base, NOW);
    expect(s.severity).toBe('warn');
    const critical = buildOperationsSnapshot({ ...base, alerts: [
      { field_id: 'F-1', status: 'active' }, { field_id: 'F-1', status: 'active' }, { field_id: 'F-1', status: 'active' },
    ] }, NOW);
    expect(critical.severity).toBe('critical');
  });

  it('returns an honest empty summary when no field is active', () => {
    const s = buildOperationsSnapshot({ ...base, fieldId: null }, NOW);
    expect(s.openTasks).toBe(0);
    expect(s.summary).toContain('اختر حقلاً');
  });
});
