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
  geometry: any;
  area: number;
  crop: string;
}

// حقل خام (من useFields) → FieldOption مُطبَّع. id دائماً نصّ (للمطابقة المستقرّة).
export function toFieldOption(f: any): FieldOption {
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
