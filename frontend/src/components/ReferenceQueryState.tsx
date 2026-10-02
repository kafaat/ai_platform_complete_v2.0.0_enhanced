// ReferenceQueryState — يعرض لوحةً مرجعيّة بحسب queryView: البياناتُ الناجحة تبقى ظاهرة،
// وحالُ تحديثها ملاحظةٌ غير حاجبة؛ وبلا بيانات يُفرَّق الانقطاعُ عن التحميل عن الفشل.
import type { ReactNode } from "react";
import {
  OFFLINE_NO_DATA_TEXT,
  queryView,
  refreshNoteText,
  type QueryLike,
} from "../lib/queryView";

interface Props<T> {
  query: QueryLike<T>;
  loadingText: string;
  errorText: string;
  emptyText: string;
  children: (data: T) => ReactNode;
}

export default function ReferenceQueryState<T>({
  query,
  loadingText,
  errorText,
  emptyText,
  children,
}: Props<T>) {
  const view = queryView(query);
  switch (view.kind) {
    case "idle":
      return null;
    case "loading":
      return <div className="mt-2 text-slate-400">{loadingText}</div>;
    case "offline":
      return (
        <div role="status" className="mt-2 text-amber-300">
          {OFFLINE_NO_DATA_TEXT}
        </div>
      );
    case "error":
      return <div className="mt-2 text-red-400">{errorText}</div>;
    default: {
      const note = refreshNoteText(view.refresh);
      return (
        <>
          {note && (
            <div role="status" className="mt-2 text-xs text-amber-300">
              {note}
            </div>
          )}
          {view.kind === "empty" ? (
            <div className="mt-2 text-slate-400">{emptyText}</div>
          ) : (
            children(query.data as T)
          )}
        </>
      );
    }
  }
}
