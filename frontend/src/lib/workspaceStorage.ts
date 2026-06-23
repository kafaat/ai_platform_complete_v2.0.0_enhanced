// SAHOOL — lib/workspaceStorage.ts
// استرجاع تلقائيّ لإعدادات «مركز الخرائط» عبر localStorage (يبني على projectFile / GeoLibre):
// تُحفَظ الإعدادات عند كلّ تغيير، وتُستعاد تلقائيّاً عند فتح المركز — «العودة لنفس البيئة» دون
// حفظ يدويّ. عميل-فقط، بلا خادم. الحقل المختار يُدار في useFieldContext فلا يُكرَّر هنا.
import { parseMapView, type SahoolProjectWorkspace } from './projectFile';

/** إعدادات العرض المحفوظة محليّاً (دون selectedFieldId — يُدار في useFieldContext). */
export type WorkspaceSettings = Omit<SahoolProjectWorkspace, 'selectedFieldId'>;

const KEY = 'sahool-map-workspace-v1';

/** يقرأ الإعدادات المحفوظة (جزئيّة — قد تنقص حقول من نسخة أقدم). تعذّر/فساد ⇒ null.
 *  v2: لقطة عرض الخريطة (mapView) تُطهَّر عبر parseMapView (نطاقات صالحة) — أيّ
 *  فساد ⇒ null فيعود السلوك للملاءمة التلقائيّة (توافق رجعيّ مع بيانات v1 بلا mapView). */
export function loadWorkspace(): Partial<WorkspaceSettings> | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as unknown;
    if (!data || typeof data !== 'object') return null;
    const w = data as Partial<WorkspaceSettings>;
    // طهّر mapView من مخزن محليّ ربّما تالف/قديم — null إن غاب/فسد.
    return { ...w, mapView: parseMapView((w as { mapView?: unknown }).mapView) };
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
