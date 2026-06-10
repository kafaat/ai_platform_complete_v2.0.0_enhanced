// ════════════════════════════════════════════════════════════
// SAHOOL — المايسترو (Field Intelligence) — ربط حيّ بـ
// POST /api/v1/field-intelligence/analyze. يُبرِز التحليل الموحّد لحقل:
// الحقائق التشغيليّة + الثقة + قرار السياسة + التناقضات + الإشارات الناقصة +
// التنبيهات الاستباقيّة + أثر المحاكاة. صدق: المصادر المتعذّرة تُعلَن (لا اختراع).
// ════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Activity, Search, ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react';
import { useFieldIntelligence } from '../hooks/useApi';
import { ErrorState } from '../components/StateViews';

function asText(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

// مستوى الثقة نصّيّ من المحرّك (high|medium|low|none) — يُترجَم للعرض.
const CONF_AR: Record<string, string> = {
  high: 'عالية', medium: 'متوسطة', low: 'منخفضة', none: 'غير متوفّرة',
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border p-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
      <div className="text-sm font-semibold text-slate-200 mb-2">{title}</div>
      {children}
    </div>
  );
}

function KV({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) return <p className="text-xs text-slate-500">—</p>;
  return (
    <div className="space-y-1">
      {entries.map(([k, v]) => (
        <div key={k} className="flex items-start justify-between gap-3 text-xs py-1 border-b last:border-0" style={{ borderColor: '#334155' }}>
          <span className="text-slate-500 flex-shrink-0">{k}</span>
          <span className="text-slate-300 text-left break-all">{asText(v) || '—'}</span>
        </div>
      ))}
    </div>
  );
}

export default function FieldIntelligencePage() {
  const [fieldId, setFieldId] = useState('');
  const [lat, setLat] = useState('');
  const [lon, setLon] = useState('');
  const [crop, setCrop] = useState('');
  const [showProv, setShowProv] = useState(false);
  const mut = useFieldIntelligence();

  // رقم محدود صالح أو undefined — لئلّا نُرسل NaN كـquery param (يسبب 422).
  const toNum = (s: string): number | undefined => {
    const n = Number(s);
    return s.trim() && Number.isFinite(n) ? n : undefined;
  };

  const submit = () => {
    if (!fieldId.trim()) return;
    mut.mutate({
      field_id: fieldId.trim(),
      lat: toNum(lat),
      lon: toNum(lon),
      crop: crop.trim() || undefined,
    });
  };

  const res = mut.data;
  const conf = asText(res?.confidence);
  const truths = (res?.operational_truths ?? {}) as Record<string, unknown>;
  const policy = (res?.policy_decision ?? {}) as Record<string, unknown>;
  const sim = (res?.simulation ?? {}) as Record<string, unknown>;
  const contradictions = (res?.contradictions ?? []) as unknown[];
  const missing = (res?.missing_signals ?? []) as unknown[];
  const alerts = (res?.alerts ?? []) as Record<string, unknown>[];

  return (
    <div className="space-y-5 max-w-3xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <Activity className="w-5 h-5 text-sky-400" />
        <h2 className="text-xl font-bold text-slate-100">المايسترو — تحليل الحقل الموحّد</h2>
      </div>
      <p className="text-sm text-slate-400">
        يدمج المصادر الحيّة (طقس/تربة/استشعار/ذاكرة الحقل) في حالة موحّدة: حقائق
        تشغيليّة + ثقة + قرار سياسة + تنبيهات. المصادر المتعذّرة تُعلَن بصدق.
      </p>

      {/* Form */}
      <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'معرّف الحقل', v: fieldId, set: setFieldId, ph: 'field_06' },
            { label: 'lat', v: lat, set: setLat, ph: '15.05' },
            { label: 'lon', v: lon, set: setLon, ph: '45.55' },
            { label: 'المحصول', v: crop, set: setCrop, ph: 'قمح صلب' },
          ].map(f => (
            <label key={f.label} className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">{f.label}</span>
              <input value={f.v} onChange={e => f.set(e.target.value)} placeholder={f.ph}
                className="px-3 py-2 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
          ))}
        </div>
        <div className="flex justify-end">
          <button onClick={submit} disabled={mut.isPending || !fieldId.trim()}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: '#0ea5e9' }}>
            <Search className="w-4 h-4" />
            {mut.isPending ? 'جارٍ التحليل…' : 'تحليل الحقل'}
          </button>
        </div>
      </div>

      {mut.isError && <ErrorState title="تعذّر تحليل الحقل" onRetry={submit} />}

      {res && (
        <div className="space-y-4">
          {/* Confidence */}
          <Section title="الثقة">
            <div className="flex items-center gap-3">
              <span className="text-2xl font-bold text-emerald-400">
                {CONF_AR[conf] ?? conf ?? '—'}
              </span>
              {res.confidence_reason && <span className="text-xs text-slate-400">{res.confidence_reason}</span>}
            </div>
          </Section>

          {/* Operational truths */}
          <Section title="الحقائق التشغيليّة">
            <KV data={truths} />
          </Section>

          {/* Policy decision */}
          {Object.keys(policy).length > 0 && (
            <Section title="قرار السياسة">
              <KV data={policy} />
            </Section>
          )}

          {/* Contradictions / missing */}
          {(contradictions.length > 0 || missing.length > 0) && (
            <Section title="جودة الإشارة">
              {contradictions.length > 0 && (
                <div className="mb-2">
                  <div className="text-xs text-amber-400 flex items-center gap-1 mb-1"><AlertTriangle className="w-3 h-3" /> تناقضات</div>
                  {contradictions.map((c, i) => <p key={i} className="text-xs text-slate-300">• {asText(c)}</p>)}
                </div>
              )}
              {missing.length > 0 && (
                <div>
                  <div className="text-xs text-slate-500 mb-1">إشارات ناقصة (مصادر متعذّرة)</div>
                  <p className="text-xs text-slate-400">{missing.map(asText).join('، ')}</p>
                </div>
              )}
            </Section>
          )}

          {/* Alerts */}
          {alerts.length > 0 && (
            <Section title={`التنبيهات (${alerts.length})`}>
              <div className="space-y-2">
                {alerts.map((a, i) => (
                  <div key={i} className="text-xs text-slate-300 border-r-2 pr-2" style={{ borderColor: '#f59e0b' }}>
                    {asText(a.message_ar ?? a.message ?? a.title ?? a)}
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* Simulation */}
          {Object.keys(sim).length > 0 && (
            <Section title="أثر المحاكاة (what-if)">
              <KV data={sim} />
            </Section>
          )}

          {/* Provenance toggle */}
          <button onClick={() => setShowProv(s => !s)}
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200">
            {showProv ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            {showProv ? 'إخفاء المصدريّة (provenance)' : 'عرض المصدريّة (provenance)'}
          </button>
          {showProv && res.provenance && (
            <div className="rounded-xl border p-4 font-mono text-[11px] text-slate-400 break-all" style={{ background: '#0d1611', borderColor: '#334155' }}>
              {asText(res.provenance)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
