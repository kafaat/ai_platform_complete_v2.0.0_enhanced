// ═══════════════════════════════════════════════════════════════
// SAHOOL — GovernancePage (الحوكمة والتدقيق)
// عارض قراءة-غالباً للأنظمة الخلفيّة التي لم يكن لها واجهة: أصل الكيان
// (lineage)، أحداثه (events)، البحث عن أمر (command)، ومفاتيح المشاركة.
// كلّها DB-backed (عبر tenant_connection + RLS): عند تعطيل قاعدة البيانات
// يُرجِع الخادم 503 وتُعرَض حالة صادقة (StateViews). لا بيانات مُلفَّقة —
// سجلّ التدقيق حقيقيّ أو لا شيء. إدارة فقط (owner/manager). مفتاح المشاركة
// يُعرَض نصّاً كاملاً مرّة واحدة فقط بعد الإنشاء.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  GitBranch, Search, KeyRound, ShieldCheck, Loader2, Copy, AlertTriangle,
} from 'lucide-react';
import {
  getEntityLineage, getEntityEvents, getCommand,
  type EntityLineage,
} from '../services/api';
import { useSharingKeys, useCreateSharingKey } from '../hooks/useApi';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { canManage } from '../lib/permissions';
import { useAuthStore } from '../hooks/useAuth';
import { toastStore } from '../services/websocket';

// رسالة خطأ صادقة حسب رمز الحالة من الخادم (يطابق بقيّة الصفحات).
function errorDetail(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status;
  if (status === 503) return 'خدمة الحوكمة غير متاحة حاليّاً (قاعدة البيانات معطّلة).';
  if (status === 403) return 'لا تملك صلاحيّة الوصول إلى سجلّ التدقيق.';
  if (status === 404) return 'العنصر غير موجود.';
  const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return detail ?? 'تعذّر إكمال الطلب — حاول مجدّداً.';
}

type LookupState<T> = { loading: boolean; error: unknown; data: T | null; done: boolean };
const idle = <T,>(): LookupState<T> => ({ loading: false, error: null, data: null, done: false });

export default function GovernancePage() {
  const role = useAuthStore((s) => s.user?.role);
  const manageable = canManage(role);

  return (
    <div className="space-y-6 max-w-5xl mx-auto" dir="rtl">
      <header>
        <h2 className="text-xl font-bold text-sahool-text flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-sahool-green" />
          الحوكمة والتدقيق
        </h2>
        <p className="text-sm text-sahool-muted mt-1">
          تتبّع أصل الكيانات وأحداثها وأوامرها، وإدارة مفاتيح المشاركة. سجلّ حقيقيّ
          عبر قاعدة البيانات (يُعرَض 503 بصدق عند تعطّلها) — بلا أيّ بيانات مُختلَقة.
        </p>
      </header>

      <LineageSection />
      <EventsSection />
      <CommandSection />
      <SharingSection manageable={manageable} />
    </div>
  );
}

// ── قسم بطاقة موحّد ──
function Card({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-sahool-border bg-sahool-surface/40 p-4">
      <h3 className="text-sm font-bold text-sahool-text flex items-center gap-2 mb-3">
        {icon}
        {title}
      </h3>
      {children}
    </section>
  );
}

function EntityInputs({
  entityType, setEntityType, entityId, setEntityId, onSubmit, busy,
}: {
  entityType: string; setEntityType: (v: string) => void;
  entityId: string; setEntityId: (v: string) => void;
  onSubmit: () => void; busy: boolean;
}) {
  const disabled = busy || !entityId.trim();
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="flex flex-col gap-1 text-xs text-sahool-muted">
        نوع الكيان
        <input
          value={entityType}
          onChange={(e) => setEntityType(e.target.value)}
          placeholder="field"
          className="px-2 py-1.5 rounded-lg bg-sahool-bg border border-sahool-border text-sm text-sahool-text w-32"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-sahool-muted flex-1 min-w-[180px]">
        معرّف الكيان
        <input
          value={entityId}
          onChange={(e) => setEntityId(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !disabled) onSubmit(); }}
          placeholder="field_..."
          className="px-2 py-1.5 rounded-lg bg-sahool-bg border border-sahool-border text-sm text-sahool-text w-full"
        />
      </label>
      <button
        onClick={onSubmit}
        disabled={disabled}
        className="px-3 py-1.5 rounded-lg bg-sahool-green text-white text-sm disabled:opacity-50 flex items-center gap-1.5"
      >
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
        تتبّع
      </button>
    </div>
  );
}

function LineageSection() {
  const [entityType, setEntityType] = useState('field');
  const [entityId, setEntityId] = useState('');
  const [st, setSt] = useState<LookupState<EntityLineage>>(idle());

  const run = async () => {
    setSt({ loading: true, error: null, data: null, done: false });
    try {
      const data = await getEntityLineage(entityType.trim() || 'field', entityId.trim());
      setSt({ loading: false, error: null, data, done: true });
    } catch (error) {
      setSt({ loading: false, error, data: null, done: true });
    }
  };

  return (
    <Card icon={<GitBranch className="w-4 h-4 text-sahool-green" />} title="أصل الكيان (Lineage)">
      <EntityInputs
        entityType={entityType} setEntityType={setEntityType}
        entityId={entityId} setEntityId={setEntityId}
        onSubmit={run} busy={st.loading}
      />
      <div className="mt-3">
        {st.loading && <LoadingState message="جارٍ تجميع الأصل…" />}
        {!st.loading && st.error != null && (
          <ErrorState title="تعذّر جلب الأصل" detail={errorDetail(st.error)} onRetry={run} />
        )}
        {!st.loading && st.done && st.error == null && st.data && (
          st.data.total_entries === 0 ? (
            <EmptyState title="لا سجلّات أصل لهذا الكيان" />
          ) : (
            <div className="space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
                <Stat label="الإجمالي" value={st.data.total_entries} />
                <Stat label="أوامر" value={st.data.commands_count} />
                <Stat label="أحداث" value={st.data.events_count} />
                <Stat label="الأحدث" value={fmtDate(st.data.latest_at)} />
              </div>
              <ol className="relative border-r border-sahool-border pr-4 space-y-2">
                {st.data.entries.map((e, i) => (
                  <li key={i} className="text-sm">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] px-1.5 py-0.5 rounded bg-sahool-bg text-sahool-muted">
                        {e.source_type}
                      </span>
                      <span className="text-sahool-text font-medium">{e.action ?? '—'}</span>
                      <span className="text-[11px] text-sahool-muted">{fmtDate(e.timestamp)}</span>
                    </div>
                    {e.summary_ar && (
                      <p className="text-xs text-sahool-muted mt-0.5">{e.summary_ar}</p>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          )
        )}
      </div>
    </Card>
  );
}

function EventsSection() {
  const [entityType, setEntityType] = useState('field');
  const [entityId, setEntityId] = useState('');
  const [st, setSt] = useState<LookupState<unknown[]>>(idle());

  const run = async () => {
    setSt({ loading: true, error: null, data: null, done: false });
    try {
      const res = await getEntityEvents(entityType.trim() || 'field', entityId.trim());
      setSt({ loading: false, error: null, data: res.events ?? [], done: true });
    } catch (error) {
      setSt({ loading: false, error, data: null, done: true });
    }
  };

  return (
    <Card icon={<Search className="w-4 h-4 text-sahool-green" />} title="أحداث الكيان (Events)">
      <EntityInputs
        entityType={entityType} setEntityType={setEntityType}
        entityId={entityId} setEntityId={setEntityId}
        onSubmit={run} busy={st.loading}
      />
      <div className="mt-3">
        {st.loading && <LoadingState message="جارٍ جلب الأحداث…" />}
        {!st.loading && st.error != null && (
          <ErrorState title="تعذّر جلب الأحداث" detail={errorDetail(st.error)} onRetry={run} />
        )}
        {!st.loading && st.done && st.error == null && st.data && (
          st.data.length === 0 ? (
            <EmptyState title="لا أحداث لهذا الكيان" />
          ) : (
            <pre className="text-xs text-sahool-muted bg-sahool-bg rounded-lg p-3 overflow-x-auto max-h-64">
              {JSON.stringify(st.data, null, 2)}
            </pre>
          )
        )}
      </div>
    </Card>
  );
}

function CommandSection() {
  const [commandId, setCommandId] = useState('');
  const [st, setSt] = useState<LookupState<{ command_id: string; found: boolean }>>(idle());

  const run = async () => {
    setSt({ loading: true, error: null, data: null, done: false });
    try {
      const data = await getCommand(commandId.trim());
      setSt({ loading: false, error: null, data, done: true });
    } catch (error) {
      setSt({ loading: false, error, data: null, done: true });
    }
  };

  const disabled = st.loading || !commandId.trim();
  return (
    <Card icon={<Search className="w-4 h-4 text-sahool-green" />} title="البحث عن أمر (Command)">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-sahool-muted flex-1 min-w-[180px]">
          معرّف الأمر
          <input
            value={commandId}
            onChange={(e) => setCommandId(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !disabled) run(); }}
            placeholder="cmd_..."
            className="px-2 py-1.5 rounded-lg bg-sahool-bg border border-sahool-border text-sm text-sahool-text w-full"
          />
        </label>
        <button
          onClick={run}
          disabled={disabled}
          className="px-3 py-1.5 rounded-lg bg-sahool-green text-white text-sm disabled:opacity-50 flex items-center gap-1.5"
        >
          {st.loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          بحث
        </button>
      </div>
      <div className="mt-3">
        {st.loading && <LoadingState message="جارٍ البحث…" />}
        {!st.loading && st.error != null && (
          (st.error as { response?: { status?: number } })?.response?.status === 404 ? (
            <EmptyState title="الأمر غير موجود" hint={commandId} />
          ) : (
            <ErrorState title="تعذّر البحث" detail={errorDetail(st.error)} onRetry={run} />
          )
        )}
        {!st.loading && st.done && st.error == null && st.data?.found && (
          <p className="text-sm text-sahool-green flex items-center gap-2">
            <ShieldCheck className="w-4 h-4" /> الأمر موجود: {st.data.command_id}
          </p>
        )}
      </div>
    </Card>
  );
}

function SharingSection({ manageable }: { manageable: boolean }) {
  const { data, isLoading, error, refetch } = useSharingKeys();
  const create = useCreateSharingKey();
  const [scope, setScope] = useState<'read' | 'write'>('read');
  const [validDays, setValidDays] = useState(30);
  const [partyName, setPartyName] = useState('');
  const [plaintext, setPlaintext] = useState<string | null>(null);

  const submit = () => {
    setPlaintext(null);
    create.mutate(
      {
        scope,
        valid_days: validDays,
        ...(partyName.trim() ? { third_party_name: partyName.trim() } : {}),
      },
      {
        onSuccess: (res) => {
          setPlaintext(res.key_plaintext);
          setPartyName('');
          toastStore.add('success', 'مفاتيح المشاركة', 'أُنشئ مفتاح المشاركة');
          void refetch();
        },
        onError: (e) => {
          toastStore.add('error', 'مفاتيح المشاركة', errorDetail(e));
        },
      },
    );
  };

  return (
    <Card icon={<KeyRound className="w-4 h-4 text-sahool-green" />} title="مفاتيح المشاركة">
      {manageable && (
        <div className="mb-4 p-3 rounded-lg border border-sahool-border bg-sahool-bg space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-xs text-sahool-muted">
              النطاق
              <select
                value={scope}
                onChange={(e) => setScope(e.target.value as 'read' | 'write')}
                className="px-2 py-1.5 rounded-lg bg-sahool-surface border border-sahool-border text-sm text-sahool-text"
              >
                <option value="read">قراءة</option>
                <option value="write">كتابة</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-sahool-muted">
              صلاحيّة (يوم)
              <input
                type="number"
                min={1}
                value={validDays}
                onChange={(e) => setValidDays(Math.max(1, Number(e.target.value) || 1))}
                className="px-2 py-1.5 rounded-lg bg-sahool-surface border border-sahool-border text-sm text-sahool-text w-24"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-sahool-muted flex-1 min-w-[160px]">
              اسم الطرف (اختياري)
              <input
                value={partyName}
                onChange={(e) => setPartyName(e.target.value)}
                placeholder="المهندس الزراعيّ الموثوق"
                className="px-2 py-1.5 rounded-lg bg-sahool-surface border border-sahool-border text-sm text-sahool-text w-full"
              />
            </label>
            <button
              onClick={submit}
              disabled={create.isPending}
              className="px-3 py-1.5 rounded-lg bg-sahool-green text-white text-sm disabled:opacity-50 flex items-center gap-1.5"
            >
              {create.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />}
              إنشاء مفتاح
            </button>
          </div>

          {plaintext && (
            <div className="p-2.5 rounded-lg border border-amber-500/40 bg-amber-500/10 text-xs">
              <p className="text-amber-400 flex items-center gap-1.5 mb-1">
                <AlertTriangle className="w-3.5 h-3.5" />
                انسخ المفتاح الآن — لن يُعرَض مجدّداً.
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 break-all text-sahool-text">{plaintext}</code>
                <button
                  onClick={() => {
                    void navigator.clipboard?.writeText(plaintext);
                    toastStore.add('success', 'نسخ', 'نُسخ المفتاح');
                  }}
                  className="p-1.5 rounded-lg border border-sahool-border hover:border-sahool-green"
                  title="نسخ"
                >
                  <Copy className="w-3.5 h-3.5 text-sahool-text" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {isLoading && <LoadingState message="جارٍ تحميل المفاتيح…" />}
      {!isLoading && error != null && (
        <ErrorState title="تعذّر تحميل المفاتيح" detail={errorDetail(error)} onRetry={() => void refetch()} />
      )}
      {!isLoading && error == null && (
        !data || data.length === 0 ? (
          <EmptyState title="لا مفاتيح مشاركة" hint={manageable ? 'أنشئ مفتاحاً من الأعلى' : undefined} />
        ) : (
          <ul className="space-y-2">
            {data.map((k) => (
              <li
                key={k.key_id}
                className="flex items-center justify-between p-2.5 rounded-lg border border-sahool-border bg-sahool-bg text-sm"
              >
                <div className="flex items-center gap-2">
                  <code className="text-sahool-text">{k.key_prefix ?? k.key_id}</code>
                  {k.scope && (
                    <span className="text-[11px] px-1.5 py-0.5 rounded bg-sahool-surface text-sahool-muted">
                      {k.scope}
                    </span>
                  )}
                  {k.revoked && (
                    <span className="text-[11px] px-1.5 py-0.5 rounded bg-red-500/15 text-red-400">ملغى</span>
                  )}
                </div>
                <span className="text-[11px] text-sahool-muted">{fmtDate(k.expires_at as string | null)}</span>
              </li>
            ))}
          </ul>
        )
      )}
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-sahool-bg border border-sahool-border py-2">
      <div className="text-sahool-text font-bold text-sm">{value}</div>
      <div className="text-[11px] text-sahool-muted">{label}</div>
    </div>
  );
}

function fmtDate(v: string | null | undefined): string {
  if (!v) return '—';
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString('ar');
}
