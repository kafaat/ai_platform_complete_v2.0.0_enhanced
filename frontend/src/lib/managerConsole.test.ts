import { describe, expect, it } from 'vitest';
import {
  costsByFieldTotal,
  dash,
  feasibilityTone,
  fmtNum,
  readinessSummary,
  roleChangeTone,
  settingScopeLabelAr,
  sharingScopeLabelAr,
  thirdPartyTypeLabelAr,
  whoCanTone,
  type FeasibilityResult,
  type RoleChangePreview,
} from './managerConsole';

describe('dash + fmtNum — null ⇒ «—» (لا قيمة مُلفَّقة)', () => {
  it('dash returns value or em-dash for missing', () => {
    expect(dash('x')).toBe('x');
    expect(dash(0)).toBe('0'); // صفر حقيقيّ يُعرَض (لا يُطمَس)
    expect(dash(null)).toBe('—');
    expect(dash(undefined)).toBe('—');
    expect(dash('')).toBe('—');
  });
  it('fmtNum formats numbers and dashes the missing', () => {
    expect(fmtNum(1234.5)).toBe('1,234.5');
    expect(fmtNum(null)).toBe('—');
    expect(fmtNum(undefined)).toBe('—');
    expect(fmtNum(NaN)).toBe('—');
  });
});

describe('known-value maps — neutral fallback, null ⇒ «—»', () => {
  it('settingScopeLabelAr maps known scopes, keeps unknown raw', () => {
    expect(settingScopeLabelAr('platform')).toBe('المنصّة');
    expect(settingScopeLabelAr('irrigation')).toBe('الريّ');
    expect(settingScopeLabelAr('weird')).toBe('weird'); // مجهول ⇒ خام
    expect(settingScopeLabelAr(null)).toBe('—');
  });
  it('thirdPartyTypeLabelAr maps known, dashes null, keeps unknown', () => {
    expect(thirdPartyTypeLabelAr('ministry')).toBe('جهة حكوميّة');
    expect(thirdPartyTypeLabelAr('x')).toBe('x');
    expect(thirdPartyTypeLabelAr(null)).toBe('—');
  });
  it('sharingScopeLabelAr maps read/read_write', () => {
    expect(sharingScopeLabelAr('read')).toBe('قراءة');
    expect(sharingScopeLabelAr('read_write')).toBe('قراءة وكتابة');
    expect(sharingScopeLabelAr('nope')).toBe('nope');
    expect(sharingScopeLabelAr(undefined)).toBe('—');
  });
});

describe('feasibilityTone — server figures decide, unknown neutral', () => {
  const base: FeasibilityResult = { supported: true, complete: true, net_profit: 100, profit_margin_pct: 40 };
  it('good margin profit ⇒ ok', () => {
    expect(feasibilityTone(base)).toBe('ok');
  });
  it('thin-margin profit ⇒ warn', () => {
    expect(feasibilityTone({ ...base, profit_margin_pct: 10 })).toBe('warn');
  });
  it('loss ⇒ danger', () => {
    expect(feasibilityTone({ ...base, net_profit: -50 })).toBe('danger');
  });
  it('incomplete (revenue only) ⇒ warn', () => {
    expect(feasibilityTone({ supported: true, complete: false })).toBe('warn');
  });
  it('unsupported / missing / disabled ⇒ neutral', () => {
    expect(feasibilityTone({ supported: false })).toBe('neutral');
    expect(feasibilityTone(null)).toBe('neutral');
    expect(feasibilityTone({ supported: true, disabled: true })).toBe('neutral');
  });
});

describe('roleChangeTone — escalation & safety-critical', () => {
  const esc: RoleChangePreview = { is_escalation: true, gained_safety_critical: [] };
  it('gaining safety-critical ⇒ danger', () => {
    expect(roleChangeTone({ ...esc, gained_safety_critical: ['PESTICIDE_APPROVE'] })).toBe('danger');
  });
  it('plain escalation ⇒ warn', () => {
    expect(roleChangeTone(esc)).toBe('warn');
  });
  it('error / missing ⇒ danger / neutral', () => {
    expect(roleChangeTone({ error_ar: 'دور غير صالح' })).toBe('danger');
    expect(roleChangeTone(null)).toBe('neutral');
    expect(roleChangeTone({ is_escalation: false })).toBe('neutral');
  });
});

describe('whoCanTone — safety-critical warns', () => {
  it('safety-critical ⇒ warn, else neutral', () => {
    expect(whoCanTone({ is_safety_critical: true })).toBe('warn');
    expect(whoCanTone({ is_safety_critical: false })).toBe('neutral');
    expect(whoCanTone(null)).toBe('neutral');
  });
});

describe('aggregations — pure', () => {
  it('costsByFieldTotal sums total_usd, tolerates missing', () => {
    expect(costsByFieldTotal([{ field_id: 'a', total_usd: 10 }, { field_id: 'b', total_usd: 5 }])).toBe(15);
    expect(costsByFieldTotal([])).toBe(0);
    expect(costsByFieldTotal(null)).toBe(0);
  });
  it('readinessSummary counts level + available/blocked', () => {
    expect(
      readinessSummary({ highest_complete_level: 3, available_recommendations: ['a', 'b'], blocked_recommendations: [{}] }),
    ).toEqual({ level: 3, available: 2, blocked: 1 });
    expect(readinessSummary(null)).toEqual({ level: 0, available: 0, blocked: 0 });
  });
});
