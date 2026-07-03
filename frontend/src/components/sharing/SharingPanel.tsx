// ═══════════════════════════════════════════════════════════════
// SAHOOL — SharingPanel (واجهة مشاركة بمستوى الحقل)
// ───────────────────────────────────────────────────────────────
// تُنشئ وتسرد «مفاتيح المشاركة» عبر النقاط القائمة (لا نقاط جديدة):
//   GET  /api/v1/sharing/keys      → useSharingKeys
//   POST /api/v1/sharing/keys      → useCreateSharingKey
// الصدق (ما هو حقيقيّ): الخادم يدعم تقييد المفتاح بحقول محدّدة عبر
// allowed_field_ids — وهذا هو «المستوى الحقليّ» الفعليّ للمشاركة. النطاق
// (scope) = 'read' | 'read_write'. لا «حذف/إلغاء» مفتاح من الواجهة (لا نقطة
// إلغاء مكشوفة عبر هذه الـAPI) — نعرض حالة الإلغاء (revoked_at) إن وردت من
// الخادم فقط. المفتاح النصّيّ الكامل يُعرَض **مرّة واحدة** بعد الإنشاء ثمّ يُهمَل
// (لا يُعاد عرضه أبداً) — نُبرز ذلك بصدق. يُعاد استخدام عناصر نظام التصميم (DS).
// واعٍ RTL. مُقيَّد بالدور: الإنشاء يتطلّب صلاحيّة دعوة (canManage) — والإنفاذ
// الحقيقيّ خادم-جانبيّ (403 لغير المخوّل).
// ═══════════════════════════════════════════════════════════════
import { useEffect, useMemo, useState } from 'react';
import { KeyRound, Plus, Copy, Check, AlertTriangle, Share2 } from 'lucide-react';
import { useSharingKeys, useCreateSharingKey } from '../../hooks/useApi';
import { useSelectedField } from '../../hooks/useSelectedField';
import { useAuthStore } from '../../hooks/useAuth';
import { canManage } from '../../lib/permissions';
import { apiErrorMessage, type SharingKey, type SharingScope } from '../../services/api';
import { Card, Button, Pill, SectionLabel } from '../ds/atoms';
import { Input, Select, Checkbox, FormField } from '../ds/forms';
import { Modal } from '../ds/modal';
import { DataTable, type Column } from '../ds/table';
import { T } from '../ds/tokens';
import { LoadingState, ErrorState, EmptyState } from '../StateViews';

const SCOPE_LABEL: Record<SharingScope, string> = {
  read: 'قراءة',
  read_write: 'قراءة وكتابة',
};
const SCOPE_OPTIONS: { value: SharingScope; label: string }[] = [
  { value: 'read', label: 'قراءة فقط' },
  { value: 'read_write', label: 'قراءة وكتابة' },
];

function fmtDate(v: string | null | undefined): string {
  if (!v) return '—';
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleDateString('ar');
}

// ── نموذج إنشاء مفتاح مشاركة (داخل مودال) ─────────────────────────
function CreateKeyDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (plaintext: string) => void;
}) {
  const create = useCreateSharingKey();
  const { options: fields, isLoading: fieldsLoading, fieldId: activeFieldId } = useSelectedField();

  const [scope, setScope] = useState<SharingScope>('read');
  const [validDays, setValidDays] = useState('30');
  const [partyName, setPartyName] = useState('');
  // المجموعة الفارغة ⇒ كلّ الحقول (مشاركة على مستوى المستأجِر). مجموعة غير
  // فارغة ⇒ تقييد بمستوى الحقل (allowed_field_ids) — وهو جوهر هذه الواجهة.
  const [allFields, setAllFields] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // FieldView: عند تقييد المشاركة بحقول محددة، نبدأ بالحقل النشط بدل قائمة فارغة.
  useEffect(() => {
    if (!allFields && selected.size === 0 && activeFieldId) {
      setSelected(new Set([activeFieldId]));
    }
  }, [activeFieldId, allFields, selected.size]);

  const days = Math.max(1, Number(validDays) || 1);
  const fieldError = !allFields && selected.size === 0
    ? 'اختر حقلاً واحداً على الأقلّ، أو فعّل «كلّ الحقول».'
    : undefined;
  const canSubmit = !create.isPending && !fieldError;

  const toggleField = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const reset = () => {
    setScope('read');
    setValidDays('30');
    setPartyName('');
    setAllFields(true);
    setSelected(new Set());
  };

  const submit = () => {
    if (!canSubmit) return;
    create.mutate(
      {
        scope,
        valid_days: days,
        ...(partyName.trim() ? { third_party_name: partyName.trim() } : {}),
        ...(!allFields && selected.size > 0 ? { allowed_field_ids: [...selected] } : {}),
      },
      {
        onSuccess: (res) => {
          onCreated(res.key_plaintext);
          reset();
          onClose();
        },
      },
    );
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="إنشاء مفتاح مشاركة"
      maxWidth={560}
      footer={
        <>
          <Button tone="gold" full={false} onClick={onClose} style={{ background: T.card2, color: T.brownSoft }}>
            إلغاء
          </Button>
          <Button full={false} onClick={submit} disabled={!canSubmit}>
            {create.isPending ? 'جارٍ الإنشاء…' : 'إنشاء المفتاح'}
          </Button>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }} dir="rtl">
        <p style={{ fontSize: 12, color: T.muted, lineHeight: 1.6 }}>
          يمنح المفتاح طرفاً ثالثاً وصولاً مُحدَّداً. يمكنك قصره على{' '}
          <strong style={{ color: T.ink }}>حقول بعينها</strong> (مشاركة بمستوى الحقل) أو منحه على كلّ
          الحقول. المفتاح النصّيّ الكامل يُعرَض <strong style={{ color: T.warn }}>مرّة واحدة فقط</strong> بعد
          الإنشاء.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
          <Select<SharingScope>
            label="نطاق الصلاحيّة"
            value={scope}
            onChange={setScope}
            options={SCOPE_OPTIONS}
          />
          <Input
            label="مدّة الصلاحيّة (يوم)"
            type="number"
            inputMode="numeric"
            value={validDays}
            onChange={setValidDays}
            hint="من 1 يوم فأكثر"
          />
        </div>

        <Input
          label="اسم الطرف المُستفيد (اختياري)"
          value={partyName}
          onChange={setPartyName}
          placeholder="مثال: المهندس الزراعيّ الموثوق"
        />

        <div>
          <SectionLabel>نطاق الحقول</SectionLabel>
          <Checkbox
            checked={allFields}
            onChange={(c) => { setAllFields(c); if (c) setSelected(new Set()); }}
            label="كلّ الحقول (مشاركة على مستوى المستأجِر)"
          />
          {!allFields && (
            <FormField error={fieldError} hint={fieldError ? undefined : 'حدّد الحقول المسموح بها لهذا المفتاح.'}>
              {() => (
                <div
                  style={{
                    marginTop: 8,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                    maxHeight: 200,
                    overflowY: 'auto',
                    border: `1px solid ${T.line}`,
                    borderRadius: 8,
                    padding: 10,
                    background: T.card,
                  }}
                >
                  {fieldsLoading ? (
                    <span style={{ fontSize: 12, color: T.muted }}>جارٍ تحميل الحقول…</span>
                  ) : fields.length === 0 ? (
                    <span style={{ fontSize: 12, color: T.muted }}>لا توجد حقول لتقييد المشاركة بها.</span>
                  ) : (
                    fields.map((f) => (
                      <Checkbox
                        key={f.id}
                        checked={selected.has(f.id)}
                        onChange={() => toggleField(f.id)}
                        label={f.name}
                      />
                    ))
                  )}
                </div>
              )}
            </FormField>
          )}
        </div>

        {create.isError && (
          <p style={{ fontSize: 12, color: T.danger, display: 'flex', alignItems: 'center', gap: 6 }} role="alert">
            <AlertTriangle style={{ width: 14, height: 14, flexShrink: 0 }} aria-hidden="true" />
            {apiErrorMessage(create.error, 'تعذّر إنشاء المفتاح — تحقّق من الصلاحيّة والاتصال.')}
          </p>
        )}
      </div>
    </Modal>
  );
}

// ── بطاقة عرض المفتاح المُنشأ (مرّة واحدة) ────────────────────────
function PlaintextBanner({ plaintext, onDismiss }: { plaintext: string; onDismiss: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(plaintext);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* الحافظة غير متاحة — يبقى المفتاح ظاهراً للنسخ اليدويّ */
    }
  };
  return (
    <div
      style={{
        background: T.warnBg,
        border: `1px solid ${T.warn}`,
        borderRadius: 12,
        padding: 12,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
      role="status"
    >
      <p style={{ fontSize: 12, color: T.brownSoft, display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700 }}>
        <AlertTriangle style={{ width: 14, height: 14, flexShrink: 0, color: T.warn }} aria-hidden="true" />
        انسخ المفتاح الآن — لن يُعرَض مجدّداً.
      </p>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <code
          dir="ltr"
          style={{
            flex: 1,
            fontSize: 12,
            color: T.ink,
            background: T.card,
            border: `1px solid ${T.line}`,
            borderRadius: 8,
            padding: '8px 10px',
            wordBreak: 'break-all',
          }}
        >
          {plaintext}
        </code>
        <Button full={false} tone="gold" onClick={copy} style={{ padding: '8px 12px' }}>
          {copied ? <Check style={{ width: 14, height: 14 }} /> : <Copy style={{ width: 14, height: 14 }} />}
          {copied ? ' نُسخ' : ' نسخ'}
        </Button>
        <Button full={false} onClick={onDismiss} style={{ padding: '8px 12px', background: T.card2, color: T.brownSoft }}>
          إخفاء
        </Button>
      </div>
    </div>
  );
}

// ── اللوحة الرئيسيّة ──────────────────────────────────────────────
export default function SharingPanel() {
  const role = useAuthStore((s) => s.user?.role);
  const manageable = canManage(role);
  const { data, isLoading, error, refetch } = useSharingKeys();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [plaintext, setPlaintext] = useState<string | null>(null);

  const keys: SharingKey[] = data ?? [];

  const columns = useMemo<Column<SharingKey>[]>(() => {
    const fieldCount = (k: SharingKey): number => {
      const ids = k.allowed_field_ids;
      return Array.isArray(ids) ? ids.length : 0;
    };
    return [
      {
        key: 'key_prefix',
        label: 'المفتاح',
        render: (k) => (
          <code dir="ltr" style={{ fontSize: 12, color: T.ink }}>
            {(k.key_prefix as string | undefined) ?? k.key_id}
          </code>
        ),
      },
      {
        key: 'scope',
        label: 'النطاق',
        render: (k) => (
          <Pill tone={k.scope === 'read_write' ? 'warn' : 'info'}>
            {SCOPE_LABEL[(k.scope as SharingScope) ?? 'read'] ?? String(k.scope ?? '—')}
          </Pill>
        ),
      },
      {
        key: 'allowed_field_ids',
        label: 'الحقول',
        render: (k) => {
          const n = fieldCount(k);
          return n > 0 ? (
            <Pill tone="ok">{`${n} حقل محدّد`}</Pill>
          ) : (
            <span style={{ fontSize: 12, color: T.muted }}>كلّ الحقول</span>
          );
        },
      },
      {
        key: 'expires_at',
        label: 'تنتهي في',
        render: (k) => <span style={{ fontSize: 12, color: T.muted }}>{fmtDate(k.expires_at)}</span>,
      },
      {
        key: 'revoked_at',
        label: 'الحالة',
        render: (k) =>
          k.revoked_at != null ? (
            <Pill tone="danger">ملغى</Pill>
          ) : (
            <Pill tone="ok">نشط</Pill>
          ),
      },
    ];
  }, []);

  return (
    <Card>
      <SectionLabel
        action={
          manageable ? (
            <Button full={false} onClick={() => setDialogOpen(true)} style={{ padding: '8px 12px' }}>
              <Plus style={{ width: 14, height: 14 }} /> مفتاح جديد
            </Button>
          ) : undefined
        }
      >
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Share2 style={{ width: 14, height: 14, color: T.gold }} aria-hidden="true" />
          مفاتيح المشاركة (بمستوى الحقل)
        </span>
      </SectionLabel>

      <p style={{ fontSize: 12, color: T.muted, lineHeight: 1.6, marginBottom: 12 }}>
        امنح أطرافاً ثالثة (مهندس زراعيّ، مورّد، جهة تمويل) وصولاً مُحدَّداً ببيانات مزرعتك — قراءةً أو قراءةً
        وكتابةً — مع إمكان <strong style={{ color: T.ink }}>قصر المفتاح على حقول بعينها</strong>. المفتاح النصّيّ
        يُعرَض مرّة واحدة فقط بعد الإنشاء.
      </p>

      {plaintext && (
        <div style={{ marginBottom: 12 }}>
          <PlaintextBanner plaintext={plaintext} onDismiss={() => setPlaintext(null)} />
        </div>
      )}

      {isLoading ? (
        <LoadingState message="جارٍ تحميل المفاتيح…" />
      ) : error != null ? (
        <ErrorState
          title="تعذّر تحميل مفاتيح المشاركة"
          detail={apiErrorMessage(error, 'قد تكون قاعدة البيانات غير متاحة (503) أو لا تملك الصلاحيّة (403).')}
          onRetry={() => void refetch()}
        />
      ) : keys.length === 0 ? (
        <EmptyState
          icon={<KeyRound className="w-8 h-8" />}
          title="لا توجد مفاتيح مشاركة بعد"
          hint={manageable ? 'أنشئ مفتاحاً جديداً لمشاركة بياناتك بأمان.' : 'لم يُنشأ أيّ مفتاح حتى الآن.'}
        />
      ) : (
        <DataTable<SharingKey>
          columns={columns}
          rows={keys}
          rowKey={(k) => k.key_id}
          emptyTitle="لا توجد مفاتيح مشاركة بعد"
        />
      )}

      {manageable && (
        <CreateKeyDialog
          open={dialogOpen}
          onClose={() => setDialogOpen(false)}
          onCreated={(pt) => setPlaintext(pt)}
        />
      )}
    </Card>
  );
}
