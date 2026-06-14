// ═══════════════════════════════════════════════════════════════
// SAHOOL — قشرة التطبيق الموحّدة (Unified Cabin) · تجميع الوجهات الستّ
// ───────────────────────────────────────────────────────────────
// تجسيد UI_DESIGN_SPEC_UNIFIED.md §1 (معماريّة المعلومات): شريط وجهات سفليّ
// بستّ وجهات (القيادة · الخريطة · التخطيط · المراقبة · التحليل · الإعداد) يستضيف
// شاشات الدمج الخمس المبنيّة فعلاً في تطبيقٍ واحد، بدل صفحات «معاينة» متفرّقة.
//
// صدق: لا تلفيق. الوجهات الأربع ذات الشاشات الموحّدة المبنيّة تعرضها مباشرةً؛
// «التخطيط» يجمع شاشتَي التخطيط (توصية←تنفيذ + المهام) عبر TabBar؛ ووجهتا
// «التحليل/الإعداد» اللتان لم تُبنَ وحدتهما الموحّدة بعد تُظهران بطاقة «قيد
// الإنشاء» صريحة (تشيران للقسم الكلاسيكيّ القائم) — لا شاشة مزيّفة.
// ═══════════════════════════════════════════════════════════════
import { useState, lazy, Suspense } from 'react';
import type { ReactNode } from 'react';
import {
  Gauge, Map as MapIcon, ClipboardList, Activity, BarChart3, Settings, Loader2, Hammer,
} from 'lucide-react';
import { T, Card, SectionLabel, FieldCabin, BottomTabBar, TabBar } from '../components/ds';

const OperationCommand  = lazy(() => import('./OperationCommand'));
const FieldMapCenter    = lazy(() => import('./FieldMapCenter'));
const RecommendationFlow = lazy(() => import('./RecommendationFlow'));
const FieldTasksCabin   = lazy(() => import('./FieldTasksCabin'));
const HybridMonitor     = lazy(() => import('./HybridMonitor'));
const AnalyzeCabin      = lazy(() => import('./AnalyzeCabin'));

type DestId = 'command' | 'map' | 'plan' | 'monitor' | 'analyze' | 'setup';
const DESTS: { id: DestId; label: string; icon: ReactNode }[] = [
  { id: 'command', label: 'القيادة', icon: <Gauge style={{ width: 16, height: 16 }} /> },
  { id: 'map', label: 'الخريطة', icon: <MapIcon style={{ width: 16, height: 16 }} /> },
  { id: 'plan', label: 'التخطيط', icon: <ClipboardList style={{ width: 16, height: 16 }} /> },
  { id: 'monitor', label: 'المراقبة', icon: <Activity style={{ width: 16, height: 16 }} /> },
  { id: 'analyze', label: 'التحليل', icon: <BarChart3 style={{ width: 16, height: 16 }} /> },
  { id: 'setup', label: 'الإعداد', icon: <Settings style={{ width: 16, height: 16 }} /> },
];

// وجهة لم تُبنَ وحدتها الموحّدة بعد — بطاقة صادقة تشير للقسم الكلاسيكيّ.
function ComingSoon({ title, classic }: { title: string; classic: string }) {
  return (
    <FieldCabin
      eyebrow="التطبيق الموحّد"
      title={title}
      note={<>الوحدة الموحّدة لهذه الوجهة لم تُبنَ بعد — يغطّيها القسم الكلاسيكيّ «{classic}» في القائمة الجانبيّة.</>}
    >
      <Card pad={16}>
        <SectionLabel>قيد الإنشاء</SectionLabel>
        <div className="flex flex-col items-center" style={{ gap: 10, padding: '20px 0', color: T.muted, textAlign: 'center' }}>
          <Hammer style={{ width: 30, height: 30, color: T.faint }} />
          <div style={{ fontSize: 14, fontWeight: 700, color: T.ink }}>وجهة «{title}»</div>
          <div style={{ fontSize: 12, lineHeight: 1.7 }}>
            الوحدة الموحّدة لهذه الوجهة ضمن خطّة الكسوة التاليّة. حتى تُبنى، استخدم قسم
            «{classic}» الكلاسيكيّ — لا نعرض شاشة مزيّفة هنا.
          </div>
        </div>
      </Card>
    </FieldCabin>
  );
}

// وجهة «التخطيط» — تجمع شاشتَي التخطيط المبنيّتين عبر مبدّل علويّ.
type PlanTab = 'rec' | 'tasks';
function PlanDestination() {
  const [tab, setTab] = useState<PlanTab>('rec');
  return (
    <div>
      <div style={{ maxWidth: 420, margin: '0 auto', padding: '12px 16px 0' }}>
        <TabBar
          tabs={[{ id: 'rec' as PlanTab, label: 'توصية ← تنفيذ' }, { id: 'tasks' as PlanTab, label: 'المهام' }]}
          active={tab}
          onChange={setTab}
        />
      </div>
      {tab === 'rec' ? <RecommendationFlow /> : <FieldTasksCabin />}
    </div>
  );
}

export default function UnifiedCabin() {
  const [dest, setDest] = useState<DestId>('command');

  function renderDest() {
    switch (dest) {
      case 'command': return <OperationCommand />;
      case 'map': return <FieldMapCenter />;
      case 'plan': return <PlanDestination />;
      case 'monitor': return <HybridMonitor />;
      case 'analyze': return <AnalyzeCabin />;
      case 'setup': return <ComingSoon title="الإعداد" classic="إدارة الحقول/المعدّات" />;
    }
  }

  return (
    <div dir="rtl" style={{ minHeight: '100%', background: T.cream, paddingBottom: 8 }}>
      <Suspense
        fallback={
          <div className="flex items-center justify-center" style={{ padding: '60px 0' }}>
            <Loader2 className="animate-spin" style={{ width: 28, height: 28, color: T.green }} />
          </div>
        }
      >
        {/* مفتاح الوجهة يُعيد تركيب الشاشة عند التبديل (حالة نظيفة لكلّ وجهة) */}
        <div key={dest}>{renderDest()}</div>
      </Suspense>

      {/* شريط الوجهات الستّ — لاصق بأسفل منطقة المحتوى */}
      <div style={{ position: 'sticky', bottom: 0, zIndex: 50, maxWidth: 420, margin: '0 auto' }}>
        <BottomTabBar tabs={DESTS} active={dest} onChange={setDest} />
      </div>
    </div>
  );
}
