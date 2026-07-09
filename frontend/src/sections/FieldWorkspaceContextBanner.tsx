import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import { FIELD_WORKSPACE_TABS, type FieldWorkspaceTab } from './fieldWorkspaceContract';
import { getWorkspaceTabAvailability, listUnavailableWorkspaceTabs } from './fieldWorkspaceAvailability';

export interface FieldWorkspaceContextBannerProps {
  fieldId: string;
  seasonId?: string | null;
  activeTab: FieldWorkspaceTab;
}

export default function FieldWorkspaceContextBanner({ fieldId, seasonId, activeTab }: FieldWorkspaceContextBannerProps) {
  const active = getWorkspaceTabAvailability(activeTab, { fieldId, seasonId });
  const missing = listUnavailableWorkspaceTabs({ fieldId, seasonId });
  const activeLabel = FIELD_WORKSPACE_TABS.find((tab) => tab.id === activeTab)?.label_ar ?? activeTab;

  return (
    <section
      className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 text-sm text-slate-200"
      aria-label="حالة سياق مساحة عمل الحقل"
      dir="rtl"
    >
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="space-y-1">
          <p className="text-xs text-slate-400">سياق التشغيل الحالي</p>
          <p>
            field_id: <code className="text-emerald-200">{fieldId}</code>
            {' · '}
            season_id: {seasonId ? <code className="text-emerald-200">{seasonId}</code> : <span className="text-amber-200">غير محدد</span>}
            {' · '}
            tab: <span className="text-slate-100">{activeLabel}</span>
          </p>
          <p className="text-xs text-slate-500">لا يتم إنشاء موسم أو توصيات أو جداول بديلة من الواجهة عند غياب السياق.</p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-2">
          {active.available ? (
            <div className="inline-flex items-center gap-2 text-emerald-200">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              التبويب الحالي قابل للعرض من السياق المتاح.
            </div>
          ) : (
            <div className="inline-flex items-center gap-2 text-amber-200">
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
              {active.reason_ar}
            </div>
          )}
        </div>
      </div>

      {missing.length > 0 && (
        <p className="mt-3 text-xs text-slate-400">
          تبويبات تتطلب سياقاً إضافياً: {missing.map((m) => `${m.tab}: ${m.reason_ar}`).join(' · ')}
        </p>
      )}
    </section>
  );
}
