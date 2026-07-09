import { Lightbulb } from 'lucide-react';
import { EmptyState } from '../components/StateViews';

export type FieldWorkspaceRecommendationsPanelProps = {
  fieldId: string;
  seasonId?: string | null;
};

/**
 * UI-22 honest recommendation shell.
 * Recommendations must come from a future evidence-backed endpoint; this shell
 * intentionally refuses to fabricate agronomic advice from UI-only context.
 */
export default function FieldWorkspaceRecommendationsPanel({ fieldId, seasonId }: FieldWorkspaceRecommendationsPanelProps) {
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5" dir="rtl" aria-label="توصيات الحقل">
      <div className="mb-4 flex items-start gap-3">
        <Lightbulb className="mt-1 h-5 w-5 text-emerald-300" aria-hidden="true" />
        <div>
          <h2 className="text-base font-bold text-slate-100">التوصيات</h2>
          <p className="mt-1 text-sm leading-relaxed text-slate-400">
            تعرض هذه المساحة توصيات ذات مصدر وسبب وثقة فقط. لا تُحوّل مؤشرات الخريطة إلى نصائح زراعية دون evidence lineage.
          </p>
          <p className="mt-2 text-xs text-slate-500">
            context: <code>{fieldId}</code>{seasonId ? <> · season: <code>{seasonId}</code></> : ' · لا موسم نشط'}
          </p>
        </div>
      </div>
      <EmptyState title="لا توجد توصيات موثقة" hint="سيتم عرض التوصيات بعد ربط endpoint يعيد recommendation_id + evidence + confidence." />
    </section>
  );
}
