// ═══════════════════════════════════════════════════════════════
// SAHOOL — قشرة التطبيق الموحّدة (Unified Cabin) · تجميع الوجهات الستّ
// ───────────────────────────────────────────────────────────────
// تجسيد UI_DESIGN_SPEC_UNIFIED.md §1 (معماريّة المعلومات): شريط وجهات سفليّ
// بستّ وجهات (القيادة · الخريطة · التخطيط · المراقبة · التحليل · الإعداد) يستضيف
// شاشات الدمج الخمس المبنيّة فعلاً في تطبيقٍ واحد، بدل صفحات «معاينة» متفرّقة.
//
// صدق: لا تلفيق. الوجهات الست تعرض شاشاتها الموحّدة المبنيّة مباشرةً؛ «التخطيط»
// يجمع شاشتَي التخطيط (توصية←تنفيذ + المهام) عبر TabBar؛ و«التحليل/الإعداد»
// أصبحتا شاشتَين موحّدتَين حقيقيّتَين (قراءة فقط) — لم تعد أيّ وجهة «قيد الإنشاء».
// ═══════════════════════════════════════════════════════════════
import { useState, lazy, Suspense } from 'react';
import type { ReactNode } from 'react';
import {
  Gauge, Map as MapIcon, ClipboardList, Activity, BarChart3, Settings, Loader2,
} from 'lucide-react';
import { T, BottomTabBar, TabBar } from '../components/ds';

const OperationCommand  = lazy(() => import('./OperationCommand'));
const FieldMapCenter    = lazy(() => import('./FieldMapCenter'));
const RecommendationFlow = lazy(() => import('./RecommendationFlow'));
const FieldTasksCabin   = lazy(() => import('./FieldTasksCabin'));
const HybridMonitor     = lazy(() => import('./HybridMonitor'));
const AnalyzeCabin      = lazy(() => import('./AnalyzeCabin'));
const SetupCabin        = lazy(() => import('./SetupCabin'));

type DestId = 'command' | 'map' | 'plan' | 'monitor' | 'analyze' | 'setup';
const DESTS: { id: DestId; label: string; icon: ReactNode }[] = [
  { id: 'command', label: 'القيادة', icon: <Gauge style={{ width: 16, height: 16 }} /> },
  { id: 'map', label: 'الخريطة', icon: <MapIcon style={{ width: 16, height: 16 }} /> },
  { id: 'plan', label: 'التخطيط', icon: <ClipboardList style={{ width: 16, height: 16 }} /> },
  { id: 'monitor', label: 'المراقبة', icon: <Activity style={{ width: 16, height: 16 }} /> },
  { id: 'analyze', label: 'التحليل', icon: <BarChart3 style={{ width: 16, height: 16 }} /> },
  { id: 'setup', label: 'الإعداد', icon: <Settings style={{ width: 16, height: 16 }} /> },
];

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
      case 'setup': return <SetupCabin />;
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
