// useScouting — ربط حيّ بتصنيف المشاهدات الميدانيّة + دبابيسها الدائمة.
//
// التصنيف (GET موجود سابقاً):
//   GET /api/v1/scouting/taxonomy        → التصنيف الكامل + دليل نقص العناصر
//   GET /api/v1/scouting/taxonomy?crop=X → مشاكل محصول واحد فقط
//
// الدبابيس الدائمة (v94 — صار للخادم نقطة قراءة فعليّة):
//   GET  /api/v1/scouting/pins?field_id=… → المشاهدات المُثبَّتة (RLS، معزولة بالمستأجِر)
//   POST /api/v1/fields/{field_id}/pins   → إنشاء + إدامة (idempotent عبر pin_id)
// كان الإنشاء سابقاً POST-فقط بلا قراءة (فبقيت الدبابيس محلّيّة للجلسة)؛ الآن تُجلَب
// وتُعرَض. صدق: القاعدة غير مفعّلة ⇒ pins:[] + note_ar (لا اختراع مشاهدات).
import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from '@tanstack/react-query';
import {
  kongApi,
  fetchScoutingPins,
  createScoutingPin,
  type ScoutingPinRecord,
  type ScoutingPinsResponse,
  type ScoutingPinCreateInput,
  type ScoutingPinCreated,
} from '../services/api';

export type {
  ScoutingPinRecord,
  ScoutingPinsResponse,
  ScoutingPinCreateInput,
  ScoutingPinCreated,
};

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

// ── دبابيس الاستطلاع الدائمة (v94) ──

const pinsQueryKey = (fieldId: string) => ['scouting', 'pins', fieldId] as const;

// دبابيس مشاهدة الحقل المُخزَّنة (GET /api/v1/scouting/pins?field_id=…). مُفعَّل فقط
// عند وجود fieldId. صدق: القاعدة غير مفعّلة ⇒ pins:[] + note_ar؛ 503 ⇒ خطأ يُكشَف.
export function useScoutingPins(
  fieldId?: string,
): UseQueryResult<ScoutingPinsResponse, Error> {
  return useQuery<ScoutingPinsResponse, Error>({
    queryKey: pinsQueryKey(fieldId ?? 'none'),
    queryFn: () => fetchScoutingPins(fieldId as string),
    staleTime: 60_000,
    retry: false,
    enabled: !!fieldId,
  });
}

// إنشاء دبّوس (POST) ثمّ إبطال مخبّأ دبابيس الحقل لإعادة الجلب (المصدر القانونيّ
// هو القاعدة بعد الإنشاء). التفاؤل يتولّاه المستهلِك بإضافة الدبّوس محلّيّاً ريثما
// تكتمل إعادة الجلب — وإن فشل الإنشاء يتراجع المستهلِك. يُرجِع الدبّوس + علم persisted.
export function useCreateScoutingPin(
  fieldId?: string,
): UseMutationResult<ScoutingPinCreated, Error, ScoutingPinCreateInput> {
  const qc = useQueryClient();
  return useMutation<ScoutingPinCreated, Error, ScoutingPinCreateInput>({
    mutationFn: (input) => createScoutingPin(input),
    onSuccess: () => {
      if (fieldId) qc.invalidateQueries({ queryKey: pinsQueryKey(fieldId) });
    },
  });
}
