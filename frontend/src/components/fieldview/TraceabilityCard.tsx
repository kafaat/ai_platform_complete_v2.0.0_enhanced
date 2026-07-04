import { useState } from 'react';
import { FileText, Copy, Download, Check } from 'lucide-react';
import { buildTraceabilityReport, traceabilityToMarkdown, type TraceabilityInput } from '../../lib/fieldTraceability';
import { T } from '../ds';

/** سجلّ الحقل القابل للمشاركة: يجمع الموسم + العمليّات + الماء + الوصفات ويصدّره Markdown. */
export default function TraceabilityCard(props: TraceabilityInput) {
  const report = buildTraceabilityReport(props);
  const [copied, setCopied] = useState(false);

  const md = traceabilityToMarkdown(report);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(md);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* الحافظة محظورة — نتجاهل بصمت */ }
  };

  const download = () => {
    try {
      const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${(props.fieldName || 'field').replace(/\s+/g, '_')}_traceability.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* بيئة بلا DOM — نتجاهل */ }
  };

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="traceability" aria-label="سجلّ الحقل">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <FileText className="w-4 h-4 text-emerald-300" aria-hidden="true" /> سجلّ الحقل (تتبّع)
        </span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={copy}
            disabled={!report.hasData}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
            style={{ border: `1px solid ${T.line}`, color: T.ink, background: 'rgba(15,23,42,.45)' }}
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-300" aria-hidden="true" /> : <Copy className="w-3.5 h-3.5" aria-hidden="true" />}
            {copied ? 'نُسِخ' : 'نسخ'}
          </button>
          <button
            type="button"
            onClick={download}
            disabled={!report.hasData}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
            style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}
          >
            <Download className="w-3.5 h-3.5" aria-hidden="true" /> تنزيل
          </button>
        </div>
      </div>

      {!report.hasData ? (
        <div className="text-[11px]" style={{ color: T.muted }}>لا سجلّ كافٍ بعد — أضِف موسماً وعمليّات لبناء تقرير قابل للمشاركة.</div>
      ) : (
        <div className="flex flex-col gap-2">
          {report.facts.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {report.facts.map((f) => (
                <span key={f.label} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                  <span style={{ color: T.faint }}>{f.label}:</span> {f.value}
                </span>
              ))}
            </div>
          )}
          {report.operations.length > 0 && (
            <div className="text-[11px] leading-5" style={{ color: T.muted }}>
              <span className="font-bold" style={{ color: T.ink }}>العمليّات:</span>{' '}
              {report.operations.slice(0, 5).map((o) => `${o.date} ${o.label}`).join(' · ')}
              {report.operations.length > 5 ? ` … (+${report.operations.length - 5})` : ''}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
