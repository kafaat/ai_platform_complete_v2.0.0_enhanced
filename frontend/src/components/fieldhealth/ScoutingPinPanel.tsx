// ═══════════════════════════════════════════════════════════════
// SAHOOL — صحّة الحقل · لوحة دبابيس الاستطلاع (Scouting Pins Panel)
// ───────────────────────────────────────────────────────────────
// لوحة جانبيّة لإدارة دبابيس المشاهدات الدائمة (FieldView): إعداد الدبّوس التالي
// (فئة · دوام موسميّ/دائم · شدّة · مشكلة من الـtaxonomy · ملاحظة) ثمّ قائمة الدبابيس
// المُخزَّنة. الدبابيس تُحفَظ على الخادم (POST) وتُجلَب (GET /scouting/pins) فتبقى عبر
// الجلسات (v94). صدق: القاعدة غير مفعّلة ⇒ حالة فارغة صريحة (لا اختراع مشاهدات).
// ═══════════════════════════════════════════════════════════════
import { MapPin, Trash2, Info, Loader2, AlertTriangle } from 'lucide-react';
import { Card, SectionLabel, Badge, T } from '../ds';
import {
  PIN_CATEGORY_AR,
  PIN_PERSISTENCE_AR,
  PIN_SEVERITY_AR,
  pinColor,
  type PinCategory,
  type PinPersistence,
  type PinSeverity,
  type ScoutPin,
} from './ScoutingMap';

const CATEGORIES: PinCategory[] = ['disease', 'pest', 'weed', 'nutrient', 'water_stress', 'abiotic', 'other'];
const PERSISTENCES: PinPersistence[] = ['seasonal', 'permanent'];
const SEVERITIES: PinSeverity[] = ['low', 'medium', 'high'];

// مشكلة واحدة من تصنيف المحصول (taxonomy) — للقائمة المنسدلة الاختياريّة.
export interface IssueOption {
  code: string;
  name_ar: string;
}

export interface ScoutingPinPanelProps {
  pins: ScoutPin[];
  // إعداد الدبّوس التالي
  activeCategory: PinCategory;
  onCategoryChange: (c: PinCategory) => void;
  persistence: PinPersistence;
  onPersistenceChange: (p: PinPersistence) => void;
  severity: PinSeverity;
  onSeverityChange: (s: PinSeverity) => void;
  note: string;
  onNoteChange: (n: string) => void;
  // مشكلة الـtaxonomy (اختياريّة — تظهر فقط عند توفّر خيارات لمحصول الحقل)
  issueOptions?: IssueOption[];
  issueCode?: string;
  onIssueChange?: (code: string) => void;
  // إجراءات القائمة
  onRemove: (id: string) => void;
  onClear: () => void;
  // حالات صادقة
  isLoading?: boolean;
  isError?: boolean;
  dbDisabledNote?: string | null; // القاعدة غير مفعّلة — لا مشاهدات مُخزَّنة
}

// زرّ شريحة قابل لإعادة الاستخدام (فئة/دوام/شدّة).
function Chip({ label, on, color, onClick }: { label: string; on: boolean; color: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        fontSize: 11, fontWeight: on ? 700 : 500, cursor: 'pointer',
        padding: '5px 10px', borderRadius: 999,
        background: on ? `${color}22` : 'transparent',
        color: on ? color : T.muted,
        border: `1px solid ${on ? color : T.line}`,
      }}
    >
      {label}
    </button>
  );
}

export default function ScoutingPinPanel({
  pins,
  activeCategory,
  onCategoryChange,
  persistence,
  onPersistenceChange,
  severity,
  onSeverityChange,
  note,
  onNoteChange,
  issueOptions,
  issueCode,
  onIssueChange,
  onRemove,
  onClear,
  isLoading = false,
  isError = false,
  dbDisabledNote = null,
}: ScoutingPinPanelProps) {
  const accent = pinColor(activeCategory);
  return (
    <Card pad={14}>
      <SectionLabel
        action={<Badge tone={pins.length ? 'ok' : 'neutral'}>{pins.length} دبّوس</Badge>}
      >
        دبابيس الاستطلاع
      </SectionLabel>

      {/* فئة الدبّوس التالي (تُحدّد اللون) */}
      <div style={{ fontSize: 11, color: T.muted, marginBottom: 6 }}>فئة الدبّوس التالي</div>
      <div className="flex" style={{ flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
        {CATEGORIES.map((c) => (
          <Chip key={c} label={PIN_CATEGORY_AR[c]} on={activeCategory === c} color={pinColor(c)} onClick={() => onCategoryChange(c)} />
        ))}
      </div>

      {/* الدوام: موسميّ vs دائم (نمط FieldView — مشكلة بنيويّة تبقى عبر المواسم) */}
      <div style={{ fontSize: 11, color: T.muted, marginBottom: 6 }}>الدوام</div>
      <div className="flex" style={{ gap: 6, marginBottom: 10 }}>
        {PERSISTENCES.map((p) => (
          <Chip key={p} label={PIN_PERSISTENCE_AR[p]} on={persistence === p} color={accent} onClick={() => onPersistenceChange(p)} />
        ))}
      </div>

      {/* الشدّة */}
      <div style={{ fontSize: 11, color: T.muted, marginBottom: 6 }}>الشدّة</div>
      <div className="flex" style={{ gap: 6, marginBottom: 10 }}>
        {SEVERITIES.map((s) => (
          <Chip key={s} label={PIN_SEVERITY_AR[s]} on={severity === s} color={accent} onClick={() => onSeverityChange(s)} />
        ))}
      </div>

      {/* المشكلة من تصنيف المحصول (اختياريّة) */}
      {issueOptions && issueOptions.length > 0 && onIssueChange && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 11, color: T.muted, marginBottom: 6 }}>المشكلة (من تصنيف المحصول)</div>
          <select
            value={issueCode ?? ''}
            onChange={(e) => onIssueChange(e.target.value)}
            dir="rtl"
            style={{
              width: '100%', fontSize: 12, padding: '6px 8px', borderRadius: 8,
              background: T.card2, color: T.ink, border: `1px solid ${T.line}`,
            }}
          >
            <option value="">— بلا تحديد —</option>
            {issueOptions.map((o) => (
              <option key={o.code} value={o.code}>{o.name_ar}</option>
            ))}
          </select>
        </div>
      )}

      {/* ملاحظة الدبّوس التالي */}
      <div style={{ fontSize: 11, color: T.muted, marginBottom: 6 }}>ملاحظة (تُرفَق بالدبّوس التالي)</div>
      <textarea
        value={note}
        onChange={(e) => onNoteChange(e.target.value)}
        dir="rtl"
        rows={2}
        placeholder="مثال: بؤرة إصابة في الزاوية الشماليّة…"
        style={{
          width: '100%', fontSize: 12, padding: '6px 8px', borderRadius: 8, resize: 'vertical',
          background: T.card2, color: T.ink, border: `1px solid ${T.line}`, marginBottom: 10,
        }}
      />

      {/* قائمة الدبابيس المُخزَّنة — حالات صادقة */}
      {isLoading ? (
        <div className="flex items-center justify-center" style={{ color: T.muted, fontSize: 12, padding: '12px 0', gap: 6 }}>
          <Loader2 className="animate-spin" style={{ width: 16, height: 16 }} />
          جارٍ جلب الدبابيس المُخزَّنة…
        </div>
      ) : isError ? (
        <div className="flex items-start gap-2" style={{ color: T.danger, fontSize: 11, padding: '10px 0' }}>
          <AlertTriangle style={{ width: 14, height: 14, flexShrink: 0, marginTop: 1 }} />
          تعذّر جلب الدبابيس المُخزَّنة (القاعدة غير متاحة). حاول لاحقاً.
        </div>
      ) : dbDisabledNote ? (
        <div className="flex items-start gap-2" style={{ color: T.muted, fontSize: 11, padding: '10px 0' }}>
          <Info style={{ width: 14, height: 14, flexShrink: 0, marginTop: 1 }} />
          {dbDisabledNote}
        </div>
      ) : pins.length === 0 ? (
        <div className="flex flex-col items-center" style={{ color: T.muted, fontSize: 12, padding: '12px 0', gap: 6 }}>
          <MapPin style={{ width: 22, height: 22, color: T.faint }} />
          لا دبابيس مُخزَّنة لهذا الحقل بعد — انقر الخريطة لإسقاط أوّل مشاهدة.
        </div>
      ) : (
        <>
          <div style={{ borderTop: `1px solid ${T.line}`, paddingTop: 8 }}>
            {pins.map((p) => (
              <div
                key={p.id}
                className="flex items-center gap-2"
                style={{ padding: '6px 0', borderBottom: `1px solid ${T.line}` }}
              >
                <span
                  style={{
                    width: 10, height: 10, flexShrink: 0,
                    borderRadius: '50%',
                    background: p.persistence === 'permanent' ? 'transparent' : pinColor(p.category),
                    border: `2px solid ${pinColor(p.category)}`,
                  }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: T.ink }}>
                    {PIN_CATEGORY_AR[p.category]}
                    <span style={{ fontSize: 10, fontWeight: 400, color: T.faint }}>
                      {' · '}{PIN_PERSISTENCE_AR[p.persistence]}
                      {p.severity ? ` · ${PIN_SEVERITY_AR[p.severity]}` : ''}
                    </span>
                  </div>
                  <div style={{ fontSize: 10, color: T.faint }}>
                    {p.lat.toFixed(4)}، {p.lon.toFixed(4)}
                    {p.persisted === false ? ' · بانتظار الحفظ' : ''}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onRemove(p.id)}
                  aria-label="إخفاء الدبّوس من العرض"
                  style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: T.danger, padding: 4 }}
                >
                  <Trash2 style={{ width: 14, height: 14 }} />
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={onClear}
            style={{
              marginTop: 10, fontSize: 11, color: T.danger, background: 'transparent',
              border: `1px solid ${T.danger}55`, borderRadius: 8, padding: '5px 12px', cursor: 'pointer',
            }}
          >
            إخفاء كلّ الدبابيس من العرض
          </button>
        </>
      )}
    </Card>
  );
}
