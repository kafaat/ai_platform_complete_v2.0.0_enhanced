// ════════════════════════════════════════════════════════════
// SAHOOL — المايسترو (Field Intelligence) — ربط حيّ بـ
// POST /api/v1/field-intelligence/analyze. يُبرِز التحليل الموحّد لحقل:
// الحقائق التشغيليّة + الثقة + قرار السياسة + التناقضات + الإشارات الناقصة +
// التنبيهات الاستباقيّة + أثر المحاكاة. صدق: المصادر المتعذّرة تُعلَن (لا اختراع).
// ════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Activity, Search, ChevronDown, ChevronUp, AlertTriangle, Map, FlaskConical, ListChecks, Bot } from 'lucide-react';
import { useCancelFieldIntelligenceJob, useFieldIntelligenceJob, useStartFieldIntelligenceJob } from '../hooks/useApi';
import FieldSelector from '../components/FieldSelector';
import { ErrorState } from '../components/StateViews';
import { useSelectedField } from '../hooks/useSelectedField';

function asText(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

// مستوى الثقة نصّيّ من المحرّك (high|medium|low|none) — يُترجَم للعرض.
const CONF_AR: Record<string, string> = {
  high: 'عالية', medium: 'متوسطة', low: 'منخفضة', none: 'غير متوفّرة',
};


function WorkflowCard({ icon, title, desc }: { icon: React.ReactNode; title: string; desc: string }) {
  return (
    <div className="rounded-xl border p-3" style={{ background: '#172033', borderColor: '#334155' }}>
      <div className="flex items-center gap-2 text-slate-100 text-sm font-semibold mb-1">{icon}{title}</div>
      <p className="text-xs text-slate-400 leading-6">{desc}</p>
    </div>
  );
}

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
  const { fieldId, field: activeField } = useSelectedField();
  const [lat, setLat] = useState('');
  const [lon, setLon] = useState('');
  const [crop, setCrop] = useState('');
  const [showProv, setShowProv] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const startMut = useStartFieldIntelligenceJob();
  const jobQ = useFieldIntelligenceJob(jobId);
  const cancelMut = useCancelFieldIntelligenceJob();

  // رقم محدود صالح أو undefined — لئلّا نُرسل NaN كـquery param (يسبب 422).
  const toNum = (s: string): number | undefined => {
    const n = Number(s);
    return s.trim() && Number.isFinite(n) ? n : undefined;
  };

  const submit = () => {
    if (!fieldId) return;
    startMut.mutate({
      field_id: fieldId,
      lat: toNum(lat),
      lon: toNum(lon),
      crop: crop.trim() || undefined,
    }, {
      onSuccess: (job) => setJobId(job.job_id),
    });
  };

  const cancel = () => {
    if (!jobId) return;
    cancelMut.mutate(jobId);
  };

  const job = jobQ.data ?? startMut.data;
  const isWorking = startMut.isPending || job?.status === 'queued' || job?.status === 'running';
  const res = job?.status === 'completed' ? job.result : undefined;
  const conf = asText(res?.confidence);
  const truths = (res?.operational_truths ?? {}) as Record<string, unknown>;
  const policy = (res?.policy_decision ?? {}) as Record<string, unknown>;
  const sim = (res?.simulation ?? {}) as Record<string, unknown>;
  const contradictions = (res?.contradictions ?? []) as unknown[];
  const missing = (res?.missing_signals ?? []) as unknown[];
  const alerts = (res?.alerts ?? []) as Record<string, unknown>[];
  const dailyBrief = (res?.daily_ai_brief ?? null) as Record<string, unknown> | null;
  const dailyActions = Array.isArray(dailyBrief?.actions) ? dailyBrief.actions as Record<string, unknown>[] : [];

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

      <div className="grid sm:grid-cols-4 gap-3">
        <WorkflowCard icon={<Map className="w-4 h-4 text-emerald-400" />} title="مناطق الإنتاجية" desc="تحويل NDVI/الإنتاجية/المختبر إلى High/Medium/Low/Problem بدلاً من عرض المؤشر فقط." />
        <WorkflowCard icon={<FlaskConical className="w-4 h-4 text-sky-400" />} title="العينات والمختبر" desc="نقاط GPS ونتائج تربة/مياه تدخل بوابة القرار ولا تُستخدم إن كانت ناقصة أو غير معتمدة." />
        <WorkflowCard icon={<ListChecks className="w-4 h-4 text-amber-400" />} title="خرائط الوصفات" desc="القرار يتحول إلى وصفة ومهام يومية، ثم يُغلق بسجل تنفيذ وتغذية راجعة." />
        <WorkflowCard icon={<Bot className="w-4 h-4 text-violet-400" />} title="الموجز اليومي" desc="ضغط إشارات كثيرة إلى قائمة إجراءات قابلة للتنفيذ: ري، رش، فحص، مختبر، أو تأجيل." />
      </div>

      {/* Form */}
      <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <FieldSelector label="الحقل للتحليل" />
        {activeField ? <div className="text-xs text-slate-400">سيتم تحليل: <b className="text-slate-200">{activeField.name}</b> · {activeField.crop || 'بلا محصول'} · {activeField.area ? `${activeField.area} هـ` : 'مساحة غير معروفة'}</div> : null}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[
            { label: 'lat اختياري', v: lat, set: setLat, ph: '15.05' },
            { label: 'lon اختياري', v: lon, set: setLon, ph: '45.55' },
            { label: 'المحصول اختياري', v: crop, set: setCrop, ph: activeField?.crop || 'قمح صلب' },
          ].map(f => (
            <label key={f.label} className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">{f.label}</span>
              <input value={f.v} onChange={e => f.set(e.target.value)} placeholder={f.ph}
                className="px-3 py-2 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
          ))}
        </div>
        <div className="flex justify-end">
          <button onClick={submit} disabled={isWorking || !fieldId}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: '#0ea5e9' }}>
            <Search className="w-4 h-4" />
            {isWorking ? 'التحليل يعمل في الخلفية…' : 'تحليل الحقل'}
          </button>
        </div>
      </div>

      {(startMut.isError || jobQ.isError || job?.status === 'failed') && <ErrorState title="تعذّر تحليل الحقل" onRetry={submit} />}

      {job && job.status !== 'completed' && (
        <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-100">جاري تحليل الحقل في الخلفية</div>
              <div className="text-xs text-slate-400 mt-1">المرحلة: {job.stage || 'queued'} · التقدم {job.progress ?? 0}%</div>
            </div>
            {(job.status === 'queued' || job.status === 'running') && (
              <button onClick={cancel} disabled={cancelMut.isPending} className="px-3 py-1.5 rounded-lg text-xs font-semibold" style={{ background: '#334155', color: '#e2e8f0' }}>
                إلغاء التحليل
              </button>
            )}
          </div>
          <div className="h-2 rounded-full overflow-hidden" style={{ background: '#0f172a' }}>
            <div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(100, job.progress ?? 0))}%`, background: '#0ea5e9' }} />
          </div>
          <ol className="grid sm:grid-cols-5 gap-2 text-[11px] text-slate-400">
            <li>1. تحميل بيانات الحقل</li>
            <li>2. قراءة الموسم</li>
            <li>3. جلب الطقس</li>
            <li>4. جلب صور القمر الصناعي</li>
            <li>5. توليد التوصيات</li>
          </ol>
          {job.status === 'cancelled' && <p className="text-xs text-amber-400">تم إلغاء التحليل. يمكنك تشغيله لاحقاً.</p>}
        </div>
      )}

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

          {/* Daily AI Brief */}
          {dailyBrief && (
            <Section title="موجز اليوم — AI Agronomist">
              <div className="space-y-3">
                <div className="flex items-start gap-2 rounded-lg border p-3" style={{ background: '#0f172a', borderColor: '#334155' }}>
                  <Bot className="w-4 h-4 text-violet-400 mt-0.5" />
                  <div>
                    <div className="text-sm font-semibold text-slate-100">{asText(dailyBrief.headline_ar) || 'لا يوجد إجراء عاجل'}</div>
                    <div className="text-xs text-slate-500 mt-1">
                      سياسة العرض: {asText(dailyBrief.decision_policy ?? dailyBrief.source_policy ?? 'إجراءات مبنية على إشارات متاحة فقط')}
                    </div>
                  </div>
                </div>
                {dailyActions.length > 0 && (
                  <div className="space-y-2">
                    {dailyActions.map((a, i) => (
                      <div key={asText(a.action_id) || i} className="rounded-lg border p-3" style={{ background: '#172033', borderColor: '#334155' }}>
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-sm font-semibold text-slate-100">{asText(a.title_ar)}</span>
                          <span className="text-[11px] rounded-full px-2 py-1" style={{ background: '#312e81', color: '#ddd6fe' }}>
                            {asText(a.priority)} · {asText(a.source)}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400 mt-2 leading-6">{asText(a.reason_ar)}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
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
