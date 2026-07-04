import { describe, expect, it } from 'vitest';
import {
  advanceLifecycle,
  followUpForObjective,
  initLifecycle,
  outcomeLabel,
  recommendationQuality,
  stageLabel,
  type LifecycleState,
} from './fieldActionLifecycle';
import { getObjective } from './fieldObjectiveEngine';

const diagnose = getObjective('diagnose_field_stress')!;
const vra = getObjective('create_vra_prescription')!;

describe('initLifecycle', () => {
  it('starts as an honest draft with unknown outcome and no follow-up', () => {
    const s = initLifecycle();
    expect(s.stage).toBe('draft');
    expect(s.outcome).toBe('unknown');
    expect(s.followUp).toBeNull();
  });
});

describe('advanceLifecycle — explicit transitions only', () => {
  it('walks the full happy path draft → reviewed', () => {
    let s: LifecycleState = initLifecycle();
    const step = (event: Parameters<typeof advanceLifecycle>[1], input = {}) => {
      const r = advanceLifecycle(s, event, input);
      expect(r.changed).toBe(true);
      s = r.state;
    };
    step('attach_evidence', { canAct: true });
    expect(s.stage).toBe('evidence');
    step('approve');
    step('create_task');
    step('start_execution');
    step('schedule_follow_up', { objective: diagnose });
    expect(s.stage).toBe('follow_up');
    expect(s.followUp).toEqual({ kind: 'next_image' });
    step('record_outcome', { outcome: 'improved' });
    expect(s.stage).toBe('reviewed');
    expect(s.outcome).toBe('improved');
  });

  it('never jumps: an out-of-order event is blocked with a reason', () => {
    const s = initLifecycle();
    const r = advanceLifecycle(s, 'create_task');
    expect(r.changed).toBe(false);
    expect(r.state).toBe(s);
    expect(r.blockedReason).toContain('غير مسموح');
  });

  it('blocks attaching evidence when the objective cannot act (incomplete evidence)', () => {
    const s = initLifecycle();
    const r = advanceLifecycle(s, 'attach_evidence', { canAct: false });
    expect(r.changed).toBe(false);
    expect(r.blockedReason).toContain('ناقص');
  });

  it('schedules a day-based follow-up from the objective catalog', () => {
    const irrigation = getObjective('plan_irrigation_week')!;
    let s = initLifecycle();
    for (const e of ['attach_evidence', 'approve', 'create_task', 'start_execution'] as const) {
      s = advanceLifecycle(s, e, { canAct: true }).state;
    }
    s = advanceLifecycle(s, 'schedule_follow_up', { objective: irrigation }).state;
    expect(s.followUp).toEqual({ kind: 'days', days: 7 });
  });

  it('can archive from any live stage', () => {
    const s = advanceLifecycle(initLifecycle(), 'archive').state;
    expect(s.stage).toBe('archived');
    // مؤرشفة نهائيّة — لا انتقال بعدها
    expect(advanceLifecycle(s, 'approve').changed).toBe(false);
  });

  it('records outcome directly from executing without a scheduled follow-up', () => {
    let s = initLifecycle();
    for (const e of ['attach_evidence', 'approve', 'create_task', 'start_execution'] as const) {
      s = advanceLifecycle(s, e, { canAct: true }).state;
    }
    s = advanceLifecycle(s, 'record_outcome', { outcome: 'stable' }).state;
    expect(s.stage).toBe('reviewed');
    expect(s.outcome).toBe('stable');
  });
});

describe('followUpForObjective', () => {
  it('maps none-follow-up objectives honestly to none', () => {
    expect(followUpForObjective(vra)).toEqual({ kind: 'none' });
  });
});

describe('recommendationQuality — unknown until truly reviewed', () => {
  it('is unknown before review', () => {
    expect(recommendationQuality(initLifecycle())).toBe('unknown');
  });
  it('is good for improved/stable and poor for declined', () => {
    expect(recommendationQuality({ stage: 'reviewed', outcome: 'improved', followUp: null })).toBe('good');
    expect(recommendationQuality({ stage: 'reviewed', outcome: 'stable', followUp: null })).toBe('good');
    expect(recommendationQuality({ stage: 'reviewed', outcome: 'declined', followUp: null })).toBe('poor');
    expect(recommendationQuality({ stage: 'reviewed', outcome: 'unknown', followUp: null })).toBe('unknown');
  });
});

describe('labels', () => {
  it('render Arabic stage and outcome labels', () => {
    expect(stageLabel('follow_up')).toBe('بانتظار المتابعة');
    expect(outcomeLabel('declined')).toBe('تراجع');
  });
});
