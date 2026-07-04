// FieldView Traceability — مستوحى من Farmonaut (traceability من المزرعة إلى السوق):
// يجمع سجلّ الحقل/الموسم في تقرير قابل للمشاركة/التصدير — الهويّة + الموسم + العمليّات
// المنفَّذة + الماء المُطبَّق + الوصفات. صدق: يُبنى من بيانات حقيقيّة فقط (حقل · موسم ·
// مهامّ مكتملة · دفتر مياه · وصفات)؛ لا يُدرَج حقل لا قيمة له، ولا أرقام مُختلَقة.
export interface TraceabilityOperation {
  label: string;
  date: string; // ISO أو '—'
}

export interface TraceabilitySeasonLite {
  crops?: string[];
  cultivar?: string | null;
  sowing_date?: string | null;
  plowing_date?: string | null;
  land_leveling_date?: string | null;
  irrigation_type?: string | null;
  status?: string | null;
  season_end?: string | null;
}

export interface TraceabilityInput {
  fieldName?: string | null;
  crop?: string | null;
  areaHa?: number | null;
  season?: TraceabilitySeasonLite | null;
  completedOps?: TraceabilityOperation[];
  /** إجماليّ الريّ المُطبَّق (mm) من الدفتر. */
  irrigationMm?: number | null;
  prescriptionCount?: number | null;
}

export interface TraceabilityFact {
  label: string;
  value: string;
}

export interface TraceabilityReport {
  title: string;
  facts: TraceabilityFact[];
  operations: TraceabilityOperation[];
  hasData: boolean;
}

function fdate(s: string | null | undefined): string {
  const d = String(s ?? '').slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(d) ? d : '—';
}

export function buildTraceabilityReport(input: TraceabilityInput): TraceabilityReport {
  const fieldName = input.fieldName || 'الحقل';
  const facts: TraceabilityFact[] = [];
  const push = (label: string, value: string | null | undefined) => {
    if (value != null && value !== '' && value !== '—') facts.push({ label, value });
  };

  push('المحصول', input.crop ?? input.season?.crops?.[0] ?? null);
  push('المساحة', input.areaHa != null && input.areaHa > 0 ? `${input.areaHa.toFixed(1)} هـ` : null);
  push('الصنف', input.season?.cultivar ?? null);
  push('نوع الريّ', input.season?.irrigation_type ?? null);
  push('حالة الموسم', input.season?.status ?? null);
  if (input.season?.land_leveling_date) push('تسوية الأرض', fdate(input.season.land_leveling_date));
  if (input.season?.plowing_date) push('الحراثة', fdate(input.season.plowing_date));
  if (input.season?.sowing_date) push('البذار', fdate(input.season.sowing_date));
  if (input.season?.season_end) push('نهاية الموسم', fdate(input.season.season_end));
  if (typeof input.irrigationMm === 'number' && input.irrigationMm > 0) {
    push('الماء المُطبَّق', `${Math.round(input.irrigationMm)} مم`);
  }
  if (typeof input.prescriptionCount === 'number' && input.prescriptionCount > 0) {
    push('وصفات التطبيق المتغيّر', String(input.prescriptionCount));
  }

  const operations = (input.completedOps ?? []).map((o) => ({ label: o.label, date: fdate(o.date) }));
  const hasData = facts.length > 0 || operations.length > 0;

  return { title: `سجلّ ${fieldName}`, facts, operations, hasData };
}

/** يُصدِّر التقرير كـMarkdown قابل للمشاركة (نصّ حقيقيّ من بيانات الحقل). */
export function traceabilityToMarkdown(r: TraceabilityReport): string {
  const lines: string[] = [`# ${r.title}`, ''];
  if (r.facts.length) {
    lines.push('## المعطيات');
    for (const f of r.facts) lines.push(`- **${f.label}:** ${f.value}`);
    lines.push('');
  }
  if (r.operations.length) {
    lines.push('## العمليّات المنفَّذة');
    for (const o of r.operations) lines.push(`- ${o.date} — ${o.label}`);
    lines.push('');
  }
  if (!r.hasData) lines.push('_لا سجلّ كافٍ بعد لهذا الحقل._');
  return lines.join('\n');
}
