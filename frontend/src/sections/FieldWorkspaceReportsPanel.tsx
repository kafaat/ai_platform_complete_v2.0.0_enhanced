import { FileText } from 'lucide-react';
import { EmptyState } from '../components/StateViews';

export type FieldWorkspaceReportsPanelProps = {
  fieldId: string;
  seasonId?: string | null;
};

/** UI-23 reports shell: no generated report is shown unless it exists server-side. */
export default function FieldWorkspaceReportsPanel({ fieldId, seasonId }: FieldWorkspaceReportsPanelProps) {
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5" dir="rtl" aria-label="تقارير الحقل">
      <div className="mb-4 flex items-start gap-3">
        <FileText className="mt-1 h-5 w-5 text-emerald-300" aria-hidden="true" />
        <div>
          <h2 className="text-base font-bold text-slate-100">التقارير</h2>
          <p className="mt-1 text-sm leading-relaxed text-slate-400">
            تعرض هذه الصفحة تقارير محفوظة فقط. لا تُولد PDF/CSV من بيانات غير مكتملة داخل الواجهة.
          </p>
          <p className="mt-2 text-xs text-slate-500">
            context: <code>{fieldId}</code>{seasonId ? <> · season: <code>{seasonId}</code></> : ' · لا موسم نشط'}
          </p>
        </div>
      </div>
      <EmptyState title="لا توجد تقارير محفوظة" hint="اربط endpoint تقارير يعيد report_id/status/download_url قبل إظهار أزرار تحميل." />
    </section>
  );
}
