import type { ComponentType } from 'react';
import { Map, CalendarDays, CloudSun, Droplets, ClipboardList, FileText, Satellite, Lightbulb, LayoutDashboard } from 'lucide-react';
import { FIELD_WORKSPACE_TABS, type FieldWorkspaceTab } from './fieldWorkspaceContract';
import { getWorkspaceTabAvailability } from './fieldWorkspaceAvailability';

const ICONS: Record<FieldWorkspaceTab, ComponentType<{ className?: string }>> = {
  overview: LayoutDashboard,
  map: Map,
  season: CalendarDays,
  imagery: Satellite,
  weather: CloudSun,
  irrigation: Droplets,
  operations: ClipboardList,
  recommendations: Lightbulb,
  reports: FileText,
};

export interface FieldWorkspaceTabsProps {
  activeTab: FieldWorkspaceTab;
  seasonId?: string | null;
  onChange: (tab: FieldWorkspaceTab) => void;
}

export default function FieldWorkspaceTabs({ activeTab, seasonId, onChange }: FieldWorkspaceTabsProps) {
  return (
    <nav
      className="flex gap-2 overflow-x-auto rounded-2xl border border-slate-800 bg-slate-950/70 p-2"
      aria-label="تبويبات مساحة عمل الحقل"
      dir="rtl"
    >
      {FIELD_WORKSPACE_TABS.map((tab) => {
        const Icon = ICONS[tab.id];
        // Compatibility guard: this central helper preserves the old requires_season && !seasonId rule (يتطلب موسماً نشطاً).
        const availability = getWorkspaceTabAvailability(tab.id, { fieldId: 'route-or-selected', seasonId });
        const disabled = !availability.available;
        const selected = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => !disabled && onChange(tab.id)}
            disabled={disabled}
            aria-current={selected ? 'page' : undefined}
            title={disabled ? availability.reason_ar : tab.label_ar}
            className={[
              'inline-flex items-center gap-2 whitespace-nowrap rounded-xl px-3 py-2 text-sm border transition',
              selected ? 'border-emerald-500 bg-emerald-950/60 text-emerald-100' : 'border-slate-800 bg-slate-900/60 text-slate-300 hover:border-slate-600',
              disabled ? 'opacity-50 cursor-not-allowed hover:border-slate-800' : '',
            ].join(' ')}
          >
            <Icon className="w-4 h-4" aria-hidden="true" />
            <span>{tab.label_ar}</span>
          </button>
        );
      })}
    </nav>
  );
}
