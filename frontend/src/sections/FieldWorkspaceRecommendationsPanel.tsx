import { UnifiedRecommendations } from './RecommendationPage';

export type FieldWorkspaceRecommendationsPanelProps = {
  fieldId: string;
  seasonId?: string | null;
};

export default function FieldWorkspaceRecommendationsPanel({ fieldId }: FieldWorkspaceRecommendationsPanelProps) {
  return (
    <section className="space-y-4" dir="rtl" aria-label="توصيات الحقل">
      <header className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
        <h2 className="text-base font-bold text-slate-100">توصيات الحقل الحالية</h2>
        <p className="mt-2 text-sm text-slate-400">توصيات الخدمة للحقل وموسمه الحالي، وليست إعادة بناء لموسم تاريخي من الرابط. يعرض كل بند مصدره، وتظهر متطلبات المراجعة كما أعادتها الخدمة. لا تنفذ هذه الشاشة أوامر تشغيل.</p>
      </header>
      <UnifiedRecommendations fieldId={fieldId} />
    </section>
  );
}
