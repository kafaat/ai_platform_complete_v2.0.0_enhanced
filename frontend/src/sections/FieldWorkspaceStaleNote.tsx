// وسم صريح لبيانات مخبّأة لم تُحدَّث (UI-W6) — يُعرَض فوق آخر نتيجة ناجحة بعد فشل إعادة الجلب.
export default function FieldWorkspaceStaleNote({ updatedAt }: { updatedAt: number }) {
  const when = updatedAt ? new Date(updatedAt).toLocaleString('ar') : '—';
  return (
    <p role="status" className="mb-2 rounded-lg border border-amber-700/60 bg-amber-950/40 px-3 py-2 text-xs text-amber-200">
      بيانات قديمة غير محدَّثة — آخر جلب ناجح: {when}. لا تعتمد عليها قبل نجاح إعادة المحاولة.
    </p>
  );
}
