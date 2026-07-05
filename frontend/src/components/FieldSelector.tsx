import { useSelectedField } from '../hooks/useSelectedField';

export interface FieldSelectorProps {
  label?: string;
  className?: string;
  requireSelectionHint?: string;
}

export default function FieldSelector({
  label = 'الحقل',
  className = '',
  requireSelectionHint = 'اختر حقلاً لتفعيل بيانات هذه الشاشة.',
}: FieldSelectorProps) {
  const { options, fieldId, setFieldId, isLoading, isError } = useSelectedField();
  return (
    <div className={`rounded-xl border border-slate-800 bg-slate-950/70 p-3 ${className}`} dir="rtl">
      <label className="block text-xs text-slate-400 mb-1">{label}</label>
      <select
        value={fieldId ?? ''}
        disabled={isLoading || isError || options.length === 0}
        onChange={(e) => setFieldId(e.target.value || null, { source: 'user' })}
        className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 disabled:opacity-60"
      >
        <option value="">{isLoading ? 'جارٍ تحميل الحقول…' : 'اختر الحقل'}</option>
        {options.map((f) => <option key={f.id} value={f.id}>{f.name}{f.crop && f.crop !== '—' ? ` · ${f.crop}` : ''}</option>)}
      </select>
      {!fieldId && !isLoading ? <p className="mt-2 text-[11px] text-amber-300">{requireSelectionHint}</p> : null}
      {isError ? <p className="mt-2 text-[11px] text-red-300">تعذّر تحميل الحقول.</p> : null}
    </div>
  );
}
