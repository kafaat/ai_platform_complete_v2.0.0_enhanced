import { describe, expect, it } from 'vitest';
import {
  FIELD_OBJECTIVES,
  buildObjectivePlan,
  getObjective,
  type EvidenceAvailability,
} from './fieldObjectiveEngine';

describe('FIELD_OBJECTIVES catalog', () => {
  it('defines the nine ready objectives', () => {
    const ids = FIELD_OBJECTIVES.map((o) => o.id);
    expect(ids).toEqual([
      'diagnose_field_stress',
      'plan_irrigation_week',
      'prepare_spray_window',
      'create_vra_prescription',
      'review_season_profitability',
      'generate_field_report',
      'check_planting_window',
      'plan_rotation',
      'track_gdd_stage',
    ]);
  });

  it('every objective has at least one required source and a review step', () => {
    for (const o of FIELD_OBJECTIVES) {
      expect(o.requiredSources.length).toBeGreaterThan(0);
      const kinds = o.steps.map((s) => s.kind);
      // كلّ هدف يمرّ بحلقة الوكيل: فحص ثمّ مراجعة على الأقلّ.
      expect(kinds).toContain('inspect');
      expect(kinds).toContain('review');
    }
  });

  it('task-producing objectives carry a dispatch mapping; deliverables do not', () => {
    for (const o of FIELD_OBJECTIVES) {
      if (o.producesTask) {
        expect(o.dispatch, o.id).toBeDefined();
        expect(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']).toContain(o.dispatch!.riskLevel);
      } else {
        expect(o.dispatch, o.id).toBeUndefined();
      }
    }
    // الرشّ أعلى خطراً من الريّ (مبيدات) — يتطلّب حوكمة أشدّ في الموزِّع.
    expect(getObjective('prepare_spray_window')!.dispatch!.riskLevel).toBe('HIGH');
  });

  it('day-based follow-ups carry a concrete followUpDays (no invented cadence)', () => {
    for (const o of FIELD_OBJECTIVES) {
      if (o.followUp === 'days') expect(typeof o.followUpDays).toBe('number');
    }
  });
});

describe('getObjective', () => {
  it('returns the definition for a known id and null otherwise', () => {
    expect(getObjective('plan_irrigation_week')?.label).toBe('خطّة ريّ الأسبوع');
    // @ts-expect-error unknown id is rejected at the type level but guarded at runtime too
    expect(getObjective('nope')).toBeNull();
  });
});

describe('buildObjectivePlan — evidence gating (function #5)', () => {
  it('is ready and can act only when every required source is present', () => {
    const full: EvidenceAvailability = { imagery: true, weather: true, moisture: true };
    const plan = buildObjectivePlan('diagnose_field_stress', full);
    expect(plan).not.toBeNull();
    expect(plan!.missingSources).toEqual([]);
    expect(plan!.ready).toBe(true);
    expect(plan!.canAct).toBe(true);
    expect(plan!.summary).toContain('مكتملة');
  });

  it('blocks the action and lists exactly the missing sources when evidence is incomplete', () => {
    const partial: EvidenceAvailability = { imagery: true }; // ينقص weather + moisture
    const plan = buildObjectivePlan('diagnose_field_stress', partial);
    expect(plan!.ready).toBe(false);
    expect(plan!.canAct).toBe(false);
    expect(plan!.missingSources).toEqual(['weather', 'moisture']);
    expect(plan!.summary).toContain('ناقصة');
  });

  it('treats a source explicitly false the same as absent (honest, no optimism)', () => {
    const plan = buildObjectivePlan('plan_irrigation_week', { moisture: false, weather: true });
    expect(plan!.missingSources).toEqual(['moisture']);
    expect(plan!.canAct).toBe(false);
  });

  it('returns null for an unknown objective id', () => {
    // @ts-expect-error runtime guard for a bad id
    expect(buildObjectivePlan('unknown', {})).toBeNull();
  });
});
