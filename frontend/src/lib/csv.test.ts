import { describe, it, expect } from 'vitest';
import { csvCell, csvRow } from './csv';

// F-UI-38 / continuation-3: المُرمّز الآمن يحيّد حقن الصيغ ويهرّب RFC-4180.
describe('csvCell — formula-injection neutralization + RFC-4180', () => {
  it('يُسبِّق الخلايا المبدوءة بمُطلِق صيغة بفاصلة عليا', () => {
    expect(csvCell('=1+2')).toBe("'=1+2");
    expect(csvCell('+SUM(A1)')).toBe("'+SUM(A1)");
    expect(csvCell('-2')).toBe("'-2");
    expect(csvCell('@cmd')).toBe("'@cmd");
  });

  it('يهرّب الفاصلة/السطر/الاقتباس (اقتباس + مضاعفة)', () => {
    expect(csvCell('a,b')).toBe('"a,b"');
    expect(csvCell('line1\nline2')).toBe('"line1\nline2"');
    expect(csvCell('say "hi"')).toBe('"say ""hi"""');
  });

  it('يجمع التحييد والتهريب معاً (صيغة تحوي فاصلة)', () => {
    // يُسبَّق بفاصلة عليا ثمّ يُقتبَس لاحتوائه فاصلة.
    expect(csvCell('=HYPERLINK("x"),9')).toBe('"\'=HYPERLINK(""x""),9"');
  });

  it('القيم العاديّة والفارغة كما هي', () => {
    expect(csvCell('hello')).toBe('hello');
    expect(csvCell(42)).toBe('42');
    expect(csvCell(null)).toBe('');
    expect(csvCell(undefined)).toBe('');
  });

  it('csvRow يبني سطراً بفواصل', () => {
    expect(csvRow(['a', '=b', 'c,d'])).toBe('a,\'=b,"c,d"');
  });
});
