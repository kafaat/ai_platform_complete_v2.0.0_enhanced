import { Wallet, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react';
import {
  summarizeProfitability,
  rankCostBreakdown,
  topVariances,
  formatMoney,
  formatPercent,
  type LedgerSummaryResponse,
  type ProfitabilityResponse,
  type VarianceResponse,
} from '../../lib/fieldProfitability';
import { T } from '../ds';

interface Props {
  hasSeason: boolean;
  profitability?: ProfitabilityResponse | null;
  summary?: LedgerSummaryResponse | null;
  variance?: VarianceResponse | null;
  loading?: boolean;
}

const CATEGORY_LABEL: Record<string, string> = {
  labor: 'عمالة',
  water: 'ريّ',
  energy: 'طاقة',
  fertilizer: 'تسميد',
  seed: 'بذار',
  pesticide: 'مكافحة',
  equipment: 'معدّات',
  fuel: 'وقود',
  overhead: 'غير مباشرة',
  administration: 'إدارة',
  uncategorized: 'غير مصنَّف',
};
const catLabel = (c: string) => CATEGORY_LABEL[c] ?? c;

/** ربحيّة الموسم: تعكس التكاليف/الإيرادات الفعليّة المُخزَّنة في سجلّ العمليّات (v100–v102).
 *  صدق: أرقام حقيقيّة فقط · «—» للمجهول · حالة صريحة عند تعطّل الميزة أو غياب السجلّ. */
export default function SeasonProfitabilityCard({ hasSeason, profitability, summary, variance, loading }: Props) {
  const view = summarizeProfitability(profitability);
  const slices = rankCostBreakdown(summary?.summary?.cost_breakdown);
  const vars = topVariances(variance?.variance);
  const topRec = variance?.recommendations?.[0] ?? null;
  const ledgerCost = summary?.summary?.total_cost ?? null;
  const opCount = summary?.summary?.operation_count ?? 0;
  const disabled = !!profitability?.disabled || !!summary?.disabled;

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="season-profitability" aria-label="ربحيّة الموسم">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Wallet className="w-4 h-4 text-emerald-300" aria-hidden="true" /> ربحيّة الموسم (سجلّ فعليّ)
        </span>
        {view.available && view.profitable != null && (
          <span className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: view.profitable ? '#86efac' : '#fca5a5' }}>
            {view.profitable ? <TrendingUp className="w-3.5 h-3.5" aria-hidden="true" /> : <TrendingDown className="w-3.5 h-3.5" aria-hidden="true" />}
            {view.profitable ? 'رابح' : 'خاسر'}
          </span>
        )}
      </div>

      {!hasSeason ? (
        <div className="text-[11px]" style={{ color: T.muted }}>لا موسم نشط لعرض ربحيّته — أضِف موسماً لبدء تتبّع التكلفة.</div>
      ) : loading ? (
        <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة سجلّ التكاليف…</div>
      ) : disabled ? (
        <div className="text-[11px]" style={{ color: T.muted }}>سجلّ التكاليف (farm-ledger) غير مفعّل في هذه البيئة — فعِّل <span className="font-mono">FEATURE_FARM_OPERATIONS_LEDGER</span> لعرض الربحيّة الفعليّة.</div>
      ) : (
        <div className="flex flex-col gap-2">
          {/* الأرقام الأساسيّة — إيراد/تكلفة/هامش (حقيقيّة أو «—») */}
          <div className="grid grid-cols-3 gap-2">
            <Metric label="الإيراد" value={formatMoney(view.revenue, view.currency)} />
            <Metric label="التكلفة" value={formatMoney(view.totalCost ?? ledgerCost, view.currency)} />
            <Metric
              label="صافي الهامش"
              value={formatMoney(view.grossMargin, view.currency)}
              tone={view.grossMargin == null ? undefined : view.grossMargin > 0 ? '#86efac' : view.grossMargin < 0 ? '#fca5a5' : undefined}
              sub={formatPercent(view.marginPercent)}
            />
          </div>

          {!view.available && (
            <div className="text-[11px]" style={{ color: T.muted }}>
              {view.reason}
              {opCount > 0 ? ` (سُجِّلت ${opCount} عمليّة بتكلفة ${formatMoney(ledgerCost, view.currency)} — أضِف إيراداً لحساب الربحيّة).` : ''}
            </div>
          )}

          {/* تفصيل التكلفة الأكبر — من السجلّ الفعليّ */}
          {slices.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {slices.slice(0, 5).map((s) => (
                <span key={s.category} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                  <span style={{ color: T.faint }}>{catLabel(s.category)}:</span> {formatMoney(s.amount, view.currency)}
                </span>
              ))}
            </div>
          )}

          {/* أعلى انحراف مخطَّط/فعليّ + توصية الضبط */}
          {vars.length > 0 && (
            <div className="text-[11px] leading-5" style={{ color: T.muted }}>
              <span className="font-bold" style={{ color: T.ink }}>أبرز انحراف:</span>{' '}
              {catLabel(vars[0].category)} {vars[0].variance_amount > 0 ? '+' : ''}{formatMoney(vars[0].variance_amount, view.currency)}
              {vars[0].variance_percent != null ? ` (${formatPercent(vars[0].variance_percent)})` : ''}
            </div>
          )}
          {topRec && (
            <div className="flex items-start gap-1.5 text-[11px] rounded-xl px-2 py-1.5" style={{ border: `1px solid ${T.line}`, color: T.muted, background: 'rgba(15,23,42,.35)' }}>
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-amber-300" aria-hidden="true" />
              <span><span className="font-bold" style={{ color: T.ink }}>{topRec.title_ar}:</span> {topRec.message_ar}</span>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function Metric({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
      <div className="text-[10px]" style={{ color: T.faint }}>{label}</div>
      <div className="text-sm font-bold" style={{ color: tone ?? T.ink }}>{value}</div>
      {sub && <div className="text-[10px]" style={{ color: T.faint }}>{sub}</div>}
    </div>
  );
}
