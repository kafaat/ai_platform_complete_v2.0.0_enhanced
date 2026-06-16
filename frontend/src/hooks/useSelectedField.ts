// useSelectedField — «الحقل النشط» المشترك: يلفّ useFieldOptions ويربط الاختيار
// بمتجر useFieldContext (zustand). بديل drop-in لنمط
//   const [fieldId, setFieldId] = useState('');
//   useEffect(() => { if (!fieldId && fields.length) setFieldId(fields[0].id); }, …);
// المكرّر في الشاشات — لكنّ الاختيار الآن مشترك فيتبع المستخدم عبر الشاشات بدل
// ضياعه عند التنقّل. يُعيد نفس أعلام الاستعلام (isLoading/isError/refetch/options)
// مضافاً إليها fieldId/field/setFieldId.
import { useEffect } from 'react';
import { useFieldOptions } from './useFieldOptions';
import { useFieldContextStore } from './useFieldContext';
import { resolveActiveFieldId } from '../lib/fields';

export function useSelectedField() {
  const query = useFieldOptions();
  const options = query.options;
  const selectedFieldId = useFieldContextStore((s) => s.selectedFieldId);
  const setSelectedField = useFieldContextStore((s) => s.setSelectedField);

  // الحقل النشط الفعليّ: المُختار إن بقي موجوداً، وإلّا أوّل حقل (منطق نقيّ مُختبَر).
  const fieldId = resolveActiveFieldId(options, selectedFieldId);

  // ثبّت المتجر على الحقل المحلول حين يختلف (أوّل تحميل، أو سقوط المُختار بحذف/
  // تغيّر مستأجِر). تأثير واحد، no-op بعد الاستقرار (fieldId === selectedFieldId).
  // لا نلمس المتجر حين لا حقول (نُبقي null لا '').
  useEffect(() => {
    if (options.length && fieldId !== selectedFieldId) setSelectedField(fieldId);
  }, [options.length, fieldId, selectedFieldId, setSelectedField]);

  const field = options.find((o) => o.id === fieldId);
  return { ...query, fieldId, field, setFieldId: setSelectedField };
}
