// SAHOOL v9.0 — src/hooks/useSoilApi.ts — هوكات التربة (مقتطعة من useApi.ts)
import { useQuery } from '@tanstack/react-query';
import { soilApi } from '../services/api';
import { QK } from './useApiKeys';

// ── Soil ──────────────────────────────────────────────────────
// صدق: خدمة soil-service غير منشورة (مُعلّقة في docker-compose؛ nginx يردّ 503 على
// /api/soil/)، والمنصّة لا تكشف نقطة مكافئة لتركيب التربة (pH/EC/OM/NPK) ولا توصية
// نيتروجين بنمط GET. لذا لا نُطلق طلباً محكوماً بالفشل: الهوكات معطّلة افتراضيّاً
// (FEATURE_FLAGS.soil مُطفأ — VITE_ENABLE_SOIL!=='true')، فلا استدعاء ميّت. عند رفع
// soil-service بتنفيذ حقيقيّ وفتح العلم، يُعاد تفعيلها كما هي (مسارات /api/soil عبر
// البوّابة). المكوّن المستهلِك (FarmAdvisoryReport) يعرض حالة «بيانات التربة غير
// متاحة» الصادقة حين تكون معطّلة (لا استدعاء صامت يفشل).
// نقرأ العلم محليّاً (لا استيراد App.tsx ⇒ تفادي اعتماد دائريّ): نفس منطق
// FEATURE_FLAGS.soil في App.tsx.
export const SOIL_ENABLED = import.meta.env.VITE_ENABLE_SOIL === 'true';

export function useSoilParams(fieldId: string) {
  return useQuery({
    queryKey: QK.soilParams(fieldId),
    queryFn:  () => soilApi.get(`/soil/wofost_params/${fieldId}`).then(r => r.data),
    staleTime:60 * 60_000,
    enabled:  SOIL_ENABLED && !!fieldId,
    retry:    false,
  });
}

export function useSoilNRecommendation(fieldId: string, targetYield = 3.5) {
  return useQuery({
    queryKey: QK.soilNRec(fieldId),
    queryFn:  () => soilApi.get('/soil/nitrogen/recommendation', {
      params: { field_id: fieldId, target_yield_t_ha: targetYield }
    }).then(r => r.data),
    staleTime:30 * 60_000,
    enabled:  SOIL_ENABLED && !!fieldId,
    retry:    false,
  });
}
