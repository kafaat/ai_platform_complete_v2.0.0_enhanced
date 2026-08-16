// cabin.tsx — قشرة «الكابينة المحمولة» الموحّدة (DS).
// كانت الشاشات الثلاث (OperationCommand/FieldMapCenter/FieldTasksCabin) تكرّر
// نفس الغلاف حرفيّاً: خلفيّة كريميّة + بطاقة 420px + ترويسة بنّيّة + تعليق سفليّ.
// وُحِّد هنا. footer اختياريّ (مثلاً BottomTabBar) يحوّل الكابينة إلى عمود مرن
// بمحتوًى قابل للتمرير وشريط مثبّت أسفلها (نمط FieldTasksCabin).
import type { ReactNode } from 'react';
import { T } from './tokens';
import { DsThemeProvider, useIsDark, useT, type DsTone } from './theme';

export function FieldCabin({
  eyebrow, title, headerRight, subtitle, footer, note, children, tone,
}: {
  eyebrow: ReactNode;       // وسم صغير ذهبيّ فوق العنوان (اسم الكابينة)
  title: ReactNode;         // العنوان الكبير
  headerRight?: ReactNode;  // عنصر يمين الترويسة (عادةً Pill)
  subtitle?: ReactNode;     // سطر وصفيّ تحت العنوان
  footer?: ReactNode;       // شريط سفليّ مثبّت (BottomTabBar) — يفعّل وضع العمود المرن
  note?: ReactNode;         // تعليق أسفل الكابينة (خارج البطاقة)
  tone?: DsTone;            // dark ⇒ أسطح داكنة بعرض ويب (960px) للأحفاد · غيابه يرث نغمة الأصل
  children: ReactNode;      // جسم الكابينة (البطاقات)
}) {
  return (
    <DsThemeProvider tone={tone}>
      <FieldCabinInner
        eyebrow={eyebrow} title={title} headerRight={headerRight} subtitle={subtitle}
        footer={footer} note={note}
      >
        {children}
      </FieldCabinInner>
    </DsThemeProvider>
  );
}

function FieldCabinInner({
  eyebrow, title, headerRight, subtitle, footer, note, children,
}: {
  eyebrow: ReactNode;
  title: ReactNode;
  headerRight?: ReactNode;
  subtitle?: ReactNode;
  footer?: ReactNode;
  note?: ReactNode;
  children: ReactNode;
}) {
  const t = useT();
  const hasFooter = footer != null;
  const dark = useIsDark();   // النغمة المحلولة (الموروثة أو المفروضة) لا الـprop وحده
  return (
    <div dir="rtl" style={{ background: t.cream, minHeight: '100%', padding: 16 }}>
      <div
        style={{
          maxWidth: dark ? 960 : 420, margin: '0 auto', background: t.cream,
          borderRadius: 22, border: `1px solid ${t.line}`, overflow: 'hidden',
          boxShadow: dark ? '0 12px 40px rgba(0,0,0,.45)' : '0 12px 40px rgba(44,26,14,.10)',
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
            <div style={{ fontSize: 11, color: t.subtitle, marginTop: 6 }}>{subtitle}</div>
          )}
        </div>

        {/* ── الجسم (يتمدّد ويتمرّر حين يوجد footer) ── */}
        <div style={{ padding: 14, ...(hasFooter ? { flex: 1, overflowY: 'auto' } : null) }}>
          {children}
        </div>

        {footer}
      </div>

      {note != null && (
        <p style={{ textAlign: 'center', color: t.muted, fontSize: 11, marginTop: 14 }}>{note}</p>
      )}
    </div>
  );
}
