/** Presentation only. Missing/invalid observations never become measurements. */
export function measuredNdvi(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= -1 && value <= 1
    ? value : null;
}

export function summarizeNdvi(fields: readonly { ndvi?: unknown }[]) {
  const values = fields.map(f => measuredNdvi(f.ndvi)).filter((v): v is number => v !== null);
  return { count: values.length, mean: values.length ? values.reduce((a, b) => a + b, 0) / values.length : null };
}

export function dataFailureMessage(error: unknown): string {
  const status = (error as { response?: { status?: number } } | undefined)?.response?.status;
  if (status === 401) return 'تعذّر التحقق من صلاحية الوصول إلى هذه البيانات. أعد تسجيل الدخول إذا استمر الرفض.';
  if (status === 403) return 'لا يملك حسابك صلاحية عرض هذه البيانات.';
  return 'البيانات غير متاحة الآن. أعد المحاولة؛ لم نعتبر فشل الاتصال غيابًا للحقول أو التنبيهات.';
}
