// queryView — ما تعرضه لوحةٌ مرجعيّة، مشتقّاً من محورَي React Query معاً لا من أحدهما.
//
// FRONTEND-REFERENCE-PANELS-HIDE-OR-FAKE-STATE-ON-PAUSE-AND-REFETCH-ERROR-01: في TanStack v5
// ``status`` (pending/error/success) و``fetchStatus`` (fetching/paused/idle) متعامدان، و
// ``isLoading`` = pending **و**fetching. فسلسلةُ ``isLoading ? … : isError ? … : !data ? «لا
// بيانات»`` تكذب مرّتين:
//   • بلا اتّصالٍ قبل أوّل جلب: pending + paused ⇒ ليست «تحميلاً» ولا «خطأً» ⇒ تُقال «لا بيانات»
//     وهي انقطاع.
//   • فشلُ تحديثٍ خلفيّ: status=error مع بقاء بياناتٍ ناجحة ⇒ فرعُ الخطأ أوّلاً يُخفيها.
//
// القاعدة: وجودُ بياناتٍ ناجحة يُعرض دائماً، وحالُ التحديث ملاحظةٌ غير حاجبة بجانبه. وبلا
// بيانات يُفرَّق الانقطاعُ عن التحميل عن الفشل عن «لم يُطلب». والقائمةُ الفارغة الصحيحة
// «فراغ» لا خطأ. هذا للمراجع العامّة؛ بياناتُ المستأجر عند تبدّل الهويّة شأنٌ آخر.

export type RefreshNote = "none" | "refreshing" | "paused" | "failed";

export type QueryView =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "offline" }
  | { kind: "error" }
  | { kind: "empty"; refresh: RefreshNote }
  | { kind: "data"; refresh: RefreshNote };

export interface QueryLike<T> {
  data: T | undefined;
  status: "pending" | "error" | "success";
  fetchStatus: "fetching" | "paused" | "idle";
}

function refreshNote(q: QueryLike<unknown>): RefreshNote {
  if (q.status === "error") return "failed";
  if (q.fetchStatus === "paused") return "paused";
  if (q.fetchStatus === "fetching") return "refreshing";
  return "none";
}

export function queryView<T>(q: QueryLike<T>): QueryView {
  if (q.data !== undefined) {
    const empty = Array.isArray(q.data) && q.data.length === 0;
    return { kind: empty ? "empty" : "data", refresh: refreshNote(q) };
  }
  if (q.fetchStatus === "paused") return { kind: "offline" };
  if (q.status === "error") return { kind: "error" };
  if (q.fetchStatus === "fetching") return { kind: "loading" };
  return { kind: "idle" };
}

/** نصُّ ملاحظة التحديث غيرِ الحاجبة — ``null`` حين لا شيء يُقال. */
export function refreshNoteText(note: RefreshNote): string | null {
  switch (note) {
    case "paused":
      return "التحديث متوقّف: لا اتّصال. تُعرض آخر بياناتٍ حُمّلت.";
    case "failed":
      return "تعذّر تحديث البيانات. تُعرض آخر نسخةٍ ناجحة.";
    case "refreshing":
      return "جارٍ التحديث…";
    default:
      return null;
  }
}

/** نصُّ الانقطاع قبل أوّل بيانات — ليس «لا بيانات» ولا «تحميلاً» دائماً. */
export const OFFLINE_NO_DATA_TEXT =
  "لا اتّصال، ولم تُحمَّل هذه البيانات بعد. ستُجلب عند عودة الاتّصال.";
