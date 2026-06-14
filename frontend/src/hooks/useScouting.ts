// useScouting — ربط حيّ بتصنيف المشاهدات الميدانيّة (Scouting Taxonomy).
//
// المصدر الوحيد القابل للوصول (GET) في الخادم هو
//   GET /api/v1/scouting/taxonomy        → التصنيف الكامل + دليل نقص العناصر
//   GET /api/v1/scouting/taxonomy?crop=X → مشاكل محصول واحد فقط
// (api/scouting_pins.py عبر main.py). نقطتا pins/timeline في الخادم POST فقط
// (إنشاء/تجميع من حمولة الطلب) ولا تُرجِعان قائمة مُخزَّنة تُقرأ بـGET، فلا
// تُلَفّان هنا — صدق: لا نخترع endpoint للقراءة غير موجود.
//
// ملفّ مكتفٍ ذاتيّاً: يستورد kongApi مباشرةً ولا يلمس useApi.ts/api.ts.
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';

// ── أشكال الاستجابة المُتحقَّق منها (main.py:7121-7133, scouting_pins.py) ──

// مشكلة ميدانيّة واحدة في التصنيف (taxonomy entry).
export interface ScoutingIssue {
  code: string;      // مثل wheat.rust
  category: string;  // disease | pest | weed | nutrient | water_stress | abiotic | other
  name_ar: string;   // الاسم العربيّ للعرض
}

// دليل نقص عنصر غذائي (علامة بصريّة rule-based).
export interface NutrientDeficiency {
  code: string;     // n | p | fe | zn …
  name_ar: string;  // مثل «نقص حديد»
  sign_ar: string;  // العلامة البصريّة
}

// استجابة التصنيف الكامل (بلا crop).
export interface ScoutingTaxonomy {
  crops: string[];
  all_issues: Record<string, ScoutingIssue[]>;
  nutrient_guide: NutrientDeficiency[];
}

// استجابة تصنيف محصول واحد (مع crop).
export interface CropScoutingTaxonomy {
  crop: string;
  issues: ScoutingIssue[];
}

// ── الاستعلامات ──

// التصنيف الكامل: كلّ المحاصيل + مشاكلها + دليل العناصر. ربط حيّ بلا fallback.
export function useScoutingTaxonomy(): UseQueryResult<ScoutingTaxonomy, Error> {
  return useQuery<ScoutingTaxonomy, Error>({
    queryKey: ['scouting', 'taxonomy', 'all'],
    queryFn: () =>
      kongApi.get<ScoutingTaxonomy>('/api/v1/scouting/taxonomy').then((r) => r.data),
    staleTime: 30 * 60_000, // تصنيف ثابت — يُذكَّر طويلاً
    retry: false,
  });
}

// مشاكل محصول واحد. مُفعَّل فقط عند وجود crop (enabled على المحصول).
export function useCropScoutingIssues(
  crop?: string,
): UseQueryResult<CropScoutingTaxonomy, Error> {
  return useQuery<CropScoutingTaxonomy, Error>({
    queryKey: ['scouting', 'taxonomy', 'crop', crop ?? 'none'],
    queryFn: () =>
      kongApi
        .get<CropScoutingTaxonomy>('/api/v1/scouting/taxonomy', { params: { crop } })
        .then((r) => r.data),
    staleTime: 30 * 60_000,
    retry: false,
    enabled: !!crop,
  });
}
