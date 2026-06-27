// ═══════════════════════════════════════════════════════════════
// apiMocks.ts — بيانات mock مُستخرَجة من api.ts (تُستهلَك عبر tryReal في MOCK_MODE فقط)
// لا منطق شبكة هنا: حقول/طقس/تربة/كساء نباتيّ تركيبيّة لوضع التجريب الصريح.
// وحدات المجال (vegetationApi/weatherApi/soilApi) تستورد ما يلزمها من هنا، وapi.ts
// يستورد MOCK_FIELDS لبناء MOCK_DASHBOARD. السلوك محفوظ: نسخ حرفيّ للبيانات/الدوالّ.
// ═══════════════════════════════════════════════════════════════

export const MOCK_FIELDS = [
  { field_id:'field_01', name:'حقل وادي سبأ',        area:23.5, crop:'قمح صلب',   ndvi:0.72, stage:'ملء الحبوب', gdd:960,  yield:2.8 },
  { field_id:'field_02', name:'حقل البيضاء الشمالي', area:32.0, crop:'شعير',       ndvi:0.58, stage:'نمو خضري',  gdd:825,  yield:2.5 },
  { field_id:'field_03', name:'حقل البيضاء الجنوبي', area:18.7, crop:'ذرة صفراء',  ndvi:0.44, stage:'تزهير',     gdd:980,  yield:3.9 },
  { field_id:'field_04', name:'حقل رداع الغربي',     area:41.3, crop:'طماطم',      ndvi:0.66, stage:'ثمرة',      gdd:780,  yield:4.2 },
  { field_id:'field_05', name:'حقل ذي السفال',       area:28.9, crop:'قمح صلب',   ndvi:0.74, stage:'ملء الحبوب', gdd:1020, yield:3.1 },
  { field_id:'field_06', name:'حقل عتمة الشرقي',    area:37.5, crop:'شعير',       ndvi:0.51, stage:'نمو خضري',  gdd:792,  yield:2.4 },
  { field_id:'field_07', name:'حقل الرياشية',        area:22.1, crop:'خضروات',     ndvi:0.55, stage:'حصاد',      gdd:660,  yield:5.5 },
  { field_id:'field_08', name:'حقل ذي ناعم',         area:45.0, crop:'بطاطس',      ndvi:0.61, stage:'درنات',     gdd:680,  yield:6.8 },
];

export const MOCK_WEATHER_TODAY = { tmax:31, tmin:17, tmean:24, humidity_pct:52, rainfall_mm:0, et0_mm:4.2, et0:4.2, gdd:14, wind_speed_kmh:12, irrigation_needed:true, heat_stress:false };

export function mockWeatherDays(n: number) {
  return Array.from({length:n},(_,i) => {
    const d = new Date(); d.setDate(d.getDate()-n+i+1);
    return { date:d.toISOString().split('T')[0], tmax:28+Math.random()*6, tmin:14+Math.random()*5, tmean:21+Math.random()*4, rain:+(Math.random()*3).toFixed(2), et0:+(3.5+Math.random()*2).toFixed(2), gdd:+(8+Math.random()*8).toFixed(1), rainfall_mm:+(Math.random()*3).toFixed(2) };
  });
}

export function mockSoilData(fieldId: string) {
  const s = Math.abs(fieldId.split('').reduce((a,c) => a+c.charCodeAt(0),0)) % 100;
  return { field_id:fieldId, ph:+(6+s%28/20).toFixed(1), ec_ds_m:+(0.3+s%40/20).toFixed(2), moisture_pct:+(20+s%55).toFixed(1), nitrogen_mg_kg:+(12+s%60).toFixed(1), phosphorus_mg_kg:+(6+s%35).toFixed(1), potassium_mg_kg:+(40+s%120).toFixed(1), organic_matter_pct:+(0.8+s%28/10).toFixed(2), texture:'مزيجية', health:{ status:'good', status_ar:'جيد', color:'#65a30d' } };
}

export function mockVegetationAnalysis(fieldId: string) {
  return {
    field_id:fieldId, satellite:'sentinel-2', cloud_coverage:5,
    indices:{ ndvi:0.72, evi:0.61, savi:0.45, ndwi:0.18, ndmi:0.22, gndvi:0.68, lai:3.82 },
    classification:{ level:'good', label_ar:'جيد', color:'#65a30d' },
    nats_event:{ published:false, subject:`sahool.tenant.default.satellite.ndvi.computed` },
    analyzed_at:new Date().toISOString(),
  };
}

export function mockTimeseries(fieldId: string, days: number) {
  const series = Array.from({length:days},(_,i) => {
    const d = new Date(); d.setDate(d.getDate()-days+i+1);
    return { date:d.toISOString().split('T')[0], ndvi:+(0.45+Math.sin(i/8)*0.15+Math.random()*0.04).toFixed(4), evi:+(0.38+Math.sin(i/8)*0.12+Math.random()*0.03).toFixed(4), lai:+(2+Math.sin(i/8)*1.2+Math.random()*0.3).toFixed(2) };
  });
  return { field_id:fieldId, period_days:days, timeseries:series, data:series, statistics:{ ndvi_mean:0.58, slope:0.001, r_squared:0.72, trend_direction:'stable' } };
}
