import { Wrench } from 'lucide-react';
import FieldWorkspacePriorityPanel from './FieldWorkspacePriorityPanel';
import FieldWorkspaceTasksPanel from './FieldWorkspaceTasksPanel';

export type FieldWorkspaceOperationsPanelProps = {
  fieldId: string;
  seasonId?: string | null;
};

export default function FieldWorkspaceOperationsPanel({ fieldId, seasonId }: FieldWorkspaceOperationsPanelProps) {
  return (
    <section className="space-y-4" dir="rtl" aria-label="تشغيل الحقل">
      <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
        <div className="flex items-start gap-3">
          <Wrench className="mt-1 h-5 w-5 text-emerald-300" aria-hidden="true" />
          <div>
            <h2 className="text-base font-bold text-slate-100">تشغيل الحقل</h2>
            <p className="mt-1 text-sm leading-relaxed text-slate-400">
              يجمع هذا التبويب قائمة الأولويات والمهام الفعلية للحقل. لا تُنشأ أوامر تشغيل أو مهام من الواجهة بدون endpoint كتابة صريح وسجلّ evidence.
            </p>
            <p className="mt-2 text-xs text-slate-500">
              context: <code>{fieldId}</code>{seasonId ? <> · season: <code>{seasonId}</code></> : ' · لا موسم نشط'}
            </p>
          </div>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <FieldWorkspacePriorityPanel fieldId={fieldId} />
        <FieldWorkspaceTasksPanel fieldId={fieldId} />
      </div>
    </section>
  );
}
