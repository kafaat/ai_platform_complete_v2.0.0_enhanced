/** Opens the farm book on this task. Needs only the expense-write permission (activity:execute),
 *  so a worker records the receipt without the analytics permission or any cost total. */
export function TaskExpenseLink({ taskId, fieldId, farmId, amount }: {
  taskId: string; fieldId: string; farmId?: string; amount?: number | null;
}) {
  const params = new URLSearchParams({ task_id: taskId, field_id: fieldId });
  if (farmId) params.set('farm_id', farmId);
  if (amount != null && amount > 0) params.set('cost_usd', String(amount));
  return <a href={'/ops/farm-book?' + params.toString()} className="underline">تسجيل مصروف لهذه المهمة</a>;
}
