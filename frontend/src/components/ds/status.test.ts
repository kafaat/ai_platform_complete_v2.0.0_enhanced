// اختبارات تسميات/نغمات الحالات الموحّدة (DS) — تطابق الخرائط المُعلَنة فعلاً،
// والاحتياط للحالة المجهولة، وعدم الحساسيّة لحالة الأحرف.
import { describe, it, expect } from 'vitest';
import {
  taskStatusAr,
  taskStatusTone,
  equipStatusAr,
  equipStatusTone,
} from './status';

describe('taskStatusAr / taskStatusTone', () => {
  it('يطابق التسميات العربيّة المُعلَنة', () => {
    expect(taskStatusAr('pending')).toBe('مجدولة');
    expect(taskStatusAr('in_progress')).toBe('جارية');
    expect(taskStatusAr('completed')).toBe('مكتملة');
    expect(taskStatusAr('cancelled')).toBe('ملغاة');
  });

  it('غير حسّاس لحالة الأحرف ويُرجِع القيمة الخام للحالة المجهولة', () => {
    expect(taskStatusAr('COMPLETED')).toBe('مكتملة');
    expect(taskStatusAr('weird')).toBe('weird');
    expect(taskStatusAr(undefined)).toBe('—');
  });

  it('يربط الحالة بالنغمة الصحيحة', () => {
    expect(taskStatusTone('completed')).toBe('ok');
    expect(taskStatusTone('in_progress')).toBe('warn');
    expect(taskStatusTone('cancelled')).toBe('danger');
    expect(taskStatusTone('pending')).toBe('info');
    expect(taskStatusTone('unknown')).toBe('info'); // افتراضيّ
  });
});

describe('equipStatusAr / equipStatusTone', () => {
  it('active وoperational كلاهما «تعمل» بنغمة ok', () => {
    expect(equipStatusAr('active')).toBe('تعمل');
    expect(equipStatusAr('operational')).toBe('تعمل');
    expect(equipStatusTone('active')).toBe('ok');
    expect(equipStatusTone('operational')).toBe('ok');
  });

  it('maintenance=warn و broken/down=danger', () => {
    expect(equipStatusAr('maintenance')).toBe('صيانة');
    expect(equipStatusTone('maintenance')).toBe('warn');
    expect(equipStatusAr('broken')).toBe('معطّلة');
    expect(equipStatusTone('broken')).toBe('danger');
    expect(equipStatusTone('down')).toBe('danger');
  });

  it('الحالة المجهولة: القيمة الخام بنغمة neutral', () => {
    expect(equipStatusAr('zzz')).toBe('zzz');
    expect(equipStatusAr(undefined)).toBe('—');
    expect(equipStatusTone('zzz')).toBe('neutral');
  });
});
