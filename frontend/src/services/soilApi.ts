// ═══════════════════════════════════════════════════════════════
// soilApi.ts — دوالّ مجال التربة (مُستخرَجة من api.ts)
// صدق: soil-service غير منشورة (nginx يردّ 503 على /api/soil/) ولا مكافئ على المنصّة.
// هذه الدوالّ غير مُستهلَكة في أيّ واجهة؛ مُبقاة للـMOCK_MODE ولِما بعد نشر الخدمة.
// تعتمد على عميل soilApi/tryReal من apiClients وبيانات mock من apiMocks. api.ts يعيد
// التصدير عبر `export *` فيبقى كلّ import من '.../services/api' يعمل. السلوك محفوظ.
// ═══════════════════════════════════════════════════════════════

import { soilApi, tryReal } from './apiClients';
import { MOCK_FIELDS, mockSoilData } from './apiMocks';

// ══════════════════════════════════════════════════════════════════
// SOIL — صدق: خدمة soil-service غير منشورة (مُعلّقة في compose؛ nginx يردّ 503 على
// /api/soil/) ولا مكافئ لتركيب التربة على المنصّة. الدوالّ أدناه غير مُستهلَكة في
// أيّ واجهة (المكوّن الوحيد FarmAdvisoryReport يستعمل hooks مُعطّلة خلف FEATURE_FLAGS.soil
// مع حالة «بيانات التربة غير متاحة» الصادقة). مُبقاة للـMOCK_MODE ولِما بعد نشر
// soil-service بتنفيذ حقيقيّ؛ خارج MOCK_MODE تضرب /api/soil ⇒ 503 صادق (لا تلفيق).
// ══════════════════════════════════════════════════════════════════

export const fetchSoilData = (fieldId: string) =>
  tryReal(
    () => soilApi.get(`/soil/${fieldId}`).then(r => r.data),
    () => mockSoilData(fieldId)
  );

export const fetchAllSoilData = () =>
  tryReal(
    () => soilApi.get('/soil/all').then(r => r.data),
    () => ({ readings:MOCK_FIELDS.map(f => mockSoilData(f.field_id)), total:8 })
  );

export const fetchSoilWofostParams = (fieldId: string) =>
  tryReal(
    () => soilApi.get(`/soil/wofost_params/${fieldId}`).then(r => r.data),
    () => ({ rdmsol:1.2, soil_water_capacity_mm:150, wilting_point_pct:15, field_capacity_pct:35, suitable_for_wofost:true })
  );

export const fetchNitrogenRecommendation = (fieldId: string, targetYield = 5.0) =>
  tryReal(
    () => soilApi.get('/soil/nitrogen/recommendation', { params:{ field_id:fieldId, target_yield_t_ha:targetYield } }).then(r => r.data),
    () => ({ recommended_n_kg_ha:87.5, n_demand_kg_ha:125, n_available_kg_ha:37.5, method:'FAO adjusted', timing:'40% زراعة + 30% تفريع + 30% تطاول' })
  );

export const fetchSoilRecommendations = (fieldId: string) =>
  tryReal(
    () => soilApi.get(`/soil/${fieldId}/recommendations`).then(r => r.data),
    () => ({ recommendations:['✅ التربة في حالة جيدة — استمر بنفس الإدارة'], priority:'روتيني' })
  );

export const postSoilReading = (data: { field_id:string; ph?:number; moisture_pct?:number; nitrogen_mg_kg?:number }) =>
  tryReal(
    () => soilApi.post('/soil/reading', data).then(r => r.data),
    () => ({ status:'received', nats_published:false })
  );
