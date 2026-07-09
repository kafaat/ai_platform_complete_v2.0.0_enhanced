import { useMemo, useState } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import FieldWorkspaceMapCard from './FieldWorkspaceMapCard';
import FieldWorkspaceTabs from './FieldWorkspaceTabs';
import FieldWorkspaceDataPanels from './FieldWorkspaceDataPanels';
import FieldWorkspaceTimelinePanel from './FieldWorkspaceTimelinePanel';
import FieldWorkspacePriorityPanel from './FieldWorkspacePriorityPanel';
import FieldWorkspaceOperationsPanel from './FieldWorkspaceOperationsPanel';
import FieldWorkspaceRecommendationsPanel from './FieldWorkspaceRecommendationsPanel';
import FieldWorkspaceReportsPanel from './FieldWorkspaceReportsPanel';
import FieldWorkspaceImageryPanel from './FieldWorkspaceImageryPanel';
import FieldWorkspaceWeatherPanel from './FieldWorkspaceWeatherPanel';
import FieldWorkspaceIrrigationPanel from './FieldWorkspaceIrrigationPanel';
import FieldWorkspaceContextBanner from './FieldWorkspaceContextBanner';
import { EmptyState } from '../components/StateViews';
import { normalizeWorkspaceTab, type FieldWorkspaceTab } from './fieldWorkspaceContract';
import { useSelectedField } from '../hooks/useSelectedField';

// Workspace contract: لا تعرض أرقاماً أو توصيات أو صوراً قبل ربط مصدر بيانات فعلي.
export default function FieldWorkspaceRouteShell() {
  const params = useParams<{ fieldId?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const selected = useSelectedField({ routeFieldId: params.fieldId ?? null });
  const fieldId = params.fieldId ?? selected.fieldId ?? '';
  const seasonId = searchParams.get('season_id') ?? searchParams.get('seasonId');
  const [activeTab, setActiveTab] = useState<FieldWorkspaceTab>(() => normalizeWorkspaceTab(searchParams.get('tab')));

  const contextSource = useMemo(() => (params.fieldId ? 'route' : fieldId ? 'selected-field' : 'unknown'), [params.fieldId, fieldId]);

  function setTab(tab: FieldWorkspaceTab) {
    setActiveTab(tab);
    const next = new URLSearchParams(searchParams);
    next.set('tab', tab);
    setSearchParams(next, { replace: true });
  }

  if (!fieldId) {
    return (
      <main className="space-y-4" dir="rtl" aria-label="مساحة عمل الحقل">
        <header className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
          <h1 className="text-xl font-bold text-slate-100">مساحة عمل الحقل</h1>
          <p className="text-sm text-slate-400 mt-1">اختر حقلاً أو افتح رابطاً يتضمن field_id.</p>
        </header>
        <EmptyState title="لا يوجد حقل نشط" hint="مساحة العمل لا تعمل بدون field_id حقيقي." />
      </main>
    );
  }

  return (
    <main className="space-y-4" dir="rtl" aria-label="مساحة عمل الحقل">
      <header className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs text-emerald-300">Field Workspace · {contextSource}</p>
            <h1 className="text-xl font-bold text-slate-100">مساحة عمل الحقل</h1>
            <p className="text-sm text-slate-400 mt-1">
              context: <code>{fieldId}</code>{seasonId ? <> · season: <code>{seasonId}</code></> : ' · لا يوجد موسم نشط في الرابط'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => navigate('/')}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 hover:border-emerald-500"
          >
            <ArrowRight className="w-4 h-4" aria-hidden="true" />
            العودة لمركز الخرائط
          </button>
        </div>
      </header>

      <FieldWorkspaceContextBanner fieldId={fieldId} seasonId={seasonId} activeTab={activeTab} />

      <FieldWorkspaceTabs activeTab={activeTab} seasonId={seasonId} onChange={setTab} />

      {activeTab === 'overview' && (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
            <FieldWorkspaceMapCard fieldId={fieldId} showPicker={false} />
            <FieldWorkspacePriorityPanel fieldId={fieldId} />
          </div>
          <FieldWorkspaceDataPanels fieldId={fieldId} />
          <FieldWorkspaceTimelinePanel fieldId={fieldId} seasonId={seasonId} />
        </div>
      )}

      {activeTab === 'map' && <FieldWorkspaceMapCard fieldId={fieldId} showPicker={false} />}
      {activeTab === 'season' && <FieldWorkspaceTimelinePanel fieldId={fieldId} seasonId={seasonId} />}
      {activeTab === 'imagery' && <FieldWorkspaceImageryPanel fieldId={fieldId} />}
      {activeTab === 'weather' && <FieldWorkspaceWeatherPanel fieldId={fieldId} seasonId={seasonId} />}
      {activeTab === 'irrigation' && <FieldWorkspaceIrrigationPanel fieldId={fieldId} seasonId={seasonId} />}
      {activeTab === 'operations' && <FieldWorkspaceOperationsPanel fieldId={fieldId} seasonId={seasonId} />}
      {activeTab === 'recommendations' && <FieldWorkspaceRecommendationsPanel fieldId={fieldId} seasonId={seasonId} />}
      {activeTab === 'reports' && <FieldWorkspaceReportsPanel fieldId={fieldId} seasonId={seasonId} />}
    </main>
  );
}
