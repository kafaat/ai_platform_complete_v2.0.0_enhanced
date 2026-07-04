import { useMemo, useState } from 'react';
import { Wallet, TrendingUp, TrendingDown, AlertTriangle, Scale, Gauge } from 'lucide-react';
import {
  summarizeProfitability,
  rankCostBreakdown,
  topVariances,
  formatMoney,
  formatPercent,
  economicIntensities,
  budgetStatusLabel,
  type EconomicStateResponse,
  type LedgerSummaryResponse,
  type ProfitabilityResponse,
  type VarianceResponse,
} from '../../lib/fieldProfitability';
import { useBreakEven } from '../../hooks/useApi';
import { T } from '../ds';

interface Props {
  hasSeason: boolean;
  profitability?: ProfitabilityResponse | null;
  summary?: LedgerSummaryResponse | null;
  variance?: VarianceResponse | null;
  /** الحالة الاقتصاديّة العميقة (كثافات وحدة + حالة موازنة + توصيات كفاءة). */
  economicState?: EconomicStateResponse | null;
  /** مساحة الحقل (هـ) — لأداة سعر التعادل مع تكلفة السجلّ الفعليّة. */
  areaHa?: number | null;
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
export default function SeasonProfitabilityCard({ hasSeason, profitability, summary, variance, economicState, areaHa, loading }: Props) {
  const view = summarizeProfitability(profitability);
  const slices = rankCostBreakdown(summary?.summary?.cost_breakdown);
  const vars = topVariances(variance?.variance);
  const topRec = variance?.recommendations?.[0] ?? null;
  const ledgerCost = summary?.summary?.total_cost ?? null;
  const opCount = summary?.summary?.operation_count ?? 0;
  const disabled = !!profitability?.disabled || !!summary?.disabled;

  // الحالة الاقتصاديّة العميقة: كثافات وحدة حقيقيّة + حالة موازنة + أوّل توصية كفاءة.
  const eco = economicState?.economic_state ?? null;
  const intensities = economicIntensities(eco, view.currency);
  const effRec = eco?.recommendations?.[0] ?? null;

  // سعر التعادل: تكلفة السجلّ الفعليّة + مساحة الحقل + غلّة متوقَّعة يُدخِلها المستخدم فقط.
  const [yieldInput, setYieldInput] = useState('');
  const yieldTPerHa = useMemo(() => {
    const v = Number(yieldInput);
    return yieldInput.trim() !== '' && Number.isFinite(v) && v > 0 ? v : null;
  }, [yieldInput]);
  const breakEvenQ = useBreakEven(areaHa ?? null, yieldTPerHa, ledgerCost);

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

          {/* الحالة الاقتصاديّة العميقة — كثافات وحدة حقيقيّة من economic-state */}
          {(intensities.length > 0 || eco) && (
            <div className="flex flex-wrap items-center gap-1.5" data-testid="economic-intensities">
              <Gauge className="w-3.5 h-3.5 text-sky-300" aria-hidden="true" />
              {intensities.map((i) => (
                <span key={i.label} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                  <span style={{ color: T.faint }}>{i.label}:</span> {i.value}
                </span>
              ))}
              {eco && (
                <span
                  className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                  style={{
                    border: `1px solid ${eco.budget_variance_status === 'critical' ? '#7c2d12' : T.line}`,
                    color: eco.budget_variance_status === 'critical' ? '#fca5a5' : eco.budget_variance_status === 'watch' ? '#fdba74' : T.muted,
                  }}
                >
                  الموازنة: {budgetStatusLabel(eco.budget_variance_status)}
                </span>
              )}
            </div>
          )}
          {effRec && (
            <div className="text-[11px]" style={{ color: T.muted }}>
              <span className="font-bold" style={{ color: T.ink }}>{effRec.title_ar}:</span> {effRec.message_ar}
            </div>
          )}

          {/* سعر التعادل — تكلفة السجلّ الفعليّة + غلّة متوقَّعة من المستخدم (إرشاديّ) */}
          {ledgerCost != null && ledgerCost > 0 && areaHa != null && areaHa > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }} data-testid="break-even-tool">
              <Scale className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-hidden="true" />
              <label htmlFor="be-yield" className="font-bold" style={{ color: T.ink }}>غلّة متوقَّعة (طن/هـ):</label>
              <input
                id="be-yield"
                type="number"
                min="0"
                step="0.1"
                value={yieldInput}
                onChange={(e) => setYieldInput(e.target.value)}
                placeholder="تقديرك"
                className="w-20 px-2 py-0.5 rounded-lg text-[11px]"
                style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }}
              />
              {breakEvenQ.data?.supported && breakEvenQ.data.break_even_price_per_t != null && (
                <span style={{ color: T.ink }}>
                  سعر التعادل ~<span className="font-bold">{formatMoney(breakEvenQ.data.break_even_price_per_t, view.currency)}</span>/طن
                  {breakEvenQ.data.total_yield_t != null ? ` (إنتاج ${breakEvenQ.data.total_yield_t} طن)` : ''}
                </span>
              )}
              {breakEvenQ.data && !breakEvenQ.data.supported && (
                <span style={{ color: T.faint }}>{breakEvenQ.data.message_ar ?? '—'}</span>
              )}
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
