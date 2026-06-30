// fieldMapView.ts — حفظ/استرجاع «مشهد الخريطة» (zoom + مركز) لكلّ حقل.
// عند إنشاء حقل نلتقط مستوى التكبير ومركز الخريطة، وعند فتحه من «حقولي» نطير
// إلى المشهد نفسه بدل ضبط الإطار العامّ. تخزين جهة-العميل (localStorage) بنفس نمط
// weatherPreferences — لا يلمس مسار إنشاء الحقل الحرج في الخلفيّة (لا كسر).
// fail-safe: غياب window/localStorage أو قيمة تالفة ⇒ يُتجاهَل بهدوء (لا استثناء).

export interface FieldMapView {
  zoom: number;
  lat: number;
  lng: number;
}

const KEY = 'sahool.field.map.view.v1';

function isFiniteNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

function readAll(): Record<string, FieldMapView> {
  if (typeof window === 'undefined' || !window.localStorage) return {};
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, FieldMapView>) : {};
  } catch {
    return {};
  }
}

/** يحفظ مشهد الخريطة لحقل. يتجاهل القيم غير الصالحة أو غياب التخزين. */
export function saveFieldMapView(fieldId: string | null | undefined, view: FieldMapView): void {
  if (!fieldId) return;
  if (!isFiniteNum(view.zoom) || !isFiniteNum(view.lat) || !isFiniteNum(view.lng)) return;
  if (Math.abs(view.lat) > 90 || Math.abs(view.lng) > 180) return;
  if (typeof window === 'undefined' || !window.localStorage) return;
  try {
    const all = readAll();
    all[fieldId] = {
      zoom: Math.round(view.zoom * 100) / 100,
      lat: Number(view.lat.toFixed(7)),
      lng: Number(view.lng.toFixed(7)),
    };
    window.localStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    /* تجاهل (حصّة ممتلئة/خصوصيّة) — ميزة عرض اختياريّة لا تُفشِل شيئاً */
  }
}

/** يقرأ مشهد الخريطة المحفوظ لحقل، أو null إن لم يوجد/تالف. */
export function readFieldMapView(fieldId: string | null | undefined): FieldMapView | null {
  if (!fieldId) return null;
  const v = readAll()[fieldId];
  if (!v || !isFiniteNum(v.zoom) || !isFiniteNum(v.lat) || !isFiniteNum(v.lng)) return null;
  return v;
}
