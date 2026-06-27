// ═══════════════════════════════════════════════════════════════
// vegetationApi.ts — دوالّ مجال الكساء النباتيّ (مُستخرَجة من api.ts)
// مسارات حيّة مطابقة لـvegetation-analysis-service: ربط حقيقيّ بلا تلفيق (إلّا
// MOCK_MODE الصريح عبر tryReal). تعتمد على عميل vegetationApi من apiClients وبيانات
// mock من apiMocks. api.ts يعيد التصدير عبر `export *` فيبقى كلّ import من
// '.../services/api' يعمل دون تغيير. السلوك محفوظ: نسخ حرفيّ للدوالّ.
// ═══════════════════════════════════════════════════════════════

import { tryReal, vegetationApi } from './apiClients';
import { mockTimeseries, mockVegetationAnalysis } from './apiMocks';

// ══════════════════════════════════════════════════════════════════
// VEGETATION SERVICE — مسارات حيّة مطابقة لـvegetation-analysis-service
// ربط حقيقيّ بلا تلفيق (إلّا MOCK_MODE الصريح). صدق المصدر: المؤشّرات تقديرات
// متوسّط-حقل من نطاقات تركيبيّة (real_data=false) — البكسلات الحقيقيّة في
// raster-service. أُصلحت المسارات/الأفعال لتطابق الخادم الفعليّ (GET /v1/*).
// ══════════════════════════════════════════════════════════════════

/** تحليل صورة + مؤشّرات + نشر NATS — GET /v1/analyze (الخادم يقبل GET بمعاملات) */
export const analyzeVegetation = (fieldId: string, _satellite = 'sentinel-2', tenantId = 'default') =>
  tryReal(
    () => vegetationApi.get('/v1/analyze', { params:{ field_id:fieldId, tenant_id:tenantId } }).then(r => r.data),
    () => mockVegetationAnalysis(fieldId)
  );




/** سلسلة زمنية NDVI — GET /v1/timeseries/{fieldId} */
export const fetchVegetationTimeseries = (fieldId: string, days = 30) =>
  tryReal(
    () => vegetationApi.get(`/v1/timeseries/${fieldId}`, { params:{ days } }).then(r => r.data),
    () => mockTimeseries(fieldId, days)
  );

/** NDVI الحالي — GET /v1/ndvi/current/{fieldId} */
export const fetchCurrentNDVI = (fieldId: string) =>
  tryReal(
    () => vegetationApi.get(`/v1/ndvi/current/${fieldId}`).then(r => r.data),
    () => ({ field_id:fieldId, ndvi:{ current:0.62 }, classification:{ level:'good', label_ar:'جيد', color:'#65a30d' } })
  );
