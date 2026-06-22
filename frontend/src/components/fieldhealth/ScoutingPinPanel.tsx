// ═══════════════════════════════════════════════════════════════
// SAHOOL — صحّة الحقل · لوحة دبابيس الاستطلاع (Scouting Pins Panel)
// ───────────────────────────────────────────────────────────────
// لوحة جانبيّة لإدارة دبابيس المشاهدات المحلّيّة للجلسة: اختيار فئة الدبّوس
// التالي، وقائمة الدبابيس المُسقَطة (حذف فرديّ). صدق: شارة صريحة تُعلِم
// المستخدم أنّ الدبابيس محلّيّة للجلسة (لا حفظ خادم — لا GET للقراءة).
// ═══════════════════════════════════════════════════════════════
import { MapPin, Trash2, Info } from 'lucide-react';
import { Card, SectionLabel, Badge, Pill, T } from '../ds';
import { PIN_CATEGORY_AR, pinColor, type PinCategory, type ScoutPin } from './ScoutingMap';

const CATEGORIES: PinCategory[] = ['disease', 'pest', 'weed', 'nutrient', 'water_stress', 'abiotic', 'other'];

export interface ScoutingPinPanelProps {
  pins: ScoutPin[];
  activeCategory: PinCategory;
  onCategoryChange: (c: PinCategory) => void;
  onRemove: (id: string) => void;
  onClear: () => void;
}

export default function ScoutingPinPanel({
  pins,
  activeCategory,
  onCategoryChange,
  onRemove,
  onClear,
}: ScoutingPinPanelProps) {
  return (
    <Card pad={14}>
      <SectionLabel
        action={<Badge tone={pins.length ? 'warn' : 'neutral'}>{pins.length} دبّوس</Badge>}
      >
        دبابيس الاستطلاع
      </SectionLabel>

      {/* شارة الصدق: محلّيّ للجلسة (لا GET للقراءة في الخادم) */}
      <div
        className="flex items-start gap-2"
        style={{
          background: '#3a2e14', border: '1px solid #7a5a1a', color: '#f0d68a',
          borderRadius: 10, padding: '8px 10px', margin: '8px 0', fontSize: 11, lineHeight: 1.6,
        }}
      >
        <Info style={{ width: 13, height: 13, flexShrink: 0, marginTop: 2 }} />
        <span>
          الدبابيس محلّيّة للجلسة فقط — الخادم لا يوفّر قراءة (GET) لمشاهدات مُخزَّنة
          (pins/timeline في الخادم POST فقط). تختفي بإعادة التحميل. <code>TODO</code>:
          تُربَط عند توفّر <code>GET /scouting/pins</code>.
        </span>
      </div>

      {/* اختيار فئة الدبّوس التالي */}
      <div style={{ fontSize: 11, color: T.muted, marginBottom: 6 }}>فئة الدبّوس التالي</div>
      <div className="flex" style={{ flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
        {CATEGORIES.map((c) => {
          const on = activeCategory === c;
          const col = pinColor(c);
          return (
            <button
              key={c}
              type="button"
              onClick={() => onCategoryChange(c)}
              style={{
                fontSize: 11, fontWeight: on ? 700 : 500, cursor: 'pointer',
                padding: '5px 10px', borderRadius: 999,
                background: on ? `${col}22` : 'transparent',
                color: on ? col : T.muted,
                border: `1px solid ${on ? col : T.line}`,
              }}
            >
              {PIN_CATEGORY_AR[c]}
            </button>
          );
        })}
      </div>

      {/* قائمة الدبابيس المُسقَطة */}
      {pins.length === 0 ? (
        <div className="flex flex-col items-center" style={{ color: T.muted, fontSize: 12, padding: '12px 0', gap: 6 }}>
          <MapPin style={{ width: 22, height: 22, color: T.faint }} />
          انقر الخريطة لإسقاط أوّل دبّوس مشاهدة.
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
                  style={{ width: 10, height: 10, borderRadius: '50%', background: pinColor(p.category), flexShrink: 0 }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: T.ink }}>
                    {PIN_CATEGORY_AR[p.category]}
                  </div>
                  <div style={{ fontSize: 10, color: T.faint }}>
                    {p.lat.toFixed(4)}، {p.lon.toFixed(4)}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onRemove(p.id)}
                  aria-label="حذف الدبّوس"
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
            مسح كلّ الدبابيس
          </button>
          <Pill tone="neutral" icon={<Info style={{ width: 11, height: 11 }} />}>
            <span style={{ fontSize: 10 }}>{pins.length} مشاهدة محلّيّة هذه الجلسة</span>
          </Pill>
        </>
      )}
    </Card>
  );
}
