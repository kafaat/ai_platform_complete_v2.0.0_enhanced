// ═══════════════════════════════════════════════════════════════
// SAHOOL — تركيبات E2E هرمسيّة (طبقة اختبار Playwright فقط — لا بيانات وهميّة في
// التطبيق). 3 حقول يمنيّة بهندسة Polygon ([lng, lat] GeoJSON) على نمط إحداثيّات
// HubMapGL.test.tsx (حول lng≈44، lat≈15)، + حمولات تراكب دنيا (تنبيهات/أجهزة/طقس).
// تُخدَم عبر اعتراض الشبكة في e2e/support/seed.ts كي تكون الخريطة حتميّة.
// ═══════════════════════════════════════════════════════════════

// شكل الحقل كما تُرجعه GET /api/v1/fields (FieldSummary): field_id/name/geometry…
export interface FieldFixture {
  field_id: string;
  name: string;
  name_ar: string;
  crop: string;
  area_ha: number;
  centroid_lat: number;
  centroid_lon: number;
  geometry: { type: 'Polygon'; coordinates: number[][][] };
}

// مضلّع مربّع صغير (~0.05° ضلعاً) حول مركز معطى — حلقة GeoJSON مغلقة [lng, lat].
function squareAround(lng: number, lat: number, half = 0.05): number[][][] {
  return [[
    [lng - half, lat - half],
    [lng + half, lat - half],
    [lng + half, lat + half],
    [lng - half, lat + half],
    [lng - half, lat - half],
  ]];
}

// 3 حقول متباعدة (لا تتداخل مضلّعاتها) كي يكون كلّ حقل قابلاً للنقر منفرداً.
export const FIELDS: FieldFixture[] = [
  {
    field_id: 'fld-sanaa',
    name: 'حقل صنعاء',
    name_ar: 'حقل صنعاء',
    crop: 'قمح',
    area_ha: 12.5,
    centroid_lat: 15.35,
    centroid_lon: 44.20,
    geometry: { type: 'Polygon', coordinates: squareAround(44.20, 15.35) },
  },
  {
    field_id: 'fld-dhamar',
    name: 'حقل ذمار',
    name_ar: 'حقل ذمار',
    crop: 'ذرة',
    area_ha: 8.2,
    centroid_lat: 14.55,
    centroid_lon: 44.40,
    geometry: { type: 'Polygon', coordinates: squareAround(44.40, 14.55) },
  },
  {
    field_id: 'fld-ibb',
    name: 'حقل إب',
    name_ar: 'حقل إب',
    crop: 'بنّ',
    area_ha: 5.0,
    centroid_lat: 13.97,
    centroid_lon: 44.18,
    geometry: { type: 'Polygon', coordinates: squareAround(44.18, 13.97) },
  },
];

// تنبيهات نشطة مربوطة بحقول قائمة (field_id) كي تكون قابلة للعرض على الخريطة.
export const ALERTS = [
  {
    alert_id: 'alr-1',
    field_id: 'fld-sanaa',
    severity: 'critical',
    title_ar: 'إجهاد مائيّ',
    alert_type: 'water_stress',
    status: 'active',
  },
  {
    alert_id: 'alr-2',
    field_id: 'fld-dhamar',
    severity: 'warning',
    title_ar: 'آفة محتملة',
    alert_type: 'pest',
    status: 'active',
  },
];

// أجهزة مربوطة بحقول قائمة (field_id) — قابلة للعرض.
export const DEVICES = [
  {
    device_id: 'dev-1',
    field_id: 'fld-sanaa',
    name: 'مستشعر رطوبة',
    type: 'soil_moisture',
    online: true,
  },
  {
    device_id: 'dev-2',
    field_id: 'fld-ibb',
    name: 'محطّة طقس',
    type: 'weather_station',
    online: false,
  },
];

// طقس حاليّ (GET /api/v1/weather/current) — قيم دنيا صادقة.
export const WEATHER_CURRENT = {
  temperature_c: 27,
  humidity_pct: 45,
  wind_speed_ms: 3.2,
  weather_ar: 'صحو',
};

// توقّعات (GET /api/v1/weather/forecast) — يوم واحد يكفي للعرض.
export const WEATHER_FORECAST = {
  days: [
    { date: '2026-06-22', tmin: 18, tmax: 30, et0_mm: 5.1, precip_mm: 0 },
  ],
};
