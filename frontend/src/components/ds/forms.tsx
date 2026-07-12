// ═══════════════════════════════════════════════════════════════
// SAHOOL — Field-App Design System · عناصر النموذج (Form Controls)
// ───────────────────────────────────────────────────────────────
// عناصر إدخال واعية RTL، مكتوبة الأنواع، مُتحكَّم بها (controlled). الألوان
// والتباعد من tokens.ts (لا قيَم سحريّة). كلّ عنصر وصوليّ a11y: يربط label
// عبر htmlFor/id، ويُعلِن الخطأ عبر aria-invalid + aria-describedby. الخطأ
// يُعرَض نصّاً (لا اعتماد على اللون فقط). يُبنى ويُفحَص بـtsc.
// ═══════════════════════════════════════════════════════════════
import { useId } from 'react';
import type { CSSProperties, ReactNode, ChangeEvent } from 'react';
import { T, RADIUS, SPACE } from './tokens';

// نمط الحقل المشترك (حدّ + استدارة + خطّ تركيز ذهبيّ) — يُورَّث للـInput/Textarea/Select.
function fieldStyle(invalid: boolean, extra?: CSSProperties): CSSProperties {
  return {
    width: '100%',
    padding: '10px 12px',
    fontSize: 14,
    color: T.ink,
    background: T.card,
    border: `1px solid ${invalid ? T.danger : T.line}`,
    borderRadius: RADIUS.sm,
    outline: 'none',
    fontFamily: 'inherit',
    ...extra,
  };
}

// ── FormField ── غلاف موحّد: تسمية ⟵ محتوى ⟵ (تلميح | خطأ) ───────
// يمرّر id/aria للطفل عبر render-prop كي يربط label/error بصريّاً ووصوليّاً.
export function FormField({
  label,
  error,
  hint,
  required,
  children,
  style,
}: {
  label?: ReactNode;
  error?: string;
  hint?: string;
  required?: boolean;
  // الطفل يستقبل المعرّفات الوصوليّة ليربطها بعنصر الإدخال.
  children: (ids: { id: string; describedBy?: string; invalid: boolean }) => ReactNode;
  style?: CSSProperties;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errId = `${id}-err`;
  const invalid = Boolean(error);
  // aria-describedby يشير إلى الخطأ (إن وُجد) وإلّا التلميح.
  const describedBy = error ? errId : hint ? hintId : undefined;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: SPACE.xs, ...style }}>
      {label != null && (
        <label htmlFor={id} style={{ fontSize: 13, fontWeight: 700, color: T.brownSoft }}>
          {label}
          {required && <span style={{ color: T.danger, marginInlineStart: 4 }}>*</span>}
        </label>
      )}
      {children({ id, describedBy, invalid })}
      {error ? (
        <span id={errId} role="alert" style={{ fontSize: 11, color: T.danger, fontWeight: 600 }}>
          {error}
        </span>
      ) : hint ? (
        <span id={hintId} style={{ fontSize: 11, color: T.faint }}>
          {hint}
        </span>
      ) : null}
    </div>
  );
}

// ── Input ──────────────────────────────────────────────────────
export function Input({
  value,
  onChange,
  label,
  error,
  hint,
  required,
  type = 'text',
  placeholder,
  disabled,
  name,
  inputMode,
  list,
  style,
}: {
  value: string;
  onChange: (value: string) => void;
  label?: ReactNode;
  error?: string;
  hint?: string;
  required?: boolean;
  type?: 'text' | 'number' | 'email' | 'tel' | 'password' | 'search' | 'date';
  placeholder?: string;
  disabled?: boolean;
  name?: string;
  inputMode?: 'text' | 'numeric' | 'decimal' | 'tel' | 'email' | 'search';
  /** معرّف <datalist> لاقتراحات لا تُقيّد الإدخال. */
  list?: string;
  style?: CSSProperties;
}) {
  return (
    <FormField label={label} error={error} hint={hint} required={required} style={style}>
      {({ id, describedBy, invalid }) => (
        <input
          id={id}
          name={name}
          type={type}
          value={value}
          placeholder={placeholder}
          disabled={disabled}
          required={required}
          inputMode={inputMode}
          list={list}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
          style={fieldStyle(invalid, disabled ? { background: T.card2, cursor: 'not-allowed' } : undefined)}
        />
      )}
    </FormField>
  );
}

// ── Textarea ───────────────────────────────────────────────────
export function Textarea({
  value,
  onChange,
  label,
  error,
  hint,
  required,
  placeholder,
  disabled,
  name,
  rows = 4,
  style,
}: {
  value: string;
  onChange: (value: string) => void;
  label?: ReactNode;
  error?: string;
  hint?: string;
  required?: boolean;
  placeholder?: string;
  disabled?: boolean;
  name?: string;
  rows?: number;
  style?: CSSProperties;
}) {
  return (
    <FormField label={label} error={error} hint={hint} required={required} style={style}>
      {({ id, describedBy, invalid }) => (
        <textarea
          id={id}
          name={name}
          rows={rows}
          value={value}
          placeholder={placeholder}
          disabled={disabled}
          required={required}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) => onChange(e.target.value)}
          style={fieldStyle(invalid, {
            resize: 'vertical',
            minHeight: 80,
            ...(disabled ? { background: T.card2, cursor: 'not-allowed' } : {}),
          })}
        />
      )}
    </FormField>
  );
}

// ── Select ─────────────────────────────────────────────────────
export function Select<TValue extends string = string>({
  value,
  onChange,
  options,
  label,
  error,
  hint,
  required,
  disabled,
  name,
  placeholder,
  style,
}: {
  value: TValue | '';
  onChange: (value: TValue) => void;
  options: { value: TValue; label: ReactNode; disabled?: boolean }[];
  label?: ReactNode;
  error?: string;
  hint?: string;
  required?: boolean;
  disabled?: boolean;
  name?: string;
  placeholder?: string;
  style?: CSSProperties;
}) {
  return (
    <FormField label={label} error={error} hint={hint} required={required} style={style}>
      {({ id, describedBy, invalid }) => (
        <select
          id={id}
          name={name}
          value={value}
          disabled={disabled}
          required={required}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          onChange={(e: ChangeEvent<HTMLSelectElement>) => onChange(e.target.value as TValue)}
          style={fieldStyle(invalid, {
            cursor: disabled ? 'not-allowed' : 'pointer',
            ...(disabled ? { background: T.card2 } : {}),
          })}
        >
          {placeholder != null && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((o) => (
            <option key={o.value} value={o.value} disabled={o.disabled}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </FormField>
  );
}

// ── Checkbox ───────────────────────────────────────────────────
// تخطيط RTL: مربّع الاختيار يلي التسمية بترتيب طبيعيّ (flex-row). نضبط accentColor
// ذهبيّاً ليتطابق مع نغمة الإجراء.
export function Checkbox({
  checked,
  onChange,
  label,
  disabled,
  name,
  style,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  disabled?: boolean;
  name?: string;
  style?: CSSProperties;
}) {
  const id = useId();
  return (
    <label
      htmlFor={id}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: SPACE.sm,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.6 : 1,
        ...style,
      }}
    >
      <input
        id={id}
        name={name}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.checked)}
        style={{ width: 18, height: 18, accentColor: T.gold, flexShrink: 0, cursor: 'inherit' }}
      />
      <span style={{ fontSize: 13, color: T.ink }}>{label}</span>
    </label>
  );
}

// ── Radio (مجموعة خيارات أحاديّة) ───────────────────────────────
export function Radio<TValue extends string = string>({
  value,
  onChange,
  options,
  name,
  label,
  error,
  hint,
  disabled,
  style,
}: {
  value: TValue | '';
  onChange: (value: TValue) => void;
  options: { value: TValue; label: ReactNode; disabled?: boolean }[];
  name: string; // مطلوب: يربط أزرار المجموعة منطقيّاً
  label?: ReactNode;
  error?: string;
  hint?: string;
  disabled?: boolean;
  style?: CSSProperties;
}) {
  const groupId = useId();
  const invalid = Boolean(error);
  const hintId = `${groupId}-hint`;
  const errId = `${groupId}-err`;
  return (
    <div
      role="radiogroup"
      aria-labelledby={label != null ? `${groupId}-lbl` : undefined}
      aria-describedby={error ? errId : hint ? hintId : undefined}
      aria-invalid={invalid || undefined}
      style={{ display: 'flex', flexDirection: 'column', gap: SPACE.xs, ...style }}
    >
      {label != null && (
        <span id={`${groupId}-lbl`} style={{ fontSize: 13, fontWeight: 700, color: T.brownSoft }}>
          {label}
        </span>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: SPACE.sm }}>
        {options.map((o) => {
          const optId = `${groupId}-${o.value}`;
          const optDisabled = disabled || o.disabled;
          return (
            <label
              key={o.value}
              htmlFor={optId}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: SPACE.sm,
                cursor: optDisabled ? 'not-allowed' : 'pointer',
                opacity: optDisabled ? 0.6 : 1,
              }}
            >
              <input
                id={optId}
                type="radio"
                name={name}
                value={o.value}
                checked={value === o.value}
                disabled={optDisabled}
                onChange={() => onChange(o.value)}
                style={{ width: 18, height: 18, accentColor: T.gold, flexShrink: 0, cursor: 'inherit' }}
              />
              <span style={{ fontSize: 13, color: T.ink }}>{o.label}</span>
            </label>
          );
        })}
      </div>
      {error ? (
        <span id={errId} role="alert" style={{ fontSize: 11, color: T.danger, fontWeight: 600 }}>
          {error}
        </span>
      ) : hint ? (
        <span id={hintId} style={{ fontSize: 11, color: T.faint }}>
          {hint}
        </span>
      ) : null}
    </div>
  );
}
