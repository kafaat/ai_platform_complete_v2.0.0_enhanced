// قراءة مراجع بذار القمح من أوراق سجل الزراعة: حالات الحافّة التي لا يُستخرج لها معدل آليّ.
import { describe, expect, it } from 'vitest';
import type { Sheet } from 'read-excel-file/browser';
import { cellNumber, readWheatReferences, seedRatePerHa } from './wheatRegister';

type Cell = string | number | Date | null;
const HEADER = (area = 'مساحة القطاع (هكتار)', seed = 'كمية البذور (كغ)'): Cell[] =>
  [null, area, 'التاريخ', null, 'نوع البذور', null, seed];
const row = (area: Cell, day: Cell, variety: Cell, kg: Cell): Cell[] => [null, area, day, null, variety, null, kg];
const sheet = (name: string, data: Cell[][]): Sheet => ({ sheet: name, data: data as Sheet['data'] });
const d = (iso: string) => new Date(iso + 'T00:00:00Z');

describe('readWheatReferences', () => {
  it('sums same-variety days over one sector area in hectares', () => {
    const [ref] = readWheatReferences([sheet('م1ق3', [
      ['سجل الزراعة'], HEADER(),
      row(12.5, d('2026-10-22'), 'قمح حميري', 1000),
      row(null, d('2026-10-21'), 'حميري', 932),
    ])]);
    expect(ref).toEqual({ sheet: 'م1ق3', variety: 'حميري', hectares: 12.5, seedKg: 1932, rainfed: false, day: '2026-10-21' });
    expect(seedRatePerHa(ref)).toBe('154.56');
  });

  it('converts square metres and flags rainfed trial sheets', () => {
    const [ref] = readWheatReferences([sheet(' حميري - تجارب الري المطري ', [
      HEADER('مساحة القطاع متر مربع'), row(220, d('2026-09-16'), 'الحميري', 2.5),
    ])]);
    expect(ref.sheet).toBe('حميري - تجارب الري المطري');
    expect(ref.hectares).toBeCloseTo(0.022, 10);
    expect(ref.rainfed).toBe(true);
    expect(seedRatePerHa(ref)).toBe('113.64');
  });

  it('accepts م² in the area header', () => {
    expect(readWheatReferences([sheet('s', [HEADER('مساحة القطاع م²'), row(10000, null, 'بوني', 150)])])[0].hectares).toBe(1);
  });

  it('skips mixed-variety sheets', () => {
    expect(readWheatReferences([sheet('s', [HEADER(), row(5, null, 'علس', 100), row(null, null, 'حبيب', 100)])])).toEqual([]);
  });

  it('skips unknown, repeated, zero or textual area', () => {
    const cases: Cell[][][] = [
      [HEADER(), row(null, null, 'علس', 100)],
      [HEADER(), row(5, null, 'علس', 100), row(6, null, 'علس', 100)],
      [HEADER(), row(0, null, 'علس', 100)],
      [HEADER(), row('غير معروف', null, 'علس', 100)],
    ];
    for (const data of cases) expect(readWheatReferences([sheet('s', data)])).toEqual([]);
  });

  it('skips an area header without a known unit', () => {
    expect(readWheatReferences([sheet('s', [HEADER('مساحة القطاع (دونم)'), row(5, null, 'علس', 100)])])).toEqual([]);
    expect(readWheatReferences([sheet('s', [HEADER('مساحة القطاع'), row(5, null, 'علس', 100)])])).toEqual([]);
  });

  it('skips sheets with a missing or zero seed quantity on any lot', () => {
    expect(readWheatReferences([sheet('s', [HEADER(), row(5, null, 'علس', 100), row(null, null, 'علس', null)])])).toEqual([]);
    expect(readWheatReferences([sheet('s', [HEADER(), row(5, null, 'علس', 0)])])).toEqual([]);
  });

  it('skips non-wheat or unknown varieties and rows without a variety', () => {
    expect(readWheatReferences([sheet('s', [HEADER(), row(5, null, 'شعير', 100)])])).toEqual([]);
    expect(readWheatReferences([sheet('s', [HEADER(), row(5, null, 'علس', 100), row(null, d('2026-09-01'), null, null)])])).toEqual([]);
  });

  it('reads Eastern Arabic digits, the Arabic decimal separator and thousands grouping', () => {
    const [ref] = readWheatReferences([sheet('s', [HEADER(), row('١٢٫٥', null, 'حميري', '١٬٠٠٠'), row(null, null, 'حميري', '۹۳۲')])]);
    expect(ref.hectares).toBe(12.5);
    expect(ref.seedKg).toBe(1932);
  });

  it('normalises alef maqsura and diacritics in variety names', () => {
    expect(readWheatReferences([sheet('s', [HEADER(), row(1, null, 'بونى', 150)])])[0].variety).toBe('بوني');
    expect(readWheatReferences([sheet('s', [HEADER(), row(1, null, 'قمح  حَميري', 150)])])[0].variety).toBe('حميري');
  });

  it('applies the seed quantity unit and rejects bags of unknown weight', () => {
    expect(readWheatReferences([sheet('s', [HEADER(undefined, 'كمية البذور (طن)'), row(10, null, 'سمراء', 1.7)])])[0].seedKg).toBe(1700);
    expect(readWheatReferences([sheet('s', [HEADER(undefined, 'كمية البذور كيلوغرام'), row(10, null, 'سمراء', 1700)])])[0].seedKg).toBe(1700);
    expect(readWheatReferences([sheet('s', [HEADER(undefined, 'كمية البذور (كيس)'), row(10, null, 'سمراء', 34)])])).toEqual([]);
  });

  it('ignores sheets without the register header', () => {
    expect(readWheatReferences([sheet('ملخص', [['الإجمالي', 5, 6]])])).toEqual([]);
  });
});

describe('cellNumber', () => {
  it.each([
    [12.5, 12.5], ['12.5', 12.5], ['١٢٫٥', 12.5], ['۱۲', 12], ['1,250', 1250], ['١٬٢٥٠', 1250],
    ['12,5', null], ['12 كغ', null], ['-', null], ['', null], [null, null], [Number.NaN, null],
  ])('%j → %j', (input, expected) => {
    expect(cellNumber(input)).toBe(expected);
  });
});

describe('seedRatePerHa', () => {
  it('rounds to two decimals', () => {
    expect(seedRatePerHa({ seedKg: 2.5, hectares: 0.0237 })).toBe('105.49');
    expect(seedRatePerHa({ seedKg: 1700, hectares: 9.12 })).toBe('186.40');
  });
});
