import { describe, expect, it } from 'vitest';
import {
  confidenceBadge,
  confidenceComponentFacts,
  cropsRows,
  depthRows,
  fmtNum,
  grossFacts,
  inputNameAr,
  inputNamesAr,
  moistureDecisionColor,
  moistureFacts,
  parseMeasure,
  parsePctToFraction,
  pctFromFraction,
  soilTypeRows,
  subsampleFacts,
  unsupportedMessage,
} from './irrigationDecisionAids';

describe('fmtNum / pctFromFraction — null ⇒ «—» honestly', () => {
  it('formats finite numbers and dashes the rest', () => {
    expect(fmtNum(1.256, 2)).toBe('1.26');
    expect(fmtNum(null)).toBe('—');
    expect(fmtNum(Number.NaN)).toBe('—');
  });
  it('renders server fractions as percent, dash when absent', () => {
    expect(pctFromFraction(0.756)).toBe('76٪');
    expect(pctFromFraction(1, 0)).toBe('100٪');
    expect(pctFromFraction(null)).toBe('—');
  });
});

describe('parseMeasure / parsePctToFraction — user input, no assumptions', () => {
  it('parses numbers, empty/garbage ⇒ null', () => {
    expect(parseMeasure(' 12.5 ')).toBe(12.5);
    expect(parseMeasure('')).toBeNull();
    expect(parseMeasure('abc')).toBeNull();
  });
  it('converts percent text to server fraction (unit conversion only)', () => {
    expect(parsePctToFraction('20')).toBe(0.2);
    expect(parsePctToFraction('')).toBeNull();
  });
});

describe('confidenceBadge — server levels only, unknown neutral verbatim', () => {
  it('maps the four confidence_engine levels case-insensitively', () => {
    expect(confidenceBadge('high').label_ar).toBe('ثقة عالية');
    expect(confidenceBadge('HIGH').color).toBe('#86efac');
    expect(confidenceBadge('very_low').color).toBe('#fca5a5');
  });
  it('passes unknown level text through with neutral color (no invented verdict)', () => {
    expect(confidenceBadge('weird')).toEqual({ label_ar: 'weird', color: '#64748b' });
    expect(confidenceBadge(null).label_ar).toBe('—');
  });
});

describe('moistureDecisionColor — irrigate/monitor/safe, unknown neutral', () => {
  it('colors known server decisions', () => {
    expect(moistureDecisionColor('irrigate')).toBe('#fca5a5');
    expect(moistureDecisionColor('monitor')).toBe('#fdba74');
    expect(moistureDecisionColor('safe')).toBe('#86efac');
  });
  it('is neutral for unknown/missing', () => {
    expect(moistureDecisionColor('odd')).toBe('#64748b');
    expect(moistureDecisionColor(null)).toBe('#64748b');
  });
});

describe('inputNameAr(s) — aggregation input labels, unknown key verbatim', () => {
  it('labels known aggregation inputs', () => {
    expect(inputNameAr('et0')).toBe('ET₀');
    expect(inputNameAr('soil_moisture')).toBe('رطوبة التربة');
  });
  it('keeps unknown keys as-is and tolerates missing arrays', () => {
    expect(inputNamesAr(['ndvi', 'xyz'])).toEqual(['NDVI', 'xyz']);
    expect(inputNamesAr(null)).toEqual([]);
  });
});

describe('confidenceComponentFacts — server components as percents', () => {
  it('emits one fact per present component', () => {
    const facts = confidenceComponentFacts({
      confidence: { score: 0.8, level: 'high', components: { cloud: 1, temporal: 0.95, coverage: 0.5, source: 0.5 } },
    });
    expect(facts).toHaveLength(4);
    expect(facts[0]).toEqual({ label: 'سحب', value: '100٪' });
  });
  it('is empty without components', () => {
    expect(confidenceComponentFacts(null)).toEqual([]);
    expect(confidenceComponentFacts({ reasons_ar: [] })).toEqual([]);
  });
});

describe('moistureFacts — ok=false ⇒ [], calibrated flag is server verdict', () => {
  it('builds facts from a real-shaped ok response', () => {
    const facts = moistureFacts({
      ok: true, rwc_pct: 57.1, vwc_pct: 20, theta_fc: 0.4, theta_wp: 0.125,
      soil_type_ar: 'طميّة', calibrated: false, decision: 'irrigate',
    });
    expect(facts.find((f) => f.label === 'المحتوى النسبي RWC')?.value).toBe('57.1٪');
    expect(facts.find((f) => f.label === 'المعايرة')?.value).toContain('غير معايَرة');
  });
  it('is empty for error/missing responses', () => {
    expect(moistureFacts({ ok: false, error_ar: 'خطأ' })).toEqual([]);
    expect(moistureFacts(null)).toEqual([]);
  });
});

describe('grossFacts — server-computed gross passes through', () => {
  it('shows net/gross/volume/efficiency/energy from the response', () => {
    const facts = grossFacts({
      net_mm: 25, gross_mm: 27.78, gross_m3_ha: 277.8,
      application_efficiency: 0.9, method: 'drip', pressurized: true, calibrated: false,
    });
    expect(facts.find((f) => f.label === 'الإجمالي المسحوب')?.value).toBe('27.8 مم');
    expect(facts.find((f) => f.label === 'كفاءة التطبيق')?.value).toBe('90٪');
    expect(facts.find((f) => f.label === 'الطاقة')?.value).toContain('مضغوط');
  });
  it('is empty for missing response', () => {
    expect(grossFacts(null)).toEqual([]);
  });
});

describe('soilTypeRows / cropsRows — server dict/list as-is, missing ⇒ []', () => {
  it('flattens the soil_types dict keeping API keys', () => {
    const rows = soilTypeRows({
      soil_types: { sand: { name_ar: 'رمليّة', theta_fc: 0.2, theta_wp: 0.075 } },
      note_ar: 'قيم نوعيّة',
    });
    expect(rows).toHaveLength(1);
    expect(rows[0].key).toBe('sand');
    expect(rows[0].name_ar).toBe('رمليّة');
  });
  it('is empty when the server sent nothing', () => {
    expect(soilTypeRows(null)).toEqual([]);
    expect(cropsRows(null)).toEqual([]);
    expect(cropsRows({ crops: [{ crop: 'wheat', name_ar: 'قمح' }] })).toHaveLength(1);
  });
});

describe('sampling helpers — supported=false ⇒ message only, no facts', () => {
  it('emits subsample facts only when supported', () => {
    const facts = subsampleFacts({ supported: true, area_ha: 3, subsamples: 17 });
    expect(facts.find((f) => f.label === 'عيّنات فرعيّة')?.value).toBe('~17');
    expect(subsampleFacts({ supported: false, message_ar: 'أدخل مساحة صحيحة بالهكتار.' })).toEqual([]);
  });
  it('passes the server unsupported message verbatim', () => {
    expect(unsupportedMessage({ supported: false, message_ar: 'أدخل مساحة صحيحة بالهكتار.' }))
      .toBe('أدخل مساحة صحيحة بالهكتار.');
    expect(unsupportedMessage({ supported: true })).toBeNull();
    expect(unsupportedMessage(null)).toBeNull();
  });
  it('returns depth purpose rows as the server ordered them', () => {
    const rows = depthRows({
      purpose: 'general',
      depth_ar: '15-30 سم',
      all_purposes_ar: [{ purpose: 'general', depth_ar: '15-30 سم', for_ar: 'احتياجات الأسمدة العامّة' }],
    });
    expect(rows).toHaveLength(1);
    expect(depthRows(null)).toEqual([]);
  });
});
