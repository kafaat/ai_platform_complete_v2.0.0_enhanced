// fields.ts — تطبيع خيارات الحقل (مصدر واحد للحقيقة).
// كان تحويل الحقل الخام → {id,name,…} يُعاد كتابته في ~8 شاشات بقواعد متباينة
// (أيّ مفتاح يفوز، تطبيع id بـString، احتياط الاسم). وُحِّد هنا. الشاشات تأخذ
// ما تحتاجه من الحقول المشتركة (الخريطة تستخدم geometry/lat/lon؛ الأقمار
// تستخدم area/crop؛ البقيّة id/name فقط).

export interface FieldOption {
  id: string;
  name: string;
  lat: number | null;
  lon: number | null;
  // هندسة تمرّ كما هي من الخادم (قد تكون غائبة/جزئيّة) ⇒ unknown، لا any.
  geometry: unknown;
  area: number;
  crop: string;
}

// الحقل الخام كما يصل من useFields: مفاتيح متباينة بين الخدمات (field_id/id،
// name_ar/name/field_code، lat/centroid_lat، area_ha/area...). كلّها اختياريّة،
// والقيم العدديّة قد تصل نصّاً من الخادم (لذا string | number ثمّ Number(...)).
export interface RawField {
  field_id?: string | number;
  id?: string | number;
  name_ar?: string;
  name?: string;
  field_code?: string;
  lat?: number | null;
  centroid_lat?: number | null;
  lon?: number | null;
  centroid_lon?: number | null;
  geometry?: unknown;
  area_ha?: string | number;
  area?: string | number;
  crop?: string;
}

// حقل خام (من useFields) → FieldOption مُطبَّع. id دائماً نصّ (للمطابقة المستقرّة).
export function toFieldOption(f: RawField): FieldOption {
  return {
    id: String(f.field_id ?? f.id),
    name: String(f.name_ar ?? f.name ?? f.field_code ?? f.field_id ?? 'حقل'),
    lat: f.lat ?? f.centroid_lat ?? null,
    lon: f.lon ?? f.centroid_lon ?? null,
    geometry: f.geometry,
    area: Number(f.area_ha ?? f.area ?? 0),
    crop: String(f.crop ?? '—'),
  };
}

// resolveActiveFieldId — يختار «الحقل النشط» المشترك: المُختار إن كان لا يزال
// موجوداً ضمن الخيارات، وإلّا أوّل حقل (افتراض موحّد عبر الشاشات). يعالج الحذف
// أو تغيّر المستأجِر (id مخزَّن لم يَعُد موجوداً) ⇒ يسقط لأوّل حقل لا يتجمّد على
// اختيار ميّت. نقيّ (لا React/تخزين) ⇒ قابل للاختبار. يُرجِع '' إن لا حقول.
export function resolveActiveFieldId(
  options: ReadonlyArray<{ id: string }>,
  selectedId: string | null | undefined,
): string {
  if (selectedId && options.some((o) => o.id === selectedId)) return selectedId;
  return options[0]?.id ?? '';
}


export type FieldViewSelectionReason = 'route' | 'stored' | 'fallback' | 'empty';

export interface FieldViewSelectionResult {
  fieldId: string;
  reason: FieldViewSelectionReason;
  routeFieldIsInvalid: boolean;
  storedFieldIsInvalid: boolean;
}

export function isKnownFieldId(options: ReadonlyArray<{ id: string }>, fieldId: string | null | undefined): boolean {
  return Boolean(fieldId && options.some((o) => o.id === fieldId));
}

// Professional FieldView resolver: deep-link wins when valid, then persisted
// session choice, then deterministic fallback to the first available field.
// Invalid route/store ids are surfaced explicitly for UX and audit/debugging.
export function resolveFieldViewSelection(params: {
  options: ReadonlyArray<{ id: string }>;
  storedFieldId?: string | null;
  routeFieldId?: string | null;
}): FieldViewSelectionResult {
  const { options, storedFieldId, routeFieldId } = params;
  const route = routeFieldId ? String(routeFieldId) : null;
  const stored = storedFieldId ? String(storedFieldId) : null;

  const routeKnown = isKnownFieldId(options, route);
  if (routeKnown && route) {
    return {
      fieldId: route,
      reason: 'route',
      routeFieldIsInvalid: false,
      storedFieldIsInvalid: Boolean(stored && !isKnownFieldId(options, stored)),
    };
  }

  const storedKnown = isKnownFieldId(options, stored);
  if (storedKnown && stored) {
    return {
      fieldId: stored,
      reason: 'stored',
      routeFieldIsInvalid: Boolean(route && !routeKnown),
      storedFieldIsInvalid: false,
    };
  }

  const fallback = options[0]?.id ?? '';
  return {
    fieldId: fallback,
    reason: fallback ? 'fallback' : 'empty',
    routeFieldIsInvalid: Boolean(route && !routeKnown),
    storedFieldIsInvalid: Boolean(stored && !storedKnown),
  };
}

export function readFieldIdFromSearch(search: string): string | null {
  const params = new URLSearchParams(search);
  return params.get('field_id') ?? params.get('fieldId');
}

export function writeFieldIdToSearch(search: string, fieldId: string | null | undefined): string {
  const params = new URLSearchParams(search);
  params.delete('fieldId');
  if (fieldId) params.set('field_id', fieldId);
  else params.delete('field_id');
  const next = params.toString();
  return next ? `?${next}` : '';
}
