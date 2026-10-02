// مصفوفةُ العرض على محورَي React Query — كلُّ صفٍّ حالةٌ تبلغها المكتبةُ فعلاً.
import { describe, it, expect } from "vitest";
import { queryView, refreshNoteText, type QueryLike } from "./queryView";

const q = (
  data: unknown,
  status: QueryLike<unknown>["status"],
  fetchStatus: QueryLike<unknown>["fetchStatus"],
): QueryLike<unknown> => ({ data, status, fetchStatus });

describe("queryView", () => {
  it.each([
    [
      "لا بيانات + pending/paused ⇒ انقطاع لا تحميل",
      q(undefined, "pending", "paused"),
      { kind: "offline" },
    ],
    [
      "لا بيانات + pending/fetching ⇒ تحميل",
      q(undefined, "pending", "fetching"),
      { kind: "loading" },
    ],
    [
      "لا بيانات + pending/idle (معطَّل) ⇒ لا شيء",
      q(undefined, "pending", "idle"),
      { kind: "idle" },
    ],
    [
      "لا بيانات + error/idle ⇒ خطأ",
      q(undefined, "error", "idle"),
      { kind: "error" },
    ],
    [
      "لا بيانات + error/paused (إعادة محاولة بلا اتّصال) ⇒ انقطاع",
      q(undefined, "error", "paused"),
      { kind: "offline" },
    ],
    [
      "بيانات + success/idle ⇒ بيانات",
      q([1], "success", "idle"),
      { kind: "data", refresh: "none" },
    ],
    [
      "بيانات + success/paused ⇒ بيانات + توقّف",
      q([1], "success", "paused"),
      { kind: "data", refresh: "paused" },
    ],
    [
      "بيانات + success/fetching ⇒ بيانات + تحديث",
      q([1], "success", "fetching"),
      { kind: "data", refresh: "refreshing" },
    ],
    [
      "بيانات + error/idle (فشلُ إعادة جلب) ⇒ بيانات + فشل",
      q([1], "error", "idle"),
      { kind: "data", refresh: "failed" },
    ],
    [
      "[] صحيحة ⇒ فراغ لا خطأ",
      q([], "success", "idle"),
      { kind: "empty", refresh: "none" },
    ],
    [
      "كائنٌ غيرُ مصفوفة ⇒ بيانات",
      q({ date_iso: "x" }, "success", "idle"),
      { kind: "data", refresh: "none" },
    ],
  ])("%s", (_label, query, expected) => {
    expect(queryView(query)).toEqual(expected);
  });

  it("ملاحظةُ التحديث تُقال لكلّ حالٍ غيرِ عاديّ، ولا تُقال للعاديّ", () => {
    expect(refreshNoteText("none")).toBeNull();
    expect(refreshNoteText("paused")).toMatch(/لا اتّصال/);
    expect(refreshNoteText("failed")).toMatch(/آخر نسخةٍ ناجحة/);
    expect(refreshNoteText("refreshing")).toMatch(/جارٍ التحديث/);
  });
});
