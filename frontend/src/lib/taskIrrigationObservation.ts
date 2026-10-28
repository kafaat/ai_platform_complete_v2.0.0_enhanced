import type { TaskIrrigationObservation } from "../services/api/taskIrrigationObservations";

export function buildTaskIrrigationObservation(
  form: Record<string, string>,
  id: string,
): TaskIrrigationObservation {
  if (!form.execution_id) throw new Error("اختر عملية ري محفوظة");
  const occurred = new Date(form.occurred_at);
  if (!form.occurred_at || !Number.isFinite(occurred.getTime()))
    throw new Error("أدخل وقت المشاهدة");
  if (occurred.getTime() > Date.now() + 60_000)
    throw new Error("وقت المشاهدة لا يكون في المستقبل");
  const outcome = form.outcome as TaskIrrigationObservation["outcome"];
  const source = form.source as TaskIrrigationObservation["source"];
  if (!["irrigated", "not_irrigated", "unknown"].includes(outcome))
    throw new Error("اختر نتيجة المشاهدة");
  if (!["farmer_task", "field_inspection"].includes(source))
    throw new Error("اختر مصدر المشاهدة");
  const method =
    outcome === "irrigated"
      ? (form.quantity_method as TaskIrrigationObservation["quantity_method"])
      : "unknown";
  if (
    !["meter", "estimated_flow", "declared_volume", "unknown"].includes(method)
  )
    throw new Error("اختر طريقة تحديد الكمية");
  const number = (
    key: string,
    label: string,
    required = true,
  ): number | undefined => {
    if (!form[key]?.trim()) {
      if (required) throw new Error(`أدخل ${label}`);
      return undefined;
    }
    const n = Number(form[key]);
    if (!Number.isFinite(n) || n < 0)
      throw new Error(`${label}: أدخل رقماً محدوداً غير سالب`);
    return n;
  };
  const body: TaskIrrigationObservation = {
    observation_id: id,
    execution_id: form.execution_id,
    source,
    outcome,
    occurred_at: occurred.toISOString(),
    quantity_method: method,
    interruptions_minutes: 0,
    volume_m3: null,
    ...(form.notes?.trim() ? { notes: form.notes.trim() } : {}),
  };
  const area =
    outcome === "irrigated"
      ? number("irrigated_area_ha", "المساحة المروية", false)
      : undefined;
  if (area !== undefined) {
    if (area === 0) throw new Error("المساحة المروية يجب أن تكون أكبر من صفر");
    body.irrigated_area_ha = area;
  }
  if (method === "meter") {
    body.meter_start_m3 = number("meter_start_m3", "قراءة العداد قبل الري");
    body.meter_end_m3 = number("meter_end_m3", "قراءة العداد بعد الري");
    if (body.meter_end_m3! < body.meter_start_m3!)
      throw new Error(
        "قراءة نهاية العداد أقل من البداية؛ تحقّق من إعادة ضبط العداد",
      );
  } else if (method === "estimated_flow") {
    body.flow_m3_h = number(
      "flow_m3_h",
      "التدفق التقديري بالمتر المكعب لكل ساعة",
    );
    body.duration_minutes = number("duration_minutes", "مدة الري بالدقائق");
    body.interruptions_minutes =
      number("interruptions_minutes", "دقائق الانقطاع", false) ?? 0;
    if (body.flow_m3_h! <= 0 || body.duration_minutes! <= 0)
      throw new Error("التدفق والمدة يجب أن يكونا أكبر من صفر");
    if (body.interruptions_minutes >= body.duration_minutes!)
      throw new Error("الانقطاع يجب أن يكون أقل من مدة الري");
  } else if (method === "declared_volume") {
    body.volume_m3 = number("volume_m3", "الحجم المصرح به");
  }
  return body;
}

// This record is the immutable submitted intent, not an editable form draft.
export function pendingObservationKey(
  tenant: string,
  actor: string,
  taskId: string,
): string {
  return `sahool:irrigation-observation:v1:${JSON.stringify([tenant, actor, taskId])}`;
}
