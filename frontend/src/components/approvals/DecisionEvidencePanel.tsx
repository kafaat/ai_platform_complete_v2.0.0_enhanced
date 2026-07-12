import { FileSearch, Leaf, History, ListChecks, Satellite } from 'lucide-react';
import { useDecisionAgronomicEvidence } from '../../hooks/useApi';
import {
  entryWithinCutoff, qualityColor, shortHash,
} from '../../lib/approvalsConsole';
import { T } from '../ds';

/** Phase E — لوحة الدليل الزراعيّ الكامل خلف قرار واحد (قراءة آمِرة من decision-service).
 *  صدق العرض: mirror/SoR-off يظهر كخطأ صريح لا كقائمة فارغة؛ قرارات legacy_unbound تُعلَن
 *  كذلك حرفيّاً؛ عدم تطابق hash الـmanifest المُثبَّت على القرار يُعرَض تحذيراً أحمر. */
export default function DecisionEvidencePanel({ decisionId }: { decisionId: string }) {
  const evidenceQ = useDecisionAgronomicEvidence(decisionId);

  if (evidenceQ.isLoading) {
    return <div className="text-[11px] mt-2" style={{ color: T.faint }}>جارٍ قراءة الدليل الآمر…</div>;
  }
  if (evidenceQ.isError || !evidenceQ.data) {
    return (
      <div className="text-[11px] mt-2" role="alert" style={{ color: '#fdba74' }}>
        الدليل غير متاح — في وضع mirror يفشل المسار مغلقاً بدل عرض «لا يوجد دليل» زائف.
      </div>
    );
  }

  const ev = evidenceQ.data;
  const ctx = ev.context_snapshot;
  const hist = ev.historical_snapshot;
  const manifest = ev.feature_manifest;
  const veg = ev.vegetation_snapshot;
  const legacy = (ev.decision.context_contract_version ?? 'legacy_unbound') === 'legacy_unbound';
  const domains = ctx ? Object.keys(ctx.context) : [];

  return (
    <div
      className="mt-2 rounded-xl border p-2 text-[11px] flex flex-col gap-2"
      data-testid="decision-evidence-panel"
      style={{ borderColor: T.line, background: 'rgba(2,6,23,.45)' }}
    >
      <div className="inline-flex items-center gap-2 font-bold" style={{ color: T.ink }}>
        <FileSearch className="w-3.5 h-3.5 text-sky-300" aria-hidden="true" /> الدليل الزراعيّ للقرار
        <span
          className="px-2 py-0.5 rounded-full text-[10px] font-semibold"
          style={{
            border: `1px solid ${T.line}`,
            color: ev.evidence_complete ? '#86efac' : legacy ? '#94a3b8' : '#fdba74',
          }}
        >
          {ev.evidence_complete ? 'سلسلة كاملة' : legacy ? 'قرار قديم غير مربوط (legacy_unbound)' : 'سلسلة ناقصة'}
        </span>
      </div>

      {legacy ? (
        <div style={{ color: T.muted }}>
          هذا القرار سُجِّل قبل إلزام السياق الزراعيّ — لا توجد لقطات مرتبطة، وهذا يُعرَض كما هو بلا تجميل.
        </div>
      ) : (
        <>
          {ctx && (
            <section>
              <div className="inline-flex items-center gap-1 font-semibold" style={{ color: T.ink }}>
                <Leaf className="w-3 h-3 text-emerald-300" aria-hidden="true" /> لقطة السياق المركَّبة
                <span style={{ color: T.faint }}>· {new Date(ctx.as_of_time).toLocaleString('ar')}</span>
              </div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {domains.map((domain) => (
                  <span key={domain} className="px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.muted }}>
                    {domain}
                  </span>
                ))}
              </div>
              <div className="mt-1 break-all" style={{ color: T.faint }}>
                hash: {shortHash(ctx.content_hash)} · composer {ctx.composer_version} · عقد {ctx.schema_version}
              </div>
            </section>
          )}

          {hist && (
            <section>
              <div className="inline-flex items-center gap-1 font-semibold" style={{ color: T.ink }}>
                <History className="w-3 h-3 text-amber-300" aria-hidden="true" /> النافذة التاريخيّة
              </div>
              <div style={{ color: T.muted }}>
                من {new Date(hist.history_from).toLocaleDateString('ar')} إلى {new Date(hist.history_to).toLocaleDateString('ar')}
                <span style={{ color: T.faint }}> · مفاتيح: {Object.keys(hist.history).slice(0, 6).join('، ') || '—'}</span>
              </div>
            </section>
          )}

          {manifest && (
            <section>
              <div className="inline-flex items-center gap-1 font-semibold" style={{ color: T.ink }}>
                <ListChecks className="w-3 h-3 text-violet-300" aria-hidden="true" /> بيان الميزات المُستخدَمة فعلاً
                <span style={{ color: T.faint }}>· القطع الزمنيّ {new Date(manifest.decision_cutoff_time).toLocaleString('ar')}</span>
              </div>
              {!manifest.hash_matches_decision && (
                <div role="alert" className="mt-1 font-semibold" style={{ color: '#fca5a5' }}>
                  تحذير نزاهة: بصمة البيان المثبَّتة على القرار لا تطابق البيان المخزَّن.
                </div>
              )}
              <div className="mt-1 overflow-x-auto">
                <table className="w-full text-[10px]" style={{ color: T.muted }}>
                  <thead>
                    <tr style={{ color: T.faint }}>
                      <th className="text-right pe-2">الميزة</th>
                      <th className="text-right pe-2">القيمة</th>
                      <th className="text-right pe-2">المصدر</th>
                      <th className="text-right pe-2">رُصدت</th>
                      <th className="text-right pe-2">أُتيحت</th>
                      <th className="text-right pe-2">الجودة</th>
                      <th className="text-right">ضمن القطع؟</th>
                    </tr>
                  </thead>
                  <tbody>
                    {manifest.entries.map((entry) => {
                      const withinCutoff = entryWithinCutoff(entry, manifest.decision_cutoff_time);
                      return (
                        <tr key={entry.name}>
                          <td className="pe-2 font-semibold" style={{ color: T.ink }}>{entry.name}</td>
                          <td className="pe-2">{String(entry.value)}{entry.unit ? ` ${entry.unit}` : ''}</td>
                          <td className="pe-2">{entry.source_service}</td>
                          <td className="pe-2">{new Date(entry.observed_at).toLocaleString('ar')}</td>
                          <td className="pe-2">{new Date(entry.available_at).toLocaleString('ar')}</td>
                          <td className="pe-2" style={{ color: qualityColor(entry.quality_status) }}>{entry.quality_status}</td>
                          <td style={{ color: withinCutoff ? '#86efac' : '#fca5a5' }}>{withinCutoff ? 'نعم' : 'تسريب!'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {veg && (
            <section>
              <div className="inline-flex items-center gap-1 font-semibold" style={{ color: T.ink }}>
                <Satellite className="w-3 h-3 text-sky-300" aria-hidden="true" /> لقطة الدليل النباتيّ
              </div>
              <div style={{ color: T.muted }}>
                التقاط {new Date(veg.acquisition_at).toLocaleString('ar')} · إتاحة {new Date(veg.data_available_at).toLocaleString('ar')}
                <span className="break-all" style={{ color: T.faint }}> · hash: {shortHash(veg.snapshot_hash)}</span>
              </div>
            </section>
          )}
        </>
      )}

      <div className="text-[10px]" style={{ color: T.faint }}>
        كلّ اللقطات append-only ومحتواها مُعنوَن بالبصمة؛ هذه الشاشة تعرض ولا تُعدِّل.
      </div>
    </div>
  );
}
