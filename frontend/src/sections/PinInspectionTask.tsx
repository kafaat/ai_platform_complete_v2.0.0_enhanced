import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { kongApi } from "../services/api";
import { InspectionHandoff } from "./InspectionHandoff";
import { normalizeRole } from "../lib/permissions";

type Pin = { id: string; lat: number; lng: number };
type Task = {
  task_id: string;
  assigned_to: string;
  due_at: string;
  status: string;
  priority: number;
};
type Person = { id: number; full_name: string };

function Inspection({
  field,
  pin,
  tenant,
  editable,
}: {
  field: string;
  pin: string;
  tenant: string;
  editable: boolean;
}) {
  const [person, setPerson] = useState("");
  const [due, setDue] = useState("");
  const [priority, setPriority] = useState("3");
  const qc = useQueryClient();
  // field-management-service owns pin inspection tasks (gateway /api/v1/field-tasks/).
  const path = `/api/v1/field-tasks/fields/${encodeURIComponent(field)}/pins/${encodeURIComponent(pin)}/inspection-task`;
  const key = ["pin-inspection", tenant, field, pin];
  const task = useQuery({
    queryKey: key,
    queryFn: async () =>
      (await kongApi.get<{ task: Task | null }>(path)).data.task,
  });
  const team = useQuery({
    queryKey: ["inspection-assignees", tenant, field],
    enabled: editable,
    queryFn: async () =>
      (
        await kongApi.get<{ assignees: Person[] }>(
          `/api/v1/field-tasks/fields/${encodeURIComponent(field)}/inspection-assignees`,
        )
      ).data.assignees,
  });
  const save = useMutation({
    mutationFn: async () => {
      // datetime-local uses the supervisor's local time; send the offset so the field date is retained.
      const offset = -new Date(due).getTimezoneOffset();
      const zone = `${offset < 0 ? "-" : "+"}${String(Math.floor(Math.abs(offset) / 60)).padStart(2, "0")}:${String(Math.abs(offset) % 60).padStart(2, "0")}`;
      return (
        await kongApi.post<{ task: Task; persisted: boolean }>(path, {
          assigned_to: Number(person),
          due_at: due + zone,
          priority: Number(priority),
        })
      ).data;
    },
    onSuccess: (data) => {
      if (data.persisted) qc.setQueryData(key, data.task);
      void qc.invalidateQueries({ queryKey: ["tasks", tenant] });
    },
    onError: () => {
      void task.refetch();
    },
  });
  if (task.isError) return <span role="alert">تعذّر جلب تكليف الدبوس</span>;
  if (task.isPending) return <span>جارٍ جلب التكليف…</span>;
  const assignment = task.data;
  if (assignment)
    return (
      <>
        <p>
          مهمة التفتيش {assignment.task_id} · المستلم{" "}
          {team.data?.find((p) => String(p.id) === assignment.assigned_to)
            ?.full_name ?? assignment.assigned_to}{" "}
          · {new Date(assignment.due_at).toLocaleString("ar")} ·{" "}
          {assignment.status}
        </p>
        <InspectionHandoff
          fieldId={field}
          taskId={assignment.task_id}
          tenant={tenant}
        />
      </>
    );
  if (!editable) return <p>لا توجد مهمة تفتيش لهذا الدبوس</p>;
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <label>
        المفتش{" "}
        <select
          required
          value={person}
          onChange={(e) => setPerson(e.target.value)}
        >
          <option value="">اختر المستلم</option>
          {team.data?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.full_name}
            </option>
          ))}
        </select>
      </label>
      <label>
        موعد النتيجة{" "}
        <input
          required
          type="datetime-local"
          value={due}
          onChange={(e) => setDue(e.target.value)}
        />
      </label>
      <label>
        الأولوية{" "}
        <select value={priority} onChange={(e) => setPriority(e.target.value)}>
          {[1, 2, 3, 4, 5].map((n) => (
            <option key={n}>{n}</option>
          ))}
        </select>
      </label>
      <button type="submit" disabled={save.isPending || !person || !due}>
        تكليف بزيارة تفتيش
      </button>
      {team.isError && <span role="alert">تعذّر جلب المستلمين</span>}
      {save.isError && <span role="alert">تعذّر تأكيد التكليف</span>}
    </form>
  );
}

export function PinInspectionTask({
  field,
  pins,
  role,
  tenant,
}: {
  field: string;
  pins: Pin[];
  role?: string;
  tenant: string;
}) {
  const [pin, setPin] = useState("");
  const selected = pins.find((p) => p.id === pin);
  return (
    <div className="mt-2 text-xs">
      <label>
        متابعة دبوس محفوظ{" "}
        <select
          value={selected?.id ?? ""}
          onChange={(e) => setPin(e.target.value)}
        >
          <option value="">اختر الدبوس</option>
          {pins.map((p) => (
            <option key={p.id} value={p.id}>
              {p.id} · {p.lat.toFixed(5)}, {p.lng.toFixed(5)}
            </option>
          ))}
        </select>
      </label>
      {selected && (
        <Inspection
          key={selected.id}
          field={field}
          pin={selected.id}
          tenant={tenant}
          editable={["owner", "manager"].includes(normalizeRole(role))}
        />
      )}
    </div>
  );
}
