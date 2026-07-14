import { describe, it, expect } from 'vitest';
import { assertReadOnlySelect, MAX_RESULT_ROWS } from './duckdb';

// F-UI-33/F-UI-34: مساحة SQL المحلّيّة تقبل استعلام قراءة واحداً فقط. الحارس يرفض DDL/DML/
// COPY/ATTACH/… والبيانات المتعدّدة، ويقبل SELECT/WITH النظيف.
describe('assertReadOnlySelect', () => {
  it('يقبل SELECT بسيطاً ويُعيده منظّفاً من الفاصلة الختاميّة', () => {
    expect(assertReadOnlySelect('SELECT * FROM fields;')).toBe('SELECT * FROM fields');
    expect(assertReadOnlySelect('  select id, name from fields where area > 5  ')).toContain('select id, name');
  });

  it('يقبل WITH (CTE) للقراءة', () => {
    expect(assertReadOnlySelect('WITH t AS (SELECT 1 AS n) SELECT n FROM t')).toContain('WITH t AS');
  });

  it('يرفض DDL/DML وبقيّة البيانات المُعدِّلة/المُديرة', () => {
    for (const q of [
      'DROP TABLE fields',
      'DELETE FROM fields',
      'UPDATE fields SET area = 0',
      'INSERT INTO fields VALUES (1)',
      'CREATE TABLE x (a INT)',
      'ALTER TABLE fields ADD COLUMN z INT',
      "ATTACH 'x.db'",
      "COPY fields TO 'x.csv'",
      "INSTALL httpfs",
      "LOAD httpfs",
      'PRAGMA database_list',
    ]) {
      expect(() => assertReadOnlySelect(q), q).toThrow();
    }
  });

  it('يرفض البيانات المتعدّدة (حقن عبر ; )', () => {
    expect(() => assertReadOnlySelect('SELECT 1; DROP TABLE fields')).toThrow(/بيان واحد/);
  });

  it('يرفض الاستعلام الفارغ أو غير-SELECT', () => {
    expect(() => assertReadOnlySelect('   ')).toThrow();
    expect(() => assertReadOnlySelect('EXPLAIN SELECT 1')).toThrow(/SELECT أو WITH/);
  });

  it('لا يُخدَع بتعليق يُخفي DROP', () => {
    expect(() => assertReadOnlySelect('SELECT 1 -- ok\n; DROP TABLE fields')).toThrow();
  });

  it('سقف الصفوف معرّف ومحدود', () => {
    expect(MAX_RESULT_ROWS).toBeGreaterThan(0);
    expect(MAX_RESULT_ROWS).toBeLessThanOrEqual(100_000);
  });
});
