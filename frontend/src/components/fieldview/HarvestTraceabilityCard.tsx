import { useState } from 'react';
import { PackageCheck, Link2, ClipboardList } from 'lucide-react';
import { useHarvestLots, useLotTraceability, useFieldInputTraceability } from '../../hooks/useApi';
import {
  chainStatusLabel,
  inputLedgerFacts,
  summarizeLots,
  EVENT_TYPE_AR,
} from '../../lib/fieldHarvestTraceability';
import { T } from '../ds';

interface Props {
  fieldId?: string | null;
  seasonId?: string | null;
  enabled?: boolean;
}

/** تتبّع الحصاد والمدخلات: دفعات الحقل + سلسلة الحيازة (append-only، معيار اكتمال
 *  الخادم: حصاد ⇒ سوق) + دفتر مدخلات الإنتاج بتغطية كلفة مُعلَنة. صدق: «—» للمجهول،
 *  والكمّيّات المجموعة معروفة فقط. */
export default function HarvestTraceabilityCard({ fieldId, seasonId, enabled = true }: Props) {
  const lotsQ = useHarvestLots(fieldId, enabled);
  const ledgerQ = useFieldInputTraceability(fieldId, seasonId ?? null, enabled);
  const [lotId, setLotId] = useState<string | null>(null);
  const traceQ = useLotTraceability(lotId);

  if (!enabled || !fieldId) return null;

  const lots = lotsQ.data ?? [];
  const overview = summarizeLots(lots);
  const ledgerFacts = inputLedgerFacts(ledgerQ.data);
  const chain = traceQ.data?.chain ?? null;
  const lastEvents = traceQ.data?.custody_chain?.slice(-3) ?? [];

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="harvest-traceability" aria-label="تتبّع الحصاد">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <PackageCheck className="w-4 h-4 text-emerald-300" aria-hidden="true" /> تتبّع الحصاد (مزرعة ⇒ سوق)
        </span>
        {overview.count > 0 && (
          <span className="text-[11px]" style={{ color: T.muted }}>
            {overview.count} دفعة{overview.knownQuantityKg != null ? ` · ~${Math.round(overview.knownQuantityKg).toLocaleString('en-US')} كغ` : ''}
          </span>
        )}
      </div>

      {lotsQ.isLoading ? (
        <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة دفعات الحصاد…</div>
      ) : lots.length === 0 ? (
        <div className="text-[11px]" style={{ color: T.muted }}>لا دفعات حصاد مُسجَّلة لهذا الحقل بعد — سجِّل دفعة عند الحصاد لبدء سلسلة التتبّع.</div>
      ) : (
        <div className="flex flex-col gap-2">
          {/* دفعات الحقل */}
          <div className="flex flex-wrap gap-1.5">
            {lots.slice(0, 6).map((l) => (
              <button
                key={l.harvest_lot_id}
                type="button"
                onClick={() => setLotId(lotId === l.harvest_lot_id ? null : l.harvest_lot_id)}
                className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                style={{
                  border: `1px solid ${lotId === l.harvest_lot_id ? '#14532d' : T.line}`,
                  color: lotId === l.harvest_lot_id ? '#86efac' : T.muted,
                  background: lotId === l.harvest_lot_id ? 'rgba(20,83,45,.25)' : 'rgba(15,23,42,.45)',
                }}
              >
                {l.harvest_date ?? '—'} · {l.crop ?? '—'}
                {l.quantity_kg != null ? ` · ${Math.round(l.quantity_kg)} كغ` : ''}
              </button>
            ))}
            {lots.length > 6 && <span className="text-[10px]" style={{ color: T.faint }}>+{lots.length - 6}</span>}
          </div>

          {/* سلسلة الحيازة للدفعة المختارة */}
          {lotId && traceQ.data && (
            <div className="flex flex-col gap-1 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
              <div className="flex items-center gap-1.5 text-[11px]" style={{ color: chain?.complete ? '#86efac' : '#fdba74' }}>
                <Link2 className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                <span className="font-bold">{chainStatusLabel(chain)}</span>
                {chain && <span style={{ color: T.faint }}>· {chain.event_count} حدثاً</span>}
              </div>
              {lastEvents.length > 0 && (
                <div className="text-[11px] leading-5" style={{ color: T.muted }}>
                  {lastEvents.map((e) => `${(e.occurred_at ?? '').slice(0, 10)} ${EVENT_TYPE_AR[e.event_type] ?? e.event_type}${e.location_name ? ` (${e.location_name})` : ''}`).join(' ← ')}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* دفتر مدخلات الإنتاج (بذرة ⇒ حصاد) */}
      {ledgerFacts.length > 0 && (
        <div className="mt-2 flex flex-col gap-1">
          <span className="inline-flex items-center gap-1.5 text-[11px] font-bold" style={{ color: T.ink }}>
            <ClipboardList className="w-3.5 h-3.5 text-sky-300" aria-hidden="true" /> دفتر المدخلات
          </span>
          <div className="flex flex-wrap gap-1.5">
            {ledgerFacts.map((f) => (
              <span key={f.label} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                <span style={{ color: T.faint }}>{f.label}:</span> {f.value}
              </span>
            ))}
          </div>
        </div>
      )}
      {ledgerQ.data?.state === 'no_inputs' && (
        <div className="mt-2 text-[10px]" style={{ color: T.faint }}>{ledgerQ.data.reason_ar ?? 'لا مدخلات مسجّلة بعد.'}</div>
      )}
    </section>
  );
}
