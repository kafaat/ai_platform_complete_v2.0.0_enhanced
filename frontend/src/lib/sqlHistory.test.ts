// اختبارات sqlHistory — تثبّت سقف الـ10، إزالة التكرار (نقل للمقدّمة)، والتعامل
// الصامت مع تخزين فارغ/فاسد (⇒ []). عميل-فقط (localStorage).
import { beforeEach, describe, expect, it } from 'vitest';
import { loadHistory, pushHistory } from './sqlHistory';

const KEY = 'sahool-sql-history-v1';

describe('sqlHistory', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('يعيد [] حين التخزين فارغ', () => {
    expect(loadHistory()).toEqual([]);
  });

  it('يعيد [] حين التخزين فاسد (ليس JSON صالحاً)', () => {
    localStorage.setItem(KEY, '{ not json');
    expect(loadHistory()).toEqual([]);
  });

  it('يعيد [] حين البيانات ليست مصفوفة', () => {
    localStorage.setItem(KEY, JSON.stringify({ a: 1 }));
    expect(loadHistory()).toEqual([]);
  });

  it('يصفّي القيَم غير النصّيّة من مصفوفة مختلطة', () => {
    localStorage.setItem(KEY, JSON.stringify(['SELECT 1', 42, null, 'SELECT 2']));
    expect(loadHistory()).toEqual(['SELECT 1', 'SELECT 2']);
  });

  it('يضيف استعلاماً للمقدّمة (الأحدث أوّلاً)', () => {
    pushHistory('SELECT 1');
    pushHistory('SELECT 2');
    expect(loadHistory()).toEqual(['SELECT 2', 'SELECT 1']);
  });

  it('يتجاهل الاستعلام الفارغ/المسافات فقط', () => {
    pushHistory('SELECT 1');
    expect(pushHistory('   ')).toEqual(['SELECT 1']);
    expect(loadHistory()).toEqual(['SELECT 1']);
  });

  it('يقصّ المسافات الطرفيّة قبل الحفظ', () => {
    pushHistory('  SELECT 1  ');
    expect(loadHistory()).toEqual(['SELECT 1']);
  });

  it('يزيل التكرار وينقل المطابق للمقدّمة', () => {
    pushHistory('SELECT a');
    pushHistory('SELECT b');
    pushHistory('SELECT a');
    expect(loadHistory()).toEqual(['SELECT a', 'SELECT b']);
  });

  it('يحدّ السقف عند 10 (الأقدم يسقط)', () => {
    for (let i = 1; i <= 12; i++) pushHistory(`SELECT ${i}`);
    const h = loadHistory();
    expect(h).toHaveLength(10);
    expect(h[0]).toBe('SELECT 12');
    expect(h[9]).toBe('SELECT 3');
    expect(h).not.toContain('SELECT 1');
    expect(h).not.toContain('SELECT 2');
  });

  it('pushHistory يُعيد نفس ما يحفظه (الأحدث أوّلاً)', () => {
    expect(pushHistory('SELECT x')).toEqual(['SELECT x']);
    expect(pushHistory('SELECT y')).toEqual(['SELECT y', 'SELECT x']);
  });
});
