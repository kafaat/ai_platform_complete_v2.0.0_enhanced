import { describe, expect, it } from 'vitest';
import {
  buildCandidateBodies, buildOutcomeInput, dash, emptyCandidateDraft, emptyOutcomeDraft,
  engineCategoryColor, engineCategoryLabel, engineStatusColor, engineStatusLabel, goalLabel,
  isEngineEffective, levelLabel, scoreLabel, suitedColor, suitedLabel,
  validateCandidateDrafts, validateOutcomeDraft,
} from './recommendationsLifecycle';

describe('goalLabel — الأهداف المعروفة فقط، المجهول يمرّ كما هو', () => {
  it('labels the four known FarmerGoal values', () => {
    expect(goalLabel('max_profit')).toBe('تعظيم الربح');
    expect(goalLabel('food_security')).toBe('الأمن الغذائي');
    expect(goalLabel('min_water')).toBe('ترشيد الماء');
    expect(goalLabel('drought_resilience')).toBe('الصمود للجفاف');
  });
  it('passes unknown through and dashes missing', () => {
    expect(goalLabel('weird_goal')).toBe('weird_goal');
    expect(goalLabel(null)).toBe('—');
  });
});

describe('levelLabel — low/mid/high/unknown معروفة، الغريب يمرّ حرفيّاً', () => {
  it('labels known levels', () => {
    expect(levelLabel('low')).toBe('منخفض');
    expect(levelLabel('mid')).toBe('متوسّط');
    expect(levelLabel('high')).toBe('مرتفع');
    expect(levelLabel('unknown')).toBe('مجهول');
  });
  it('unknown passes through, missing dashes', () => {
    expect(levelLabel('extreme')).toBe('extreme');
    expect(levelLabel(null)).toBe('—');
    expect(levelLabel('')).toBe('—');
  });
});

describe('engine category + effective status — known values only, neutral fallback', () => {
  it('labels/colors documented categories (recommendations_hub)', () => {
    expect(engineCategoryLabel('irrigation')).toBe('ريّ');
    expect(engineCategoryLabel('yield')).toBe('غلّة');
    expect(engineCategoryColor('disease')).toBe('#fca5a5');
  });
  it('is neutral for unknown/missing category', () => {
    expect(engineCategoryLabel('exotic')).toBe('exotic');
    expect(engineCategoryColor('exotic')).toBe('#64748b');
    expect(engineCategoryColor(null)).toBe('#64748b');
  });
  it('effective status comes from effective_enabled as-is', () => {
    expect(isEngineEffective('irrigation', ['irrigation', 'disease'])).toBe(true);
    expect(isEngineEffective('yield', ['irrigation'])).toBe(false);
    expect(isEngineEffective('yield', null)).toBe(false);
    expect(engineStatusLabel(true)).toBe('يعمل فعليّاً');
    expect(engineStatusColor(false)).toBe('#64748b');
  });
});

describe('scoreLabel + suited — server values as-is, absent is dash not zero', () => {
  it('shows the score exactly as the server sent it', () => {
    expect(scoreLabel(0.7825)).toBe('0.7825');
    expect(scoreLabel(0)).toBe('0'); // الصفر قيمة حقيقيّة تُعرَض
  });
  it('dashes non-numbers (no fabricated zero)', () => {
    expect(scoreLabel(null)).toBe('—');
    expect(scoreLabel(undefined)).toBe('—');
    expect(scoreLabel(Number.NaN)).toBe('—');
  });
  it('suited: warning (visible, ranked lower) not error; missing neutral', () => {
    expect(suitedLabel(true)).toBe('مناسب إقليميّاً');
    expect(suitedLabel(false)).toBe('غير مناسب إقليميّاً');
    expect(suitedColor(false)).toBe('#fdba74');
    expect(suitedColor(null)).toBe('#64748b');
    expect(suitedLabel(null)).toBe('—');
  });
});

describe('candidate drafts — mirrors server 422 rules, empty score is null not invented', () => {
  it('rejects empty list and missing crop_id', () => {
    expect(validateCandidateDrafts([])).toMatch('خياراً واحداً');
    expect(validateCandidateDrafts([emptyCandidateDraft()])).toMatch('crop_id');
  });
  it('rejects drought_score outside [0,1] or non-numeric', () => {
    const d = { ...emptyCandidateDraft(), crop_id: 'wheat', drought_score: '1.5' };
    expect(validateCandidateDrafts([d])).toMatch('[0,1]');
    expect(validateCandidateDrafts([{ ...d, drought_score: 'abc' }])).toMatch('[0,1]');
    expect(validateCandidateDrafts([{ ...d, drought_score: '0.8' }])).toBeNull();
    expect(validateCandidateDrafts([{ ...d, drought_score: '' }])).toBeNull();
  });
  it('builds server bodies: empty score → null, name_ar falls back to crop_id', () => {
    const body = buildCandidateBodies([
      { ...emptyCandidateDraft(), crop_id: ' wheat ', drought_score: '' },
    ])[0];
    expect(body.crop_id).toBe('wheat');
    expect(body.name_ar).toBe('wheat'); // نفس تعويض الخادم — صريحاً
    expect(body.drought_score).toBeNull();
    expect(body.profit_potential_level).toBe('unknown'); // صدق: مجهول حتى يُوثَّق
    const scored = buildCandidateBodies([
      { ...emptyCandidateDraft(), crop_id: 'sorghum', name_ar: 'ذرة رفيعة', drought_score: '0.9' },
    ])[0];
    expect(scored.name_ar).toBe('ذرة رفيعة');
    expect(scored.drought_score).toBe(0.9);
  });
});

describe('outcome draft — crop+field_id required; maturity requires measured yield', () => {
  const base = { ...emptyOutcomeDraft(), crop: 'wheat', field_id: 'f1' };
  it('requires crop and field_id (server OutcomeRecordRequest)', () => {
    expect(validateOutcomeDraft(emptyOutcomeDraft())).toMatch('crop');
    expect(validateOutcomeDraft({ ...emptyOutcomeDraft(), crop: 'wheat' })).toMatch('field_id');
    expect(validateOutcomeDraft(base)).toBeNull();
  });
  it('matured_within_lag=true demands actual yield (mirror of server 422)', () => {
    expect(validateOutcomeDraft({ ...base, matured_within_lag: true })).toMatch('غلّة فعليّة');
    expect(validateOutcomeDraft({ ...base, matured_within_lag: true, actual_yield: '2.4' })).toBeNull();
  });
  it('rejects negative/non-numeric yields (server: ge=0)', () => {
    expect(validateOutcomeDraft({ ...base, predicted_yield: '-1' })).toMatch('≥ 0');
    expect(validateOutcomeDraft({ ...base, actual_yield: 'abc' })).toMatch('≥ 0');
  });
  it('builds server body: blanks → null (nothing invented)', () => {
    const body = buildOutcomeInput({ ...base, predicted_yield: '3.5', accepted: true });
    expect(body).toEqual({
      crop: 'wheat', field_id: 'f1', farm_id: null, season_id: null, recommendation_id: null,
      predicted_yield_t_ha: 3.5, actual_yield_t_ha: null, accepted: true, matured_within_lag: false,
    });
  });
});

describe('dash — re-exported canonical helper', () => {
  it('dashes null/undefined/empty, keeps real zero', () => {
    expect(dash(null)).toBe('—');
    expect(dash(undefined)).toBe('—');
    expect(dash('')).toBe('—');
    expect(dash(0)).toBe('0');
  });
});
