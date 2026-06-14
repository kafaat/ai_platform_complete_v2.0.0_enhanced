// cabin.tsx — قشرة «الكابينة المحمولة» الموحّدة (DS).
// كانت الشاشات الثلاث (OperationCommand/FieldMapCenter/FieldTasksCabin) تكرّر
// نفس الغلاف حرفيّاً: خلفيّة كريميّة + بطاقة 420px + ترويسة بنّيّة + تعليق سفليّ.
// وُحِّد هنا. footer اختياريّ (مثلاً BottomTabBar) يحوّل الكابينة إلى عمود مرن
// بمحتوًى قابل للتمرير وشريط مثبّت أسفلها (نمط FieldTasksCabin).
import type { ReactNode } from 'react';
import { T } from './tokens';

export function FieldCabin({
  eyebrow, title, headerRight, subtitle, footer, note, children,
}: {
  eyebrow: ReactNode;       // وسم صغير ذهبيّ فوق العنوان (اسم الكابينة)
  title: ReactNode;         // العنوان الكبير
  headerRight?: ReactNode;  // عنصر يمين الترويسة (عادةً Pill)
  subtitle?: ReactNode;     // سطر وصفيّ تحت العنوان
  footer?: ReactNode;       // شريط سفليّ مثبّت (BottomTabBar) — يفعّل وضع العمود المرن
  note?: ReactNode;         // تعليق أسفل الكابينة (خارج البطاقة)
  children: ReactNode;      // جسم الكابينة (البطاقات)
}) {
  const hasFooter = footer != null;
  return (
    <div dir="rtl" style={{ background: T.cream, minHeight: '100%', padding: 16 }}>
      <div
        style={{
          maxWidth: 420, margin: '0 auto', background: T.cream,
          borderRadius: 22, border: `1px solid ${T.line}`, overflow: 'hidden',
          boxShadow: '0 12px 40px rgba(44,26,14,.10)',
          ...(hasFooter ? { display: 'flex', flexDirection: 'column', minHeight: 600 } : null),
        }}
      >
        {/* ── الترويسة ── */}
        <div style={{ background: T.brown, color: '#fff', padding: '18px 16px 22px', flexShrink: 0 }}>
          <div className="flex items-center justify-between">
            <div>
              <div style={{ fontSize: 12, color: T.goldSoft }}>{eyebrow}</div>
              <div style={{ fontSize: 18, fontWeight: 800 }}>{title}</div>
            </div>
            {headerRight}
          </div>
          {subtitle != null && (
            <div style={{ fontSize: 11, color: '#D8C7B3', marginTop: 6 }}>{subtitle}</div>
          )}
        </div>

        {/* ── الجسم (يتمدّد ويتمرّر حين يوجد footer) ── */}
        <div style={{ padding: 14, ...(hasFooter ? { flex: 1, overflowY: 'auto' } : null) }}>
          {children}
        </div>

        {footer}
      </div>

      {note != null && (
        <p style={{ textAlign: 'center', color: T.muted, fontSize: 11, marginTop: 14 }}>{note}</p>
      )}
    </div>
  );
}
