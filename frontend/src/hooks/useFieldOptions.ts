// useFieldOptions — قائمة الحقول المُطبَّعة (يلفّ useFields + toFieldOption).
// يزيل تكرار «map(raw → {id,name,…})» المنتشر في الشاشات؛ يُعيد نفس أعلام
// الاستعلام (isLoading/isError/refetch…) مع options مُطبَّعة ومُذكَّرة (مرجع
// مستقرّ ما لم تتغيّر البيانات).
import { useMemo } from 'react';
import { useFields } from './useApi';
import { toFieldOption, type FieldOption } from '../lib/fields';

export function useFieldOptions() {
  const query = useFields();
  const options = useMemo<FieldOption[]>(() => {
    const raw = Array.isArray(query.data?.fields) ? query.data.fields : [];
    return raw.map(toFieldOption);
  }, [query.data]);
  return { ...query, options };
}
