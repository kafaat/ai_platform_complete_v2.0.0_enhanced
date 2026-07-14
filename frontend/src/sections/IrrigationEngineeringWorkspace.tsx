import { IRRIGATION_ENGINEERING_SECTIONS, type IrrigationEngineeringSummary } from "../lib/irrigationEngineering";

type Props = {
  summary?: IrrigationEngineeringSummary | null;
  onCalculate?: () => void;
  onConfirmManualExecution?: () => void;
};

export function IrrigationEngineeringWorkspace({ summary, onCalculate, onConfirmManualExecution }: Props) {
  return (
    <section aria-label="Vendor-neutral irrigation engineering workspace" className="space-y-4">
      <header>
        <h2 className="text-xl font-semibold">هندسة نظام الري</h2>
        <p className="text-sm text-muted-foreground">مواصفات وحسابات محايدة عن الشركة المصنعة، للتشغيل اليدوي أو المراقب أو الآلي.</p>
      </header>
      <nav aria-label="Irrigation engineering sections" className="flex flex-wrap gap-2">
        {IRRIGATION_ENGINEERING_SECTIONS.map((section) => <span key={section} className="rounded border px-2 py-1 text-xs">{section}</span>)}
      </nav>
      {!summary ? (
        <button type="button" onClick={onCalculate}>احسب قابلية النظام</button>
      ) : (
        <div className="space-y-3">
          <div data-status={summary.status}>الحالة: {summary.status}</div>
          <div>الحجم المستهدف: {summary.manual_operation.target_volume_m3} م³</div>
          <div>مدة التشغيل: {summary.manual_operation.estimated_runtime_h ?? "غير متاحة"}</div>
          <div>وضع التنفيذ: {summary.manual_operation.execution_mode}</div>
          {summary.blocking_constraints.length > 0 && (
            <ul>{summary.blocking_constraints.map((item) => <li key={item}>{item}</li>)}</ul>
          )}
          {summary.manual_operation.execution_mode.startsWith("manual_") && (
            <button type="button" onClick={onConfirmManualExecution}>تأكيد التنفيذ اليدوي</button>
          )}
        </div>
      )}
    </section>
  );
}
