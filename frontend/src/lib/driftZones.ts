// driftZones.ts — اشتقاق مناطق حسّاسة (الحقول المجاورة) لتقييم انجراف الرشّ (V79-UI).
//
// يبني مدخلات نقطة /wind/drift-risk من بيانات الحقول الموجودة: مركز كلّ حقل مجاور يصبح
// «منطقة حسّاسة» (نوع neighboring_field) إن كان ضمن نصف قطر. صدق: بلا مركز صالح ⇒ يُتخطّى
// (لا إحداثيّة مُختلَقة). مساعِدات نقيّة (بلا React/turf) لتُختبَر منفصلةً.

export interface FieldLike {
  id: string;
  name?: string;
  lat?: number | null;
  lon?: number | null;
  geometry?: unknown;
}

export interface SensitiveZoneInput {
  id: string;
  type: string;
  lat: number;
  lon: number;
}

export interface DriftExposedZone {
  id?: string;
  type?: string;
  distance_m?: number;
  bearing_deg?: number;
}

export interface DriftRiskResponse {
  field_id?: string;
  wind_from_deg?: number;
  wind_source?: string;
  status?: 'at_risk' | 'clear' | 'unknown';
  reason?: string;
  drift_azimuth_deg?: number;
  exposed_zones?: DriftExposedZone[];
  n_zones?: number;
  note_ar?: string;
}

function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

/** مركز الحقل [lat, lon] من lat/lon المباشرَين أو متوسّط حلقة الهندسة الخارجيّة. null لو تعذّر. */
export function centroidOf(field: FieldLike | undefined | null): { lat: number; lon: number } | null {
  if (!field) return null;
  if (isNum(field.lat) && isNum(field.lon)) return { lat: field.lat, lon: field.lon };
  const g = field.geometry as { type?: string; coordinates?: unknown } | undefined;
  if (!g || typeof g !== 'object') return null;
  let ring: unknown;
  if (g.type === 'Polygon') ring = (g.coordinates as unknown[])?.[0];
  else if (g.type === 'MultiPolygon') ring = ((g.coordinates as unknown[])?.[0] as unknown[])?.[0];
  if (!Array.isArray(ring) || ring.length < 3) return null;
  let sx = 0;
  let sy = 0;
  let n = 0;
  for (const p of ring as unknown[]) {
    if (Array.isArray(p) && isNum(p[0]) && isNum(p[1])) {
      sx += p[0] as number;
      sy += p[1] as number;
      n += 1;
    }
  }
  return n ? { lat: sy / n, lon: sx / n } : null;
}

/** مسافة كرويّة (كم) بين نقطتين — لتصفية الجوار. */
export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371;
  const dp = ((lat2 - lat1) * Math.PI) / 180;
  const dl = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dp / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** الحقول المجاورة (ضمن maxKm) كمناطق حسّاسة لتقييم الانجراف. يستبعد الحقل نفسه وبلا مركز. */
export function neighborZones(
  fields: FieldLike[] | undefined,
  currentFieldId: string | undefined | null,
  maxKm = 2,
): SensitiveZoneInput[] {
  const self = (fields ?? []).find((f) => f.id === currentFieldId);
  const c = centroidOf(self);
  if (!c || !fields) return [];
  const out: SensitiveZoneInput[] = [];
  for (const f of fields) {
    if (f.id === currentFieldId) continue;
    const fc = centroidOf(f);
    if (!fc) continue;
    if (haversineKm(c.lat, c.lon, fc.lat, fc.lon) <= maxKm) {
      out.push({ id: f.id, type: 'neighboring_field', lat: fc.lat, lon: fc.lon });
    }
  }
  return out;
}
