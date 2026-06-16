// ═══════════════════════════════════════════════════════════════
// SAHOOL — useFieldContext.ts («الحقل النشط» المشترك عبر الشاشات)
// ═══════════════════════════════════════════════════════════════
// المشكلة: كلّ شاشة كانت تختار حقلاً محليّاً ([fieldId,setFieldId]=useState(''))،
// فيضيع الاختيار عند التنقّل (يختار المزارع «حقل الشمال» في الأقمار ثمّ ينتقل
// للريّ فيعيد الاختيار من الصفر). الحلّ: متجر zustand صغير يحمل الاختيار، يتبع
// المستخدم عبر كلّ الشاشات (خريطة→صحة→ري→تقرير) — نمط «الحقل النشط» العالميّ.
//
// يطابق بنية useAuth: persist على sessionStorage (عمر الاختيار = عمر الجلسة/
// التبويب، يتلاشى مع الخروج)، partialize للحالة دون الأفعال.
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

interface FieldContextState {
  selectedFieldId: string | null;
  // Actions
  setSelectedField: (id: string | null) => void;
}

export const useFieldContextStore = create<FieldContextState>()(
  persist(
    (set) => ({
      selectedFieldId: null,
      setSelectedField: (id: string | null) => set({ selectedFieldId: id }),
    }),
    {
      name: 'sahool-field-context',
      // sessionStorage (لا local) — مطابقةً لـuseAuth: السياق محصور بالجلسة/التبويب
      // ولا يتسرّب بين الجلسات أو يثبت اختياراً قديماً عند فتح تبويب جديد.
      storage: createJSONStorage(() => sessionStorage),
      partialize: (s) => ({ selectedFieldId: s.selectedFieldId }),
    },
  ),
);
