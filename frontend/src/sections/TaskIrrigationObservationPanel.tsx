import { useEffect, useRef, useState } from "react";
import { useAuthStore } from "../hooks/useAuth";
import { canMutate } from "../lib/permissions";
import {
  buildTaskIrrigationObservation,
  pendingObservationKey,
} from "../lib/taskIrrigationObservation";
import {
  listManualExecutions,
  type ManualExecutionRecord,
} from "../services/api/irrigationManualOperations";
import {
  listTaskIrrigationObservations,
  recordTaskIrrigationObservation,
  type TaskIrrigationObservation,
  type StoredTaskIrrigationObservation,
} from "../services/api/taskIrrigationObservations";

const emptyForm = () => ({
  execution_id: "",
  source: "farmer_task",
  outcome: "unknown",
  quantity_method: "unknown",
  occurred_at: localNow(),
  interruptions_minutes: "0",
});
const outcomeAr = {
  irrigated: "تم الري",
  not_irrigated: "لم يتم الري",
  unknown: "غير معلوم",
};
const methodAr = {
  meter: "فرق عداد مقاس",
  estimated_flow: "تقدير من التدفق والمدة",
  declared_volume: "حجم مصرح به",
  unknown: "الكمية غير معلومة",
};
function localNow(value?: string) {
  const d = value ? new Date(value) : new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
}

export default function TaskIrrigationObservationPanel({
  taskId,
  fieldId,
  onClose,
}: {
  taskId: string;
  fieldId: string;
  onClose: () => void;
}) {
  const { tenantId, user } = useAuthStore();
  const actor = String(user?.id ?? user?.email ?? "");
  const writable = !!tenantId && !!actor && canMutate(user?.role);
  const key = pendingObservationKey(tenantId ?? "", actor, taskId);
  const [form, setForm] = useState<Record<string, string>>(emptyForm);
  const [executions, setExecutions] = useState<ManualExecutionRecord[]>([]);
  const [history, setHistory] = useState<StoredTaskIrrigationObservation[]>([]);
  const [pending, setPending] = useState<TaskIrrigationObservation | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [storageError, setStorageError] = useState(false);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError("");
    setPending(null);
    setForm(emptyForm());
    setHistory([]);
    setExecutions([]);
    setBusy(false);
    setError("");
    setNotice("");
    setStorageError(false);
    try {
      const raw = sessionStorage.getItem(key);
      if (raw) {
        const value = JSON.parse(raw) as TaskIrrigationObservation;
        if (!value.observation_id || !value.execution_id || !value.occurred_at)
          throw new Error("invalid pending record");
        setPending(value);
        setForm({
          ...Object.fromEntries(
            Object.entries(value)
              .filter(([, v]) => v != null)
              .map(([k, v]) => [k, String(v)]),
          ),
          occurred_at: localNow(value.occurred_at),
        });
      }
    } catch {
      setStorageError(true);
      setError(
        "تعذّر قراءة سجل المحاولة السابقة. لا ترسل مشاهدة جديدة قبل استعادة السجل.",
      );
    }
    Promise.all([
      listManualExecutions(fieldId),
      listTaskIrrigationObservations(taskId),
    ])
      .then(([ops, rows]) => {
        if (active) {
          setExecutions(ops.filter((op) => op.field_id === fieldId));
          setHistory(rows);
        }
      })
      .catch(() => {
        if (active)
          setLoadError(
            "تعذّر تحميل العمليات أو سجل المشاهدات. أعد فتح اللوحة للمحاولة.",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [fieldId, taskId, key]);

  const set = (name: string, value: string) => {
    setForm((old) => ({ ...old, [name]: value }));
    setError("");
  };
  const sameOwner = () => {
    const current = useAuthStore.getState();
    return (
      current.tenantId === tenantId &&
      String(current.user?.id ?? current.user?.email ?? "") === actor
    );
  };
  async function submit() {
    if (busy || !writable || storageError || !sameOwner()) return;
    const retryingUncertain = !!pending;
    let body = pending;
    if (!body) {
      try {
        if (!executions.some((op) => op.execution_id === form.execution_id))
          throw new Error("اختر عملية ري من القائمة المحفوظة لهذا الحقل");
        body = buildTaskIrrigationObservation(form, crypto.randomUUID());
        sessionStorage.setItem(key, JSON.stringify(body));
        setPending(body);
      } catch (e) {
        setError(
          e instanceof Error
            ? e.message
            : "تعذّر حفظ المحاولة محلياً؛ لم تُرسل",
        );
        return;
      }
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await recordTaskIrrigationObservation(taskId, body);
      if (!alive.current || !sameOwner()) return;
      sessionStorage.removeItem(key);
      setPending(null);
      setForm(emptyForm());
      setNotice(
        "حُفظت المشاهدة فقط؛ لم تُنجز المهمة ولم تُعتمد عملية الري أو تُرحّل كمية إلى دفتر المياه.",
      );
      try {
        const rows = await listTaskIrrigationObservations(taskId);
        if (alive.current && sameOwner()) setHistory(rows);
      } catch {
        if (alive.current && sameOwner())
          setLoadError(
            "حُفظت المشاهدة، وتعذّر تحديث السجل. أعد فتح اللوحة لقراءته.",
          );
      }
    } catch (e) {
      if (!alive.current || !sameOwner()) return;
      const status = (e as { response?: { status?: number } }).response?.status;
      // A rejection of a retry cannot disprove that the earlier attempt committed.
      if (
        !retryingUncertain &&
        [400, 401, 403, 404, 422].includes(status ?? 0)
      ) {
        try {
          sessionStorage.removeItem(key);
          setPending(null);
        } catch {
          setStorageError(true);
        }
        setError(
          "رفض الخادم المشاهدة. تحقّق من الصلاحية والعملية والبيانات قبل المحاولة.",
        );
      } else {
        setError(
          "لم نحسم نتيجة الحفظ. أعد إرسال المحاولة الأصلية بنفس بياناتها ومعرّفها؛ لا تنشئ مشاهدة بديلة.",
        );
      }
    } finally {
      if (alive.current && sameOwner()) setBusy(false);
    }
  }
  const locked = busy || !!pending || !writable || storageError;
  const numberInput = (name: string, label: string) => (
    <label className="block text-sm" key={name}>
      {label}
      <input
        type="number"
        min="0"
        step="any"
        value={form[name] ?? ""}
        onChange={(e) => set(name, e.target.value)}
        className="block w-full rounded border p-2 text-slate-900"
      />
    </label>
  );
  return (
    <section
      aria-label="مشاهدة الري للمهمة"
      dir="rtl"
      className="space-y-3 rounded-xl border border-slate-400 p-4"
    >
      <div className="flex justify-between gap-2">
        <h3 className="font-bold">مشاهدة الري للمهمة</h3>
        <button type="button" onClick={onClose}>
          إغلاق
        </button>
      </div>
      <p className="text-sm">
        سجّل ما حدث فعلاً أو ما شاهدته في الفحص الميداني. التسجيل لا يُنجز
        المهمة ولا يثبت وصول الماء ولا يرحّله إلى الدفتر.
      </p>
      {loading && <p role="status">جارٍ تحميل العمليات والمشاهدات…</p>}
      {loadError && <p role="alert">{loadError}</p>}
      {pending && (
        <p role="status">
          توجد محاولة محفوظة في هذه الجلسة تنتظر تأكيد النتيجة. البيانات مقفلة
          حتى تسويتها. معرّفها: {pending.observation_id}
        </p>
      )}
      <fieldset
        disabled={locked || loading || !!loadError}
        className="grid gap-3 sm:grid-cols-2"
      >
        <legend>بيانات المشاهدة</legend>
        <label>
          عملية الري المرتبطة
          <select
            value={form.execution_id}
            onChange={(e) => set("execution_id", e.target.value)}
            className="block w-full rounded border p-2 text-slate-900"
          >
            <option value="">اختر عملية محفوظة</option>
            {executions.map((op) => (
              <option key={op.execution_id} value={op.execution_id}>
                {op.system_id} · {op.state} · {op.execution_id}
              </option>
            ))}
          </select>
        </label>
        <label>
          مصدر التسجيل
          <select
            value={form.source}
            onChange={(e) => set("source", e.target.value)}
            className="block w-full rounded border p-2 text-slate-900"
          >
            <option value="farmer_task">إفادة المزارع عن المهمة</option>
            <option value="field_inspection">فحص ميداني</option>
          </select>
        </label>
        <label>
          نتيجة المشاهدة
          <select
            value={form.outcome}
            onChange={(e) => set("outcome", e.target.value)}
            className="block w-full rounded border p-2 text-slate-900"
          >
            {Object.entries(outcomeAr).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          وقت المشاهدة (توقيت جهازك)
          <input
            type="datetime-local"
            value={form.occurred_at}
            onChange={(e) => set("occurred_at", e.target.value)}
            className="block w-full rounded border p-2 text-slate-900"
          />
        </label>
        {form.outcome === "irrigated" && (
          <>
            <label>
              طريقة تحديد الكمية
              <select
                value={form.quantity_method}
                onChange={(e) => set("quantity_method", e.target.value)}
                className="block w-full rounded border p-2 text-slate-900"
              >
                {Object.entries(methodAr).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
            {form.quantity_method === "meter" && (
              <>
                {numberInput("meter_start_m3", "العداد قبل الري (م³)")}
                {numberInput("meter_end_m3", "العداد بعد الري (م³)")}
              </>
            )}
            {form.quantity_method === "estimated_flow" && (
              <>
                {numberInput("flow_m3_h", "التدفق التقديري (م³/ساعة)")}
                {numberInput(
                  "duration_minutes",
                  "مدة الري شاملة الانقطاع (دقيقة)",
                )}
                {numberInput("interruptions_minutes", "الانقطاع (دقيقة)")}
                <p>
                  التقدير ليس قياساً بعداد. للتحويل: لتر/دقيقة × 0.06 = م³/ساعة.
                </p>
              </>
            )}
            {form.quantity_method === "declared_volume" &&
              numberInput("volume_m3", "الحجم المصرح به (م³)")}
            {numberInput(
              "irrigated_area_ha",
              "المساحة المروية فعلاً (هكتار، اختياري)",
            )}
          </>
        )}
        <label>
          ملاحظات
          <textarea
            maxLength={2000}
            value={form.notes ?? ""}
            onChange={(e) => set("notes", e.target.value)}
            className="block w-full rounded border p-2 text-slate-900"
          />
        </label>
      </fieldset>
      {!loading && !executions.length && (
        <p>
          لا توجد عملية ري مرتبطة بالحقل. أنشئ العملية عبر مسار الري المعتمد
          أولاً.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {writable && (
        <button
          type="button"
          disabled={
            busy ||
            storageError ||
            (!pending && (loading || !!loadError || !executions.length))
          }
          onClick={submit}
          className="rounded border px-4 py-2 disabled:opacity-50"
        >
          {busy
            ? "جارٍ التسجيل…"
            : pending
              ? "إعادة إرسال المحاولة الأصلية"
              : "حفظ المشاهدة فقط"}
        </button>
      )}
      <h4 className="font-semibold">سجل المشاهدات</h4>
      {!loading && !loadError && history.length === 0 && (
        <p>لا توجد مشاهدات محفوظة لهذه المهمة.</p>
      )}
      <ol className="space-y-2">
        {history.map((row) => (
          <li key={row.observation_id} className="rounded border p-2">
            <p>
              {outcomeAr[row.outcome] ?? "غير معلوم"} ·{" "}
              {row.source === "field_inspection"
                ? "فحص ميداني"
                : "إفادة المزارع"}
            </p>
            <p>
              {new Date(row.occurred_at).toLocaleString("ar")} ·{" "}
              {methodAr[row.quantity_method] ?? "الكمية غير معلومة"}
            </p>
            <p>
              الكمية المسجلة:{" "}
              {row.computed?.volume_m3 == null
                ? "غير معلومة"
                : `${row.computed.volume_m3} م³`}{" "}
              · العمق:{" "}
              {row.computed?.depth_mm == null
                ? "غير معلوم"
                : `${row.computed.depth_mm} مم`}
            </p>
            <p>العملية: {row.execution_id}</p>
            {row.notes && <p>{row.notes}</p>}
          </li>
        ))}
      </ol>
    </section>
  );
}
