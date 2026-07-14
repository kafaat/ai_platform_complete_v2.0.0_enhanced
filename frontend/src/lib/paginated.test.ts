import { describe, it, expect } from 'vitest';
import { unwrapList } from './paginated';

// F5-06: المُغلّف يستوعب المصفوفة والمغلّف الجديد والقديم دون كسر، ويُظهِر الاقتطاع.
describe('unwrapList', () => {
  it('مصفوفة صِرفة → items بلا total/cursor', () => {
    expect(unwrapList<number>([1, 2, 3])).toEqual({ items: [1, 2, 3], total: null, nextCursor: null, truncated: false });
  });

  it('مغلّف {items,total,next_cursor} → قيَم كما هي + truncated', () => {
    const r = unwrapList<number>({ items: [1, 2], total: 10, next_cursor: 'c1', limit: 2 });
    expect(r.items).toEqual([1, 2]);
    expect(r.total).toBe(10);
    expect(r.nextCursor).toBe('c1');
    expect(r.truncated).toBe(true);
  });

  it('مغلّف قديم بمفتاح مُسمّى (tasks/alerts/…) → items', () => {
    expect(unwrapList<number>({ tasks: [1, 2] }).items).toEqual([1, 2]);
    expect(unwrapList<number>({ documents: [9] }).items).toEqual([9]);
  });

  it('total == items ⇒ غير مقتطَع', () => {
    expect(unwrapList<number>({ items: [1, 2], total: 2 }).truncated).toBe(false);
  });

  it('مدخل غير صالح → قائمة فارغة آمنة', () => {
    expect(unwrapList<number>(null).items).toEqual([]);
    expect(unwrapList<number>(undefined).items).toEqual([]);
    expect(unwrapList<number>(42).items).toEqual([]);
  });
});
