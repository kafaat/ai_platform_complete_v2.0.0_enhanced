// SAHOOL — lib/workspaceStorage.ts
// استرجاع تلقائيّ لإعدادات «مركز الخرائط» عبر localStorage (يبني على projectFile / GeoLibre):
// تُحفَظ الإعدادات عند كلّ تغيير، وتُستعاد تلقائيّاً عند فتح المركز — «العودة لنفس البيئة» دون
// حفظ يدويّ. عميل-فقط، بلا خادم. الحقل المختار يُدار في useFieldContext فلا يُكرَّر هنا.
import type { SahoolProjectWorkspace } from './projectFile';

/** إعدادات العرض المحفوظة محليّاً (دون selectedFieldId — يُدار في useFieldContext). */
export type WorkspaceSettings = Omit<SahoolProjectWorkspace, 'selectedFieldId'>;

const KEY = 'sahool-map-workspace-v1';

/** يقرأ الإعدادات المحفوظة (جزئيّة — قد تنقص حقول من نسخة أقدم). تعذّر/فساد ⇒ null. */
export function loadWorkspace(): Partial<WorkspaceSettings> | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as unknown;
    return data && typeof data === 'object' ? (data as Partial<WorkspaceSettings>) : null;
  } catch {
    return null;
  }
}

/** يحفظ الإعدادات الحاليّة (best-effort: تجاهُل أيّ تعذّر تخزين — لا يكسر الواجهة). */
export function saveWorkspace(w: WorkspaceSettings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(w));
  } catch {
    /* تجاهُل — التخزين غير متاح (وضع خاصّ/ممتلئ) لا يؤثّر على الجلسة */
  }
}
