// ═══════════════════════════════════════════════════════════════
// SAHOOL — Field-App Design System · القائمة المنسدلة الباحثة (Combobox)
// ───────────────────────────────────────────────────────────────
// اختيار أحاديّ قابل للبحث (مثل مُنتقي الحقل). تنقّل بالكيبورد (أسهم/Enter/Esc)،
// واعٍ RTL. a11y: نمط ARIA combobox (role=combobox/listbox/option + aria-activedescendant).
// مُتحكَّم به (controlled). الألوان من tokens.ts. لا بيانات وهميّة: يعرض الخيارات
// المُمرَّرة فقط.
// ═══════════════════════════════════════════════════════════════
import { useId, useMemo, useRef, useState } from 'react';
import type { CSSProperties, KeyboardEvent } from 'react';
import { ChevronDown, Search, Check } from 'lucide-react';
import { T, RADIUS } from './tokens';

export interface ComboOption<TValue extends string = string> {
  value: TValue;
  label: string;
}

export function Combobox<TValue extends string = string>({
  value,
  onChange,
  options,
  placeholder = 'اختر…',
  searchPlaceholder = 'بحث…',
  emptyText = 'لا نتائج',
  disabled,
  style,
}: {
  value: TValue | '';
  onChange: (value: TValue) => void;
  options: ComboOption<TValue>[];
  placeholder?: string;
  searchPlaceholder?: string;
  emptyText?: string;
  disabled?: boolean;
  style?: CSSProperties;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0); // فهرس الخيار النشط (تنقّل الكيبورد)
  const id = useId();
  const listId = `${id}-list`;
  const rootRef = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => o.value === value);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) => o.label.toLowerCase().includes(q));
  }, [options, query]);

  function close() {
    setOpen(false);
    setQuery('');
    setActive(0);
  }

  function choose(opt: ComboOption<TValue>) {
    onChange(opt.value);
    close();
  }

  function onKeyDown(e: KeyboardEvent) {
    if (disabled) return;
    if (!open && (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      setOpen(true);
      return;
    }
    if (!open) return;
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setActive((a) => Math.min(a + 1, filtered.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setActive((a) => Math.max(a - 1, 0));
        break;
      case 'Enter': {
        e.preventDefault();
        const opt = filtered[active];
        if (opt) choose(opt);
        break;
      }
      case 'Escape':
        e.preventDefault();
        close();
        break;
      default:
        break;
    }
  }

  // إغلاق عند فقدان التركيز خارج الجذر (relatedTarget).
  function onBlur(e: React.FocusEvent<HTMLDivElement>) {
    if (!rootRef.current?.contains(e.relatedTarget as Node)) close();
  }

  return (
    <div
      ref={rootRef}
      onBlur={onBlur}
      style={{ position: 'relative', opacity: disabled ? 0.6 : 1, ...style }}
    >
      <button
        type="button"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-haspopup="listbox"
        disabled={disabled}
        onClick={() => !disabled && setOpen((o) => !o)}
        onKeyDown={onKeyDown}
        className="flex items-center justify-between"
        style={{
          width: '100%',
          padding: '10px 12px',
          fontSize: 14,
          color: selected ? T.ink : T.faint,
          background: T.card,
          border: `1px solid ${open ? T.gold : T.line}`,
          borderRadius: RADIUS.sm,
          cursor: disabled ? 'not-allowed' : 'pointer',
          gap: 8,
        }}
      >
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {selected ? selected.label : placeholder}
        </span>
        <ChevronDown style={{ width: 16, height: 16, color: T.muted, flexShrink: 0 }} aria-hidden="true" />
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            zIndex: 50,
            insetInlineStart: 0,
            insetInlineEnd: 0,
            top: 'calc(100% + 4px)',
            background: T.card,
            border: `1px solid ${T.line}`,
            borderRadius: RADIUS.sm,
            boxShadow: '0 8px 24px rgba(44,26,14,.18)',
            overflow: 'hidden',
          }}
        >
          <div className="flex items-center gap-2" style={{ padding: 8, borderBottom: `1px solid ${T.line}` }}>
            <Search style={{ width: 14, height: 14, color: T.muted, flexShrink: 0 }} aria-hidden="true" />
            {/* autoFocus مقصود: القائمة تُفتَح بفعل المستخدم، والتركيز على حقل
                البحث هو السلوك المتوقَّع لصندوق مركّب. (لا توجيه eslint هنا:
                jsx-a11y غير مثبَّت، وتوجيهٌ لقاعدة غير موجودة خطأ بذاته.) */}
            <input
              autoFocus
              type="search"
              value={query}
              placeholder={searchPlaceholder}
              aria-label={searchPlaceholder}
              onChange={(e) => {
                setQuery(e.target.value);
                setActive(0);
              }}
              onKeyDown={onKeyDown}
              style={{
                flex: 1,
                border: 'none',
                outline: 'none',
                fontSize: 13,
                color: T.ink,
                background: 'transparent',
                fontFamily: 'inherit',
              }}
            />
          </div>
          <ul
            id={listId}
            role="listbox"
            aria-activedescendant={filtered[active] ? `${id}-opt-${filtered[active].value}` : undefined}
            style={{ listStyle: 'none', margin: 0, padding: 4, maxHeight: 240, overflowY: 'auto' }}
          >
            {filtered.length === 0 ? (
              <li style={{ padding: '10px 8px', fontSize: 13, color: T.faint, textAlign: 'center' }}>{emptyText}</li>
            ) : (
              filtered.map((opt, i) => {
                const isActive = i === active;
                const isSelected = opt.value === value;
                return (
                  <li
                    key={opt.value}
                    id={`${id}-opt-${opt.value}`}
                    role="option"
                    aria-selected={isSelected}
                    onMouseEnter={() => setActive(i)}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => choose(opt)}
                    className="flex items-center justify-between"
                    style={{
                      padding: '8px 10px',
                      fontSize: 13,
                      borderRadius: RADIUS.sm,
                      cursor: 'pointer',
                      color: T.ink,
                      background: isActive ? T.card2 : 'transparent',
                      gap: 8,
                    }}
                  >
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {opt.label}
                    </span>
                    {isSelected && (
                      <Check style={{ width: 14, height: 14, color: T.green, flexShrink: 0 }} aria-hidden="true" />
                    )}
                  </li>
                );
              })
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
