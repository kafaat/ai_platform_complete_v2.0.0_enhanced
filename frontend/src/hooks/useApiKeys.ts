// SAHOOL v9.0 — src/hooks/useApiKeys.ts — مفاتيح React Query المشتركة (leaf)
// وحدة ورقيّة (leaf): لا تستورد من useApi.ts ⇒ تتفاداها الوحدات المجزّأة الأخرى
// لاستيراد QK دون اعتماد دائريّ (useApi.ts يُعيد تصديرها للتوافق الخلفيّ).

// ── Query Keys ─────────────────────────────────────────────────
export const QK = {
  indicators:       (fid: string)        => ['indicators', fid],
  indicatorsCatalog:                        ['indicators', 'catalog'],
  allFieldsNdvi:    (tid: string)        => ['vegetation', 'all', tid],
  ndviCurrent:      (fid: string)        => ['vegetation', 'ndvi', fid],
  timeseries:       (fid: string, d: number) => ['vegetation', 'ts', fid, d],
  weatherForecast:  (lat: number, lon: number) => ['weather', 'forecast', lat, lon],
  weatherWofost:    (lat: number, lon: number, days: number) => ['weather', 'wofost', lat, lon, days],
  weatherHistory:   (lat: number, lon: number, days: number) => ['weather', 'history', lat, lon, days],
  soilParams:       (fid: string)        => ['soil', 'params', fid],
  soilNRec:         (fid: string)        => ['soil', 'nrec', fid],
  fields:           (tid: string)        => ['fields', tid],
  fieldDetail:      (tid: string, fid: string) => ['field-detail', tid, fid],
  fieldWorkspace:   (tid: string, fid: string) => ['field-workspace', tid, fid],
  farms:            (tid: string)        => ['farms', tid],
  tasks:            (fid?: string)       => ['tasks', fid ?? 'all'],
  activities:       (tid: string, fid: string) => ['activities', tid, fid],
  seasons:          (tid: string, fid: string) => ['seasons', tid, fid],
  irrigationAdvice: (tid: string, fid: string) => ['weather-advice', 'irrigation', tid, fid],
  diseaseRisk:      (tid: string, fid: string) => ['weather-advice', 'disease', tid, fid],
  fieldRecs:        (tid: string, fid: string) => ['field-recommendations', tid, fid],
  alerts:           (tid: string)        => ['alerts', tid],
  notifPrefs:       (tid: string)        => ['notifications', 'preferences', tid],
  indicatorGrid:    (fid: string, index: string, date: string) => ['indicator-grid', fid, index, date],
  fieldChange:      (fid: string, index: string, dateA: string, dateB: string) =>
                       ['field-change', fid, index, dateA, dateB],
  fieldTimeseries:  (fid: string, index: string, dates: string) =>
                       ['field-timeseries', fid, index, dates],
  prescription:     (fid: string, index: string, date: string, n: number, baseRate: number | null, strategy: string) =>
                       ['prescription', fid, index, date, n, baseRate ?? 'auto', strategy],
  savedPrescriptions: (tid: string, fid: string) => ['saved-prescriptions', tid, fid],
  costAnalytics:    (tid: string)        => ['analytics', 'costs', tid],
  yieldAnalysis:    (tid: string, fid: string, season: string) => ['analysis', 'yield', tid, fid, season],
  farmSummary:      (tid: string)        => ['reports', 'farm-summary', tid],
  fieldReport:      (tid: string, fid: string) => ['reports', 'field', tid, fid],
  seasonReport:     (tid: string, sid: string) => ['reports', 'season', tid, sid],
  // الأنظمة الجديدة (شاشات الويب)
  inventoryItems:   (tid: string)        => ['inventory', 'items', tid],
  inventoryExpiring:(tid: string, d: number) => ['inventory', 'expiring', tid, d],
  equipment:        (tid: string)        => ['equipment', tid],
  maintenance:      (tid: string, eid: string) => ['equipment', tid, 'maintenance', eid],
  devices:          (tid: string)        => ['devices', tid],
  deviceTelemetry:  (tid: string, id: string, n: number) => ['devices', 'telemetry', tid, id, n],
  fieldSoilMoisture:(tid: string, fid: string) => ['fields', 'soil-moisture', tid, fid],
  valves:           (tid: string)        => ['irrigation', 'valves', tid],
  schedules:        (tid: string, fid?: string) => ['irrigation', 'schedules', tid, fid ?? 'all'],
  masterData:       (tid: string, cat: string) => ['master-data', tid, cat],
  documents:        (tid: string, category?: string, fieldId?: string) =>
                       ['documents', tid, category ?? 'all', fieldId ?? 'all'],
  sharingKeys:      (tid: string, includeRevoked: boolean) =>
                       ['sharing', 'keys', tid, includeRevoked],
  health:                                   ['health', 'all'],
  labSamples:       (tid: string, fid?: string) => ['lab', 'samples', tid, fid ?? 'all'],
  labContext:       (tid: string, fid: string) => ['lab', 'context', tid, fid],
  productivityZones:(tid: string, fid: string, n: number) => ['productivity-zones', tid, fid, n],
  zoneSamplingPlan: (tid: string, fid: string, n: number) => ['zone-sampling-plan', tid, fid, n],
  dailyAiBrief:     (tid: string, fid: string) => ['daily-ai-brief', tid, fid],
} as const;
