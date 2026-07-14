// مُغلّف قوائم مُوحّد (F5-06): يستوعب أشكال استجابة القوائم الثلاثة دون كسر:
//   • مصفوفة صِرفة                       → items بلا total/cursor
//   • مغلّف {items,total,next_cursor,limit} → القيم كما هي
//   • مغلّف قديم بمفتاح مُسمّى {tasks|alerts|documents|results|data:[...]}
// يُعيد شكلاً واحداً {items,total,nextCursor,truncated} تستهلكه الواجهة، فتُظهِر
// العدّ/الاقتطاع حين يوفّرها الخادم دون افتراضٍ حين لا يفعل. مُقدّمةٌ متوافقة أماميّاً
// لترقيم الصفحات: حين تُعيد الخلفيّة المغلّف لاحقاً، تستهلكه الواجهة تلقائيّاً.

export interface Paginated<T> {
  items: T[];
  /** إجماليّ الصفوف على الخادم (إن وفّره) — يميّز «كلّ السجلّات» عن «أوّل صفحة». */
  total: number | null;
  /** مؤشّر الصفحة التالية (إن وفّره الخادم). */
  nextCursor: string | null;
  /** true إن دلّت البيانات على وجود المزيد (total > items أو وجود cursor). */
  truncated: boolean;
}

const ITEM_KEYS = ['items', 'tasks', 'alerts', 'documents', 'results', 'data', 'rows'] as const;

/** يُطبّع أيّ استجابة قائمة إلى {@link Paginated}. آمن على أيّ مدخل (يفشل إلى قائمة فارغة). */
export function unwrapList<T>(payload: unknown): Paginated<T> {
  if (Array.isArray(payload)) {
    return { items: payload as T[], total: null, nextCursor: null, truncated: false };
  }
  if (payload && typeof payload === 'object') {
    const obj = payload as Record<string, unknown>;
    let items: T[] = [];
    for (const k of ITEM_KEYS) {
      if (Array.isArray(obj[k])) { items = obj[k] as T[]; break; }
    }
    const total = typeof obj.total === 'number' ? obj.total : null;
    const nextCursor =
      typeof obj.next_cursor === 'string' ? obj.next_cursor
      : typeof obj.nextCursor === 'string' ? obj.nextCursor
      : null;
    const truncated = (total !== null && total > items.length) || nextCursor !== null;
    return { items, total, nextCursor, truncated };
  }
  return { items: [], total: null, nextCursor: null, truncated: false };
}
