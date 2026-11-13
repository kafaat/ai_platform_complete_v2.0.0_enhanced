import { useRef, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { useAuthStore } from '../hooks/useAuth';
import {
  getScoutPhotoGrants, issueScoutPhotoGrant, revokeScoutPhotoGrant,
  type ScoutPhotoGrantListing, type ScoutPhotoScope,
} from '../services/scoutPhotoGrants';
import { T } from '../components/ds';

const SCOPES: { value: ScoutPhotoScope; label: string }[] = [
  { value: 'photo.read', label: 'قراءة الصورة' },
  { value: 'photo.upload', label: 'رفع صورة' },
  { value: 'photo.context', label: 'قراءة ربط التفتيش' },
  { value: 'photo.season_link', label: 'ربط صورة بموسم معتمد' },
  { value: 'photo.detection_link', label: 'ربط الصورة بمصدر نتيجة النموذج (دون اعتماد التشخيص)' },
];

type PendingRequest = { eventId: string; payload: string };
const apiError = (err: unknown) => {
  const status = (err as { response?: { status?: number } })?.response?.status;
  if (status === 404) return 'الإدارة معطلة أو الحقل غير موجود. لم تُحفظ أيّ منحة جديدة.';
  if (status === 403) return 'رفض التفويض: يجب أن يكون الحساب مالكًا نشطًا لهذا المستأجر.';
  if (status === 409) return 'تعارض في المنحة أو مفتاح الطلب. حدّث السجل قبل المحاولة.';
  if (status === 422) return 'تأكد من الحقل والمستخدم ووقت الانتهاء والسبب.';
  if (status === 503) return 'قاعدة الإدارة غير مهيأة أو غير متاحة؛ لا تفترض نجاح العملية.';
  return 'تعذر التأكد من الحفظ. راجع السجل ثم أعد نفس الطلب قبل إنشاء طلب مختلف.';
};

/** No implicit grants. Shows real server receipts only, and keeps retry IDs on
 * uncertain network errors so a replay cannot accidentally issue twice. */
export default function ScoutPhotoGrantAdminPanel() {
  const { user } = useAuthStore();
  const [fieldId, setFieldId] = useState('');
  const [target, setTarget] = useState('');
  const [scope, setScope] = useState<ScoutPhotoScope>('photo.read');
  const [expiry, setExpiry] = useState('');
  const [reason, setReason] = useState('');
  const [listing, setListing] = useState<ScoutPhotoGrantListing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [revokeId, setRevokeId] = useState<string | null>(null);
  const issuePending = useRef<PendingRequest | null>(null);
  const revokePending = useRef<PendingRequest | null>(null);

  if (user?.role !== 'owner') return null;

  async function refresh() {
    if (!fieldId.trim()) { setError('حدد معرّف الحقل أولًا.'); return; }
    setLoading(true); setError(null); setStatus(null);
    try {
      const result = await getScoutPhotoGrants(fieldId.trim());
      setListing(result);
      // Reading the last N audit events does NOT prove an uncertain write
      // never committed. Preserve the idempotency key unless its event is
      // positively present in the server ledger; otherwise a fresh ID could
      // accidentally duplicate the original operation after a lost response.
      if (issuePending.current && result.events.some(e => e.event_id === issuePending.current?.eventId)) {
        issuePending.current = null;
      }
      if (revokePending.current && result.events.some(e => e.event_id === revokePending.current?.eventId)) {
        revokePending.current = null;
      }
    } catch (err) { setError(apiError(err)); setListing(null); }
    finally { setLoading(false); }
  }

  async function issue() {
    const userId = Number(target);
    if (!fieldId.trim() || !Number.isSafeInteger(userId) || userId <= 0 ||
        !expiry || !Number.isFinite(new Date(expiry).getTime()) || reason.trim().length < 10) {
      setError('الحقل ومعرف المستخدم وتاريخ الانتهاء وسبب مفصل (10 أحرف على الأقل) إلزامية.'); return;
    }
    const expiresAt = new Date(expiry).toISOString();
    const payload = JSON.stringify({ fieldId: fieldId.trim(), userId, scope, expiresAt, reason: reason.trim() });
    if (issuePending.current && issuePending.current.payload !== payload) {
      setError('بيانات الطلب تغيّرت بعد نتيجة غير مؤكدة. اقرأ السجل أولًا قبل إصدار أمر جديد.'); return;
    }
    const eventId = issuePending.current?.eventId ?? crypto.randomUUID();
    issuePending.current = { eventId, payload };
    setLoading(true); setError(null); setStatus(null);
    try {
      const receipt = await issueScoutPhotoGrant(fieldId.trim(), {
        event_id: eventId, user_id: userId, scope, expires_at: expiresAt, reason: reason.trim(),
      });
      setStatus(`سُجّلت المنحة ${receipt.grant_id} في الخادم (${receipt.idempotent ? 'إعادة إرسال آمنة' : 'طلب جديد'}).`);
      issuePending.current = null;
      try { setListing(await getScoutPhotoGrants(fieldId.trim())); }
      catch { setError('الإصدار ناجح بالإيصال أعلاه، لكن تعذّر تحديث القائمة. اقرأ السجل لاحقًا.'); }
    } catch (err) { setError(apiError(err)); }
    finally { setLoading(false); }
  }

  async function revoke(grantId: string) {
    if (revokeId !== grantId) { setRevokeId(grantId); return; }
    if (reason.trim().length < 10) { setError('دوّن سبب الإلغاء قبل التأكيد.'); return; }
    const payload = JSON.stringify({ fieldId: fieldId.trim(), grantId, reason: reason.trim() });
    if (revokePending.current && revokePending.current.payload !== payload) {
      setError('تغيّرت معطيات إلغاء معلّق؛ اقرأ السجل أولًا.'); return;
    }
    const eventId = revokePending.current?.eventId ?? crypto.randomUUID();
    revokePending.current = { eventId, payload };
    setLoading(true); setError(null); setStatus(null);
    try {
      const receipt = await revokeScoutPhotoGrant(fieldId.trim(), grantId,
        { event_id: eventId, reason: reason.trim() });
      setStatus(`ثُبّت إلغاء المنحة ${receipt.grant_id} في سجل الخادم.`);
      revokePending.current = null;
      setRevokeId(null);
      try { setListing(await getScoutPhotoGrants(fieldId.trim())); }
      catch { setError('الإلغاء ناجح بالإيصال أعلاه، لكن تعذّر تحديث القائمة. اقرأ السجل لاحقًا.'); }
    } catch (err) { setError(apiError(err)); }
    finally { setLoading(false); }
  }

  const inputStyle = { border: `1px solid ${T.line}`, color: T.ink, background: 'rgba(2,6,23,.45)' };
  return (
    <section className="rounded-2xl border p-4 flex flex-col gap-3" style={{ borderColor: T.line }} data-testid="scout-photo-grant-admin">
      <h2 className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
        <ShieldCheck className="w-4 h-4" aria-hidden="true" /> صلاحيات الأدلة المصورة حسب الحقل — للمالك فقط
      </h2>
      <p className="text-xs" style={{ color: T.muted }}>
        لا يمنح الدور وحده حق الوصول. يجب تحديد المستفيد والعملية ومدة الصلاحية وسببها، ويُحفظ كل إصدار أو إلغاء في سجل تدقيق غير قابل للتعديل. نتيجة صورة المرض لا تفوض مكافحة أو رشًا.
      </p>
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        <label className="text-xs flex flex-col gap-1">معرّف الحقل
          <input aria-label="معرف الحقل" value={fieldId} onChange={e => { setFieldId(e.target.value); setListing(null); }} className="p-2 rounded-lg" style={inputStyle} />
        </label>
        <label className="text-xs flex flex-col gap-1">معرّف المستخدم
          <input aria-label="معرف المستخدم" type="number" min="1" value={target} onChange={e => setTarget(e.target.value)} className="p-2 rounded-lg" style={inputStyle} />
        </label>
        <label className="text-xs flex flex-col gap-1">نطاق الصلاحية
          <select value={scope} onChange={e => setScope(e.target.value as ScoutPhotoScope)} className="p-2 rounded-lg" style={inputStyle}>
            {SCOPES.map(s => <option value={s.value} key={s.value}>{s.label}</option>)}
          </select>
        </label>
        <label className="text-xs flex flex-col gap-1">تاريخ الانتهاء (≤90 يومًا)
          <input aria-label="تاريخ انتهاء الصلاحية" type="datetime-local" value={expiry} onChange={e => setExpiry(e.target.value)} className="p-2 rounded-lg" style={inputStyle} />
        </label>
      </div>
      <label className="text-xs flex flex-col gap-1">سبب الإصدار أو الإلغاء
        <textarea aria-label="سبب الصلاحية" value={reason} onChange={e => setReason(e.target.value)} className="p-2 rounded-lg" rows={2} style={inputStyle} />
      </label>
      <div className="flex gap-2 flex-wrap">
        <button type="button" onClick={() => void refresh()} disabled={loading} className="px-3 py-2 rounded-lg border text-xs" style={inputStyle}>قراءة السجل الحي</button>
        <button type="button" onClick={() => void issue()} disabled={loading} className="px-3 py-2 rounded-lg border text-xs font-bold" style={inputStyle}>إصدار منحة محددة</button>
      </div>
      {error && <div role="alert" className="text-xs" style={{ color: '#fdba74' }}>{error}</div>}
      {status && <div role="status" className="text-xs" style={{ color: '#86efac' }}>{status}</div>}
      {listing && <div className="flex flex-col gap-2">
        <p className="text-xs" style={{ color: T.muted }}>المنح المثبتة: {listing.grants.length} · أحداث التدقيق: {listing.events.length} (آخر {listing.limit})</p>
        {listing.grants.map(grant => <div className="flex items-center justify-between gap-2 flex-wrap text-xs border rounded-lg p-2" style={inputStyle} key={grant.grant_id}>
          <span>{grant.scope} · مستخدم #{grant.user_id} · {grant.revoked_at ? 'ملغاة' : 'غير ملغاة'} · تنتهي {grant.expires_at ?? 'غير محدد (قديم)'}</span>
          {!grant.revoked_at && <button type="button" disabled={loading} className="border rounded p-1" style={{ color: '#fdba74' }} onClick={() => void revoke(grant.grant_id)}>
            {revokeId === grant.grant_id ? 'تأكيد إلغاء المنحة' : 'إلغاء الصلاحية'}
          </button>}
        </div>)}
        {listing.grants.length === 0 && <p className="text-xs" style={{ color: T.muted }}>لا منح محفوظة لهذا الحقل.</p>}
      </div>}
    </section>
  );
}
