// ═══════════════════════════════════════════════════════════════
// SAHOOL — قشرة FieldView · لوحة الأوامر (Command Palette · ⌘K)
// ───────────────────────────────────────────────────────────────
// لوحة بحث/تنقّل سريعة (cmdk) تُفتح بـCtrl/⌘-K، تَسرد كلّ صفحات سجلّ
// المسارات القابلة للوصول (مُرشَّحة بـcanAccess + isPageEnabled تماماً كـNavRail)،
// مُجمَّعة وفق أقسام بنية المعلومات، وتُنقِّل عبر useNavigate(). RTL، نائب نصّ
// عربيّ، حركة تحترم prefers-reduced-motion. لا تخترع سياسة وصول جديدة —
// تستهلك البوّابات نفسها التي يستهلكها الشريط الجانبيّ.
// ═══════════════════════════════════════════════════════════════
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Command } from 'cmdk';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { Search } from 'lucide-react';
import { useAuthStore } from '../../hooks/useAuth';
import { canAccess } from '../../lib/permissions';
import { isPageEnabled } from '../../lib/featureFlags';
import { isRuntimePageEnabled, useFeatureRegistry } from '../../hooks/useFeatureRegistry';
import { NAV_SECTIONS, maturityBadge, type RouteDef } from '../../lib/routes';

/**
 * يُفتح/يُغلق بـ⌘K (أو Ctrl-K). يُدار حالة الفتح داخليّاً (لا يحتاج المستهلك
 * تمرير شيء) كي يبقى وصله بـAppShell سطراً واحداً.
 */
export default function CommandPalette() {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const reduce = useReducedMotion();
  const featureRegistry = useFeatureRegistry();
  const [open, setOpen] = useState(false);

  // فتح/طيّ بـ⌘K / Ctrl-K (يُلتقَط عالميّاً، يمنع سلوك المتصفّح الافتراضيّ).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  // مُرشِّح موحّد مطابق لـNavRail: مُفعّلة بناءً (علم الميزة) + وقت‌تشغيلاً (سجلّ الميزات
  // الحيّ) + يحقّ للدور فتحها (RBAC). إضافة isRuntimePageEnabled تُوحّد الترشيح مع NavRail
  // فلا تظهر صفحة معطَّلة وقت‌تشغيلاً في لوحة الأوامر بينما هي مخفيّة في الشريط — F-UI-02.
  const allowed = (r: RouteDef) => isPageEnabled(r.id) && isRuntimePageEnabled(r.id, featureRegistry) && canAccess(user?.role, r.id) && !r.hidden;

  // أقسام بعناصرها المسموح بها فقط؛ قسم بلا عناصر يُسقَط (لا رأس فارغ).
  const sections = NAV_SECTIONS
    .map((s) => ({ ...s, items: s.items.filter(allowed) }))
    .filter((s) => s.items.length > 0);

  const go = (r: RouteDef) => {
    setOpen(false);
    navigate(r.path);
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[60] flex items-start justify-center"
          style={{ background: 'rgba(2,6,12,.6)', padding: '12vh 16px 16px' }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reduce ? 0 : 0.15 }}
          onClick={() => setOpen(false)}
        >
          <motion.div
            dir="rtl"
            onClick={(e) => e.stopPropagation()}
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: -8, scale: 0.98 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: reduce ? 0 : 0.16 }}
            style={{ width: '100%', maxWidth: 560 }}
          >
            <Command
              label="لوحة الأوامر"
              className="rounded-xl overflow-hidden shadow-2xl"
              style={{ background: '#0d1117', border: '1px solid #1e293b' }}
            >
              <div className="flex items-center gap-2 px-3 border-b" style={{ borderColor: '#1e293b' }}>
                <Search className="w-4 h-4 text-slate-500 flex-shrink-0" />
                <Command.Input
                  autoFocus
                  placeholder="ابحث عن صفحة أو انتقل إليها…"
                  className="flex-1 bg-transparent py-3 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none text-right"
                />
                <kbd className="hidden sm:inline text-[10px] text-slate-500 border border-slate-700 rounded px-1.5 py-0.5">
                  Esc
                </kbd>
              </div>
              <Command.List className="max-h-[50vh] overflow-y-auto p-2">
                <Command.Empty className="py-6 text-center text-sm text-slate-500">
                  لا توجد نتائج مطابقة.
                </Command.Empty>
                {sections.map((section) => (
                  <Command.Group
                    key={section.id}
                    heading={section.label}
                    className="text-[11px] font-semibold text-slate-500 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5"
                  >
                    {section.items.map((item) => {
                      const Icon = item.icon;
                      const mat = maturityBadge(item.maturity);
                      return (
                        <Command.Item
                          key={item.id}
                          // قيمة البحث: التسمية + معرّف الصفحة (مطابقة عربيّ/لاتينيّ).
                          value={`${item.label} ${item.id}`}
                          onSelect={() => go(item)}
                          className="flex items-center gap-3 px-2 py-2 rounded-lg cursor-pointer text-sm text-slate-300 data-[selected=true]:bg-emerald-950 data-[selected=true]:text-emerald-300"
                        >
                          <Icon className="w-4 h-4 flex-shrink-0" />
                          <span className="flex-1 text-right">{item.label}</span>
                          {mat && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                              style={{ background: mat.bg, color: mat.fg }}>
                              {mat.label}
                            </span>
                          )}
                          {item.badge && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full"
                              style={{ background: '#16a34a22', color: '#4ade80' }}>
                              {item.badge}
                            </span>
                          )}
                        </Command.Item>
                      );
                    })}
                  </Command.Group>
                ))}
              </Command.List>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
