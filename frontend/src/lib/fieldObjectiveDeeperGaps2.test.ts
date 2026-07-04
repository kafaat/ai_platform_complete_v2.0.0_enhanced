import { describe, expect, it } from 'vitest';
import { advanceLifecycle, initLifecycle } from './fieldActionLifecycle';
import { getObjective } from './fieldObjectiveEngine';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const diagnose = getObjective('diagnose_field_stress')!;
const report = getObjective('generate_field_report')!;

function approvedTaskCreatedState() {
  let s = initLifecycle();
  s = advanceLifecycle(s, 'attach_evidence', { canAct: true }).state;
  s = advanceLifecycle(s, 'approve').state;
  s = advanceLifecycle(s, 'create_task', { objective: diagnose }).state;
  return s;
}

describe('field objective deeper hidden-gap guards v2', () => {
  it('blocks direct task outcome while a follow-up objective is still executing', () => {
    const executing = advanceLifecycle(approvedTaskCreatedState(), 'start_execution').state;
    const r = advanceLifecycle(executing, 'record_outcome', { objective: diagnose, outcome: 'improved' });
    expect(r.changed).toBe(false);
    expect(r.blockedReason).toContain('جدولة المتابعة');
  });

  it('requires an explicit non-unknown outcome before a lifecycle can be reviewed', () => {
    const follow = advanceLifecycle(
      advanceLifecycle(approvedTaskCreatedState(), 'start_execution').state,
      'schedule_follow_up',
      { objective: diagnose },
    ).state;
    expect(advanceLifecycle(follow, 'record_outcome', { objective: diagnose }).changed).toBe(false);
    expect(advanceLifecycle(follow, 'record_outcome', { objective: diagnose, outcome: 'unknown' }).changed).toBe(false);
  });

  it('does not allow task-producing objectives to close with completed instead of a real field outcome', () => {
    const follow = advanceLifecycle(
      advanceLifecycle(approvedTaskCreatedState(), 'start_execution').state,
      'schedule_follow_up',
      { objective: diagnose },
    ).state;
    const r = advanceLifecycle(follow, 'record_outcome', { objective: diagnose, outcome: 'completed' });
    expect(r.changed).toBe(false);
    expect(r.blockedReason).toContain('improved/stable/declined');
  });

  it('still permits non-field deliverables to close as completed from approved', () => {
    let s = initLifecycle();
    s = advanceLifecycle(s, 'attach_evidence', { canAct: true }).state;
    s = advanceLifecycle(s, 'approve').state;
    const r = advanceLifecycle(s, 'record_outcome', { objective: report, outcome: 'completed' });
    expect(r.changed).toBe(true);
    expect(r.state.stage).toBe('reviewed');
  });

  it('FieldObjectivePanel resets lifecycle on FieldView context changes and surfaces blocked task creation', () => {
    const src = readFileSync(resolve(process.cwd(), 'src/components/fieldview/FieldObjectivePanel.tsx'), 'utf8');
    expect(src).toContain('contextKey?: string | null');
    expect(src).toContain('}, [contextKey]);');
    expect(src).toContain('setBlockedMessage');
    expect(src).toContain('if (accepted !== true)');
    expect(src).toContain('creatingTask');
  });

  it('MapHub passes the active field id as objective context key', () => {
    const src = readFileSync(resolve(process.cwd(), 'src/sections/MapHub.tsx'), 'utf8');
    expect(src).toContain('contextKey={fieldId}');
  });
});
