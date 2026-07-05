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
  type EntityLineage, type SharingKey,
} from '../services/api';
import { useSharingKeys, useCreateSharingKey } from '../hooks/useApi';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { canManage } from '../lib/permissions';
import { useAuthStore } from '../hooks/useAuth';
import { useSelectedField } from '../hooks/useSelectedField';
import { toastStore } from '../services/websocket';
import { Card as DSCard, Button, Pill, StatBox } from '../components/ds/atoms';
import { Input, Select } from '../components/ds/forms';
import { DataTable, type Column } from '../components/ds/table';
import { T, RADIUS } from '../components/ds/tokens';

// رسالة خطأ صادقة حسب رمز الحالة من الخادم (يطابق بقيّة الصفحات).
function errorDetail(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status;
  if (status === 503) return 'خدمة الحوكمة غير متاحة حاليّاً (قاعدة البيانات معطّلة).';
  if (status === 401) return 'انتهت الجلسة — يُرجى تسجيل الدخول من جديد.';
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
        <h2 className="text-xl font-bold flex items-center gap-2" style={{ color: T.ink }}>
          <ShieldCheck className="w-5 h-5" style={{ color: T.green }} />
          الحوكمة والتدقيق
        </h2>
        <p className="text-sm mt-1" style={{ color: T.muted }}>
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

// ── قسم بطاقة موحّد (DS Card) ──
function Card({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <DSCard>
      <h3 className="text-sm font-bold flex items-center gap-2 mb-3" style={{ color: T.ink }}>
        {icon}
        {title}
      </h3>
      {children}
    </DSCard>
  );
}

function EntityInputs({
  entityType, setEntityType, entityId, setEntityId, onSubmit, busy,
}: {
  entityType: string; setEntityType: (v: string) => void;
  entityId: string; setEntityId: (v: string) => void;
  onSubmit: (entityIdOverride?: string) => void; busy: boolean;
}) {
  const { options, fieldId, setFieldId, isLoading: fieldsLoading } = useSelectedField();
  const effectiveEntityId = entityType === 'field' ? (fieldId ?? '') : entityId;
  const disabled = busy || !effectiveEntityId.trim();
  return (
    <div className="flex flex-wrap items-end gap-2">
      <div style={{ width: 128 }}>
        <Select label="نوع الكيان" value={entityType} onChange={setEntityType} options={[{ value: 'field', label: 'field' }, { value: 'command', label: 'command' }, { value: 'recommendation', label: 'recommendation' }]} />
      </div>
      {entityType === 'field' ? (
        <div className="flex-1 min-w-[220px]">
          <Select
            label="الحقل"
            value={fieldId ?? ''}
            onChange={(v) => setFieldId(v || null, { source: 'user' })}
            disabled={fieldsLoading || options.length === 0}
            options={[{ value: '', label: fieldsLoading ? 'جارٍ تحميل الحقول…' : 'اختر الحقل' }, ...options.map((f) => ({ value: f.id, label: `${f.name}${f.crop && f.crop !== '—' ? ` · ${f.crop}` : ''}` }))]}
          />
        </div>
      ) : (
        <div className="flex-1 min-w-[180px]" onKeyDown={(e) => { if (e.key === 'Enter' && !disabled) onSubmit(entityId); }}>
          <Input label="معرّف الكيان" value={entityId} onChange={setEntityId} placeholder="أدخل معرّف الكيان" />
        </div>
      )}
      <Button tone="green" full={false} disabled={disabled} onClick={() => { if (entityType === 'field') setEntityId(effectiveEntityId); onSubmit(effectiveEntityId); }}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
        تتبّع
      </Button>
    </div>
  );
}

function LineageSection() {
  const [entityType, setEntityType] = useState('field');
  const [entityId, setEntityId] = useState('');
  const [st, setSt] = useState<LookupState<EntityLineage>>(idle());

  const run = async (entityIdOverride?: string) => {
    const effectiveId = (entityIdOverride ?? entityId).trim();
    setSt({ loading: true, error: null, data: null, done: false });
    try {
      const data = await getEntityLineage(entityType.trim() || 'field', effectiveId);
      setSt({ loading: false, error: null, data, done: true });
    } catch (error) {
      setSt({ loading: false, error, data: null, done: true });
    }
  };

  return (
    <Card icon={<GitBranch className="w-4 h-4" style={{ color: T.green }} />} title="أصل الكيان (Lineage)">
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
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <StatBox label="الإجمالي" value={st.data.total_entries} />
                <StatBox label="أوامر" value={st.data.commands_count} />
                <StatBox label="أحداث" value={st.data.events_count} />
                <StatBox label="الأحدث" value={fmtDate(st.data.latest_at)} />
              </div>
              <ol className="relative space-y-2 pr-4" style={{ borderInlineStart: `1px solid ${T.line}` }}>
                {st.data.entries.map((e, i) => (
                  <li key={i} className="text-sm">
                    <div className="flex items-center gap-2">
                      <span
                        className="text-[11px]"
                        style={{ padding: '2px 6px', borderRadius: RADIUS.sm, background: T.card2, color: T.muted }}
                      >
                        {e.source_type}
                      </span>
                      <span style={{ color: T.ink, fontWeight: 600 }}>{e.action ?? '—'}</span>
                      <span className="text-[11px]" style={{ color: T.muted }}>{fmtDate(e.timestamp)}</span>
                    </div>
                    {e.summary_ar && (
                      <p className="text-xs mt-0.5" style={{ color: T.muted }}>{e.summary_ar}</p>
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

  const run = async (entityIdOverride?: string) => {
    const effectiveId = (entityIdOverride ?? entityId).trim();
    setSt({ loading: true, error: null, data: null, done: false });
    try {
      const res = await getEntityEvents(entityType.trim() || 'field', effectiveId);
      setSt({ loading: false, error: null, data: res.events ?? [], done: true });
    } catch (error) {
      setSt({ loading: false, error, data: null, done: true });
    }
  };

  return (
    <Card icon={<Search className="w-4 h-4" style={{ color: T.green }} />} title="أحداث الكيان (Events)">
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
            <pre
              className="text-xs rounded-lg p-3 overflow-x-auto max-h-64"
              style={{ color: T.muted, background: T.card2 }}
            >
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
    <Card icon={<Search className="w-4 h-4" style={{ color: T.green }} />} title="البحث عن أمر (Command)">
      <div className="flex flex-wrap items-end gap-2">
        <div
          className="flex-1 min-w-[180px]"
          onKeyDown={(e) => { if (e.key === 'Enter' && !disabled) run(); }}
        >
          <Input label="معرّف الأمر" value={commandId} onChange={setCommandId} placeholder="cmd_..." />
        </div>
        <Button tone="green" full={false} disabled={disabled} onClick={run}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          {st.loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          بحث
        </Button>
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
          <p className="text-sm flex items-center gap-2" style={{ color: T.green }}>
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
  // SharingScope الخادم = 'read' | 'read_write' (لا 'write' — كان سيُرفض بـ422).
  const [scope, setScope] = useState<'read' | 'read_write'>('read');
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

  const columns: Column<SharingKey>[] = [
    {
      key: 'key_prefix',
      label: 'المفتاح',
      render: (k) => <code className="font-mono" style={{ color: T.ink }} dir="ltr">{k.key_prefix ?? k.key_id}</code>,
    },
    {
      key: 'scope',
      label: 'النطاق',
      render: (k) => (k.scope ? <Pill tone="neutral">{k.scope}</Pill> : <span style={{ color: T.faint }}>—</span>),
    },
    {
      key: 'expires_at',
      label: 'تنتهي في',
      render: (k) => <span style={{ color: T.muted }}>{fmtDate(k.expires_at as string | null)}</span>,
    },
    {
      key: 'revoked_at',
      label: 'الحالة',
      render: (k) => (k.revoked_at != null ? <Pill tone="danger">ملغى</Pill> : <Pill tone="ok">فعّال</Pill>),
    },
  ];

  return (
    <Card icon={<KeyRound className="w-4 h-4" style={{ color: T.green }} />} title="مفاتيح المشاركة">
      {manageable && (
        <div
          className="mb-4 space-y-3"
          style={{ padding: 12, borderRadius: RADIUS.md, border: `1px solid ${T.line}`, background: T.card2 }}
        >
          <div className="flex flex-wrap items-end gap-2">
            <div style={{ minWidth: 140 }}>
              <Select<'read' | 'read_write'>
                label="النطاق"
                value={scope}
                onChange={setScope}
                options={[
                  { value: 'read', label: 'قراءة' },
                  { value: 'read_write', label: 'قراءة وكتابة' },
                ]}
              />
            </div>
            <div style={{ width: 110 }}>
              <Input
                label="صلاحيّة (يوم)"
                type="number"
                inputMode="numeric"
                value={String(validDays)}
                onChange={(v) => setValidDays(Math.max(1, Number(v) || 1))}
              />
            </div>
            <div className="flex-1 min-w-[160px]">
              <Input
                label="اسم الطرف (اختياري)"
                value={partyName}
                onChange={setPartyName}
                placeholder="المهندس الزراعيّ الموثوق"
              />
            </div>
            <Button tone="green" full={false} disabled={create.isPending} onClick={submit}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              {create.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />}
              إنشاء مفتاح
            </Button>
          </div>

          {plaintext && (
            <div
              className="text-xs"
              style={{ padding: 10, borderRadius: RADIUS.sm, border: `1px solid ${T.warn}66`, background: T.warnBg }}
            >
              <p className="flex items-center gap-1.5 mb-1" style={{ color: T.warn, fontWeight: 700 }}>
                <AlertTriangle className="w-3.5 h-3.5" />
                انسخ المفتاح الآن — لن يُعرَض مجدّداً.
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 break-all" style={{ color: T.ink }}>{plaintext}</code>
                <button
                  onClick={() => {
                    void navigator.clipboard?.writeText(plaintext);
                    toastStore.add('success', 'نسخ', 'نُسخ المفتاح');
                  }}
                  style={{ padding: 6, borderRadius: RADIUS.sm, border: `1px solid ${T.line}`, background: T.card, cursor: 'pointer' }}
                  title="نسخ"
                >
                  <Copy className="w-3.5 h-3.5" style={{ color: T.ink }} />
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
          <DataTable<SharingKey>
            columns={columns}
            rows={data}
            rowKey={(k) => k.key_id}
          />
        )
      )}
    </Card>
  );
}

function fmtDate(v: string | null | undefined): string {
  if (!v) return '—';
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString('ar');
}
