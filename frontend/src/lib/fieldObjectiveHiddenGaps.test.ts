import { describe, expect, it } from 'vitest';
import { advanceLifecycle, followUpForObjective, initLifecycle, type LifecycleState } from './fieldActionLifecycle';
import { getObjective, type FieldObjectiveDef } from './fieldObjectiveEngine';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const diagnose = getObjective('diagnose_field_stress')!;

function approvedTaskState(objective = diagnose): LifecycleState {
  let s = initLifecycle();
  s = advanceLifecycle(s, 'attach_evidence', { canAct: true }).state;
  s = advanceLifecycle(s, 'approve').state;
  s = advanceLifecycle(s, 'create_task', { objective }).state;
  return s;
}

describe('field objective hidden-gap guards', () => {
  it('does not synthesize an invalid day follow-up when the catalog is malformed', () => {
    const broken: FieldObjectiveDef = { ...diagnose, followUp: 'days', followUpDays: undefined };
    expect(followUpForObjective(broken)).toEqual({ kind: 'none' });
  });

  it('blocks scheduling follow-up when an objective explicitly has no follow-up cadence', () => {
    const noFollow: FieldObjectiveDef = { ...diagnose, followUp: 'none' };
    const s = advanceLifecycle(approvedTaskState(diagnose), 'start_execution').state;
    const r = advanceLifecycle(s, 'schedule_follow_up', { objective: noFollow });
    expect(r.changed).toBe(false);
    expect(r.blockedReason).toContain('لا يملك متابعة');
  });

  it('FieldObjectivePanel requires explicit true from onCreateTask before advancing task lifecycle', () => {
    const src = readFileSync(resolve(process.cwd(), 'src/components/fieldview/FieldObjectivePanel.tsx'), 'utf8');
    expect(src).toContain('if (!onCreateTask)')
    expect(src).toContain('if (accepted !== true)')
    expect(src).toContain('boolean | Promise<boolean>');
    expect(src).not.toContain('void | boolean');
  });

  it('MapHub does not treat crop/area metadata as real field records evidence', () => {
    const src = readFileSync(resolve(process.cwd(), 'src/sections/MapHub.tsx'), 'utf8');
    expect(src).toContain('records: completedOps.length > 0 || !!waterEfficiencyQ.data');
    expect(src).not.toContain("records: !!selected?.crop || (typeof selected?.area === 'number' && selected.area > 0)");
  });
});
