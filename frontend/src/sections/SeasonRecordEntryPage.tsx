// ═══════════════════════════════════════════════════════════════
// SAHOOL — sections/SeasonRecordEntryPage.tsx
// ترقيم المواسم الورقيّة (SEASON-RECORD-ENTRY-01 شريحة 3c، الأخيرة).
// التدفّق المتدرّج: رسم الحقل → بيانات الموسم + المحصول → مرفق الدفتر → تسليم للقبول.
// يعيد استخدام مكوّن رسم الحقل (AddFieldWithMap) وقشرة الخطوات (StepShell)، ويستمرّ
// عبر الجلسات بـdraft_key (نفس مفتاح تكرار النقطة الخلفيّة — إعادة التحميل تستأنف لا تُكرّر).
//
// حدّ صادق للنطاق: الخلفيّة تعرض حاليّاً ستّ نقاط (مسودّة+محصول · تحديث · رفع/معاينة دفتر ·
// قبول · قائمة). **تسجيل الأحداث/الحصاد/التكاليف نقاطُه الخلفيّة غير مبنيّة بعد** (شريحة لاحقة)
// — فلا نبني نماذج تُرسِل إلى العدم (نصف الحلّ الممنوع)؛ نُصرّح ذلك في خطوة المراجعة وفي سجلّ الفجوات.
//
// القبول فعل حسّاس: البوّابة توقّع هويّة المُراجِع (owner/expert) وتحقن التصديق؛ الواجهة تُصدِر
// الطلب فقط. رفض 403 (دور غير مؤهَّل) أو 401 (لا توقيع) يُعرَض بصدق لا يُبتَلع.
// ═══════════════════════════════════════════════════════════════
import { useCallback, useEffect, useState } from 'react';
import {
  CalendarRange,
  MapPinned,
  BookImage,
  CheckCircle2,
  Sprout,
  RefreshCw,
  FileWarning,
} from 'lucide-react';
import AddFieldWithMap from '../components/AddFieldWithMap';
import StepShell from '../components/fieldsetup/StepShell';
import { kongApi, apiErrorMessage } from '../services/api';
import {
  acceptSeason,
  createSeasonDraft,
  listSeasons,
  uploadSeasonLogbook,
  type SeasonListRow,
  type SowingPrecision,
} from '../services/api/season';
import {
  clearSeasonDraft,
  loadSeasonDraft,
  newDraftKey,
  saveSeasonDraft,
  type SeasonDraftSnapshot,
} from '../lib/seasonDraftStorage';

type Phase = 'list' | 'draw' | 'details' | 'logbook' | 'review' | 'done';

// FieldData الذي يمرّره AddFieldWithMap.onSave (مجموعة جزئيّة كافية لإنشاء الحقل).
interface DrawnField {
  name: string;
  manager?: string;
  crop?: string;
  soil_type?: string;
  area_ha: number;
  geometry: { type: string; coordinates: number[][][] };
  boundary_metadata?: Record<string, unknown>;
  idempotency_key?: string;
}

const SOWING_PRECISION_OPTS: { value: SowingPrecision; label: string }[] = [
  { value: 'day', label: 'يوم دقيق' },
  { value: 'month', label: 'شهر تقريبيّ' },
  { value: 'season', label: 'موسم فقط' },
];

export default function SeasonRecordEntryPage() {
  const [phase, setPhase] = useState<Phase>('list');
  const [draftKey, setDraftKey] = useState<string>('');
  const [fieldId, setFieldId] = useState('');
  const [fieldName, setFieldName] = useState('');
  const [seasonId, setSeasonId] = useState('');

  // بيانات الموسم + المحصول
  const [seasonLabel, setSeasonLabel] = useState('');
  const [observedFrom, setObservedFrom] = useState('');
  const [observedTo, setObservedTo] = useState('');
  const [varietyName, setVarietyName] = useState('');
  const [sowingDate, setSowingDate] = useState('');
  const [sowingPrecision, setSowingPrecision] = useState<SowingPrecision>('day');
  const [seedRate, setSeedRate] = useState('');
  const [notes, setNotes] = useState('');

  const [logbookFile, setLogbookFile] = useState<File | null>(null);
  const [acceptedBy, setAcceptedBy] = useState('');

  const [drafts, setDrafts] = useState<SeasonListRow[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [listError, setListError] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // ── استمرار المسودّة عبر الجلسات ────────────────────────────────
  const persist = useCallback(
    (over: Partial<SeasonDraftSnapshot>) => {
      const snap: SeasonDraftSnapshot = {
        draftKey,
        fieldId,
        fieldName,
        seasonId: seasonId || undefined,
        phase,
        observedFrom,
        observedTo,
        seasonLabel,
        varietyName,
        sowingDate,
        ...over,
      };
      saveSeasonDraft(snap);
    },
    [
      draftKey, fieldId, fieldName, seasonId, phase,
      observedFrom, observedTo, seasonLabel, varietyName, sowingDate,
    ],
  );

  // استعادة أيّ مسودّة محفوظة عند أوّل تحميل (استئناف بعد إعادة تحميل الصفحة).
  useEffect(() => {
    const snap = loadSeasonDraft();
    if (snap && snap.phase !== 'list' && snap.phase !== 'done') {
      setDraftKey(snap.draftKey);
      setFieldId(snap.fieldId);
      setFieldName(snap.fieldName);
      setSeasonId(snap.seasonId ?? '');
      setSeasonLabel(snap.seasonLabel ?? '');
      setObservedFrom(snap.observedFrom ?? '');
      setObservedTo(snap.observedTo ?? '');
      setVarietyName(snap.varietyName ?? '');
      setSowingDate(snap.sowingDate ?? '');
      setPhase(snap.phase as Phase);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshList = useCallback(async () => {
    setLoadingList(true);
    setListError('');
    try {
      const res = await listSeasons('untrusted');
      setDrafts(res.seasons);
    } catch (e: unknown) {
      setListError(apiErrorMessage(e, 'تعذّر تحميل المسودّات — تحقّق من تفعيل الميزة والصلاحيّة.'));
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    if (phase === 'list') void refreshList();
  }, [phase, refreshList]);

  // ── بدء تدفّق ترقيم جديد ─────────────────────────────────────────
  const startNew = () => {
    const key = newDraftKey();
    setDraftKey(key);
    setFieldId('');
    setFieldName('');
    setSeasonId('');
    setSeasonLabel('');
    setObservedFrom('');
    setObservedTo('');
    setVarietyName('');
    setSowingDate('');
    setSowingPrecision('day');
    setSeedRate('');
    setNotes('');
    setLogbookFile(null);
    setError('');
    setPhase('draw');
    saveSeasonDraft({ draftKey: key, fieldId: '', fieldName: '', phase: 'draw' });
  };

  const cancelFlow = () => {
    clearSeasonDraft();
    setPhase('list');
  };

  // ── الخطوة ١: رسم الحقل → إنشاؤه عبر مسار المنصّة العامّ (JWT) → التقاط field_id ──
  const handleFieldDrawn = async (data: DrawnField): Promise<void> => {
    const payload = {
      name: data.name,
      crop: data.crop,
      soil_type: data.soil_type,
      manager: data.manager,
      geometry: data.geometry,
      boundary_metadata: data.boundary_metadata ?? undefined,
    };
    // الخطأ يُرمى ليعرضه AddFieldWithMap (لا ابتلاع). النجاح ⇒ التقاط المعرّف والتقدّم.
    const r = await kongApi.post('/api/v1/fields', payload);
    const rec = r.data as Record<string, unknown>;
    const newId = String(rec.field_id ?? rec.id ?? '');
    if (!newId) throw new Error('لم تُعِد الخدمة معرّف الحقل — تعذّر متابعة الترقيم.');
    setFieldId(newId);
    setFieldName(data.name);
    setPhase('details');
    persist({ fieldId: newId, fieldName: data.name, phase: 'details' });
  };

  // ── الخطوة ٢: بيانات الموسم + المحصول → POST مسودّة (idempotent على draft_key) ──
  const submitDetails = async () => {
    if (!observedFrom || !observedTo) {
      setError('حدّد أقدم وأحدث تاريخ في الدفتر (نطاق المشاهدة).');
      return;
    }
    if (observedTo < observedFrom) {
      setError('أحدث تاريخ يجب أن يكون بعد أقدم تاريخ.');
      return;
    }
    if (!varietyName.trim()) {
      setError('اسم الصنف/المحصول مطلوب.');
      return;
    }
    if (!sowingDate) {
      setError('تاريخ البذار مطلوب.');
      return;
    }
    if (sowingDate < observedFrom || sowingDate > observedTo) {
      setError('تاريخ البذار يجب أن يقع ضمن نطاق المشاهدة (من/إلى).');
      return;
    }
    let seedRateVal: number | null = null;
    if (seedRate.trim()) {
      const n = Number(seedRate);
      if (!Number.isFinite(n) || n <= 0) {
        setError('كمية البذور يجب أن تكون رقماً موجباً (أو اتركها فارغة).');
        return;
      }
      seedRateVal = n;
    }
    setSaving(true);
    setError('');
    try {
      const res = await createSeasonDraft({
        field_id: fieldId,
        observed_at_from: observedFrom,
        observed_at_to: observedTo,
        season_label: seasonLabel.trim() || null,
        notes: notes.trim() || null,
        draft_key: draftKey,
        crop: {
          variety_name: varietyName.trim(),
          sowing_date: sowingDate,
          sowing_precision: sowingPrecision,
          seed_rate_kg_ha: seedRateVal,
        },
      });
      setSeasonId(res.season_id);
      setPhase('logbook');
      persist({ seasonId: res.season_id, phase: 'logbook' });
    } catch (e: unknown) {
      setError(apiErrorMessage(e, 'تعذّر حفظ المسودّة — تحقّق من التواريخ والصلاحيّة.'));
    } finally {
      setSaving(false);
    }
  };

  // ── الخطوة ٣: رفع مرفق الدفتر (شرط القبول) ──────────────────────
  const submitLogbook = async () => {
    if (!logbookFile) {
      setError('اختر صورة/ملفّ الدفتر (JPEG أو PNG أو PDF) — المرفق شرط للقبول.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await uploadSeasonLogbook(seasonId, logbookFile);
      setPhase('review');
      persist({ phase: 'review', hasLogbook: true });
    } catch (e: unknown) {
      setError(
        apiErrorMessage(
          e,
          'تعذّر رفع الدفتر — تأكّد أنّه صورة/PDF صالح وأقلّ من الحدّ المسموح.',
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  // ── الخطوة ٤: تسليم للقبول (يضرب مسار القبول المُصدَّق) ──────────
  const submitAccept = async () => {
    setSaving(true);
    setError('');
    try {
      const res = await acceptSeason(seasonId);
      setAcceptedBy(res.accepted_by);
      clearSeasonDraft();
      setPhase('done');
    } catch (e: unknown) {
      setError(
        apiErrorMessage(
          e,
          'تعذّر القبول — يتطلّب دور مالك أو خبير زراعيّ (owner/expert) ومرفق دفتر موجود.',
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  // ═══════════════ العرض ═══════════════
  if (phase === 'draw') {
    return (
      <AddFieldWithMap
        onSave={handleFieldDrawn as (d: unknown) => Promise<void>}
        onCancel={cancelFlow}
      />
    );
  }

  if (phase === 'details') {
    return (
      <StepShell
        title="بيانات الموسم والمحصول"
        subtitle={`الحقل: ${fieldName}`}
        icon={<Sprout className="w-5 h-5" />}
        stepIndex={1}
        stepTotal={4}
        canGoBack={false}
        onBack={() => undefined}
        onNext={submitDetails}
        saving={saving}
        error={error}
        nextLabel="حفظ المسودّة"
      >
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-slate-300 col-span-2">
            وصف الموسم (اختياريّ)
            <input
              value={seasonLabel}
              onChange={(e) => setSeasonLabel(e.target.value)}
              placeholder="شتاء 2022/2023"
              className="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-slate-100 text-sm"
            />
          </label>
          <label className="text-xs text-slate-300">
            أقدم تاريخ في الدفتر
            <input
              type="date"
              value={observedFrom}
              onChange={(e) => setObservedFrom(e.target.value)}
              className="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-slate-100 text-sm"
            />
          </label>
          <label className="text-xs text-slate-300">
            أحدث تاريخ في الدفتر
            <input
              type="date"
              value={observedTo}
              onChange={(e) => setObservedTo(e.target.value)}
              className="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-slate-100 text-sm"
            />
          </label>
          <label className="text-xs text-slate-300 col-span-2">
            الصنف / المحصول
            <input
              value={varietyName}
              onChange={(e) => setVarietyName(e.target.value)}
              placeholder="قمح صلب — بلديّ"
              className="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-slate-100 text-sm"
            />
          </label>
          <label className="text-xs text-slate-300">
            تاريخ البذار
            <input
              type="date"
              value={sowingDate}
              onChange={(e) => setSowingDate(e.target.value)}
              className="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-slate-100 text-sm"
            />
          </label>
          <label className="text-xs text-slate-300">
            دقّة تاريخ البذار
            <select
              value={sowingPrecision}
              onChange={(e) => setSowingPrecision(e.target.value as SowingPrecision)}
              className="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-slate-100 text-sm"
            >
              {SOWING_PRECISION_OPTS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-300">
            كمية البذور (kg/ha، اختياريّة)
            <input
              value={seedRate}
              onChange={(e) => setSeedRate(e.target.value)}
              inputMode="decimal"
              placeholder="—"
              className="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-slate-100 text-sm"
            />
          </label>
          <label className="text-xs text-slate-300 col-span-2">
            ملاحظات (اختياريّة)
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="mt-1 w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-slate-100 text-sm"
            />
          </label>
        </div>
        <p className="text-[11px] text-slate-400">
          المبدأ: لا بيانات مُخترَعة — الحقول الناقصة تبقى فارغة (تُصرَّح <code>null</code>) ولا تُملأ تخميناً.
        </p>
      </StepShell>
    );
  }

  if (phase === 'logbook') {
    return (
      <StepShell
        title="مرفق صفحة الدفتر"
        subtitle="المرفق هو «التوقيع» الوحيد — شرط للقبول"
        icon={<BookImage className="w-5 h-5" />}
        stepIndex={2}
        stepTotal={4}
        canGoBack
        onBack={() => setPhase('details')}
        onNext={submitLogbook}
        saving={saving}
        error={error}
        nextLabel="رفع الدفتر"
      >
        <input
          type="file"
          accept="image/jpeg,image/png,application/pdf"
          onChange={(e) => setLogbookFile(e.target.files?.[0] ?? null)}
          className="w-full text-sm text-slate-200 file:mr-3 file:px-3 file:py-2 file:rounded-lg file:border-0 file:bg-emerald-700 file:text-white"
        />
        {logbookFile && (
          <p className="text-[11px] text-slate-400">
            المُختار: {logbookFile.name} ({Math.round(logbookFile.size / 1024)} ك.ب)
          </p>
        )}
        <p className="text-[11px] text-slate-400">
          الأنواع المقبولة: JPEG / PNG / PDF. الخدمة تفحص محتوى الملفّ فعليّاً (لا الامتداد) وترفض المزوَّر.
        </p>
      </StepShell>
    );
  }

  if (phase === 'review') {
    return (
      <StepShell
        title="مراجعة وتسليم للقبول"
        subtitle={`الموسم: ${seasonLabel || fieldName}`}
        icon={<CheckCircle2 className="w-5 h-5" />}
        stepIndex={3}
        stepTotal={4}
        canGoBack
        onBack={() => setPhase('logbook')}
        onNext={submitAccept}
        saving={saving}
        error={error}
        nextLabel="تسليم للقبول"
      >
        <dl className="text-sm text-slate-200 space-y-1.5">
          <Row k="الحقل" v={fieldName} />
          <Row k="نطاق المشاهدة" v={`${observedFrom} → ${observedTo}`} />
          <Row k="الصنف" v={varietyName} />
          <Row k="البذار" v={`${sowingDate} (${SOWING_PRECISION_OPTS.find((o) => o.value === sowingPrecision)?.label})`} />
          {seedRate.trim() && <Row k="كمية البذور" v={`${seedRate} kg/ha`} />}
          <Row k="مرفق الدفتر" v="مرفوع ✓" />
        </dl>
        <div
          className="flex items-start gap-2 px-3 py-2 rounded-lg text-[11px]"
          style={{ background: '#78350f22', border: '1px solid #f59e0b33', color: '#fbbf24' }}
        >
          <FileWarning className="w-4 h-4 mt-0.5 shrink-0" />
          <span>
            تسجيل الأحداث الزراعيّة والحصاد والتكاليف يأتي في شريحة لاحقة (نقاطها الخلفيّة قيد البناء).
            هذه الشريحة تُرقّم الموسم وترفعه للقبول المُصدَّق.
          </span>
        </div>
        <p className="text-[11px] text-slate-400">
          القبول فعل حسّاس: يتطلّب دور <b>مالك</b> أو <b>خبير زراعيّ</b> (البوّابة توقّع الهويّة والخدمة تتحقّق).
        </p>
      </StepShell>
    );
  }

  if (phase === 'done') {
    return (
      <div className="p-6 max-w-2xl mx-auto" dir="rtl">
        <div
          className="rounded-2xl p-6 text-center"
          style={{ background: '#052e16', border: '1px solid #16a34a55' }}
        >
          <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto mb-3" />
          <h2 className="text-lg font-bold text-emerald-200">تمّ قبول الموسم</h2>
          <p className="text-sm text-slate-300 mt-1">
            الحقل «{fieldName}» — قبِله: {acceptedBy || '—'}
          </p>
          <button
            onClick={() => setPhase('list')}
            className="mt-4 px-5 py-2 rounded-lg text-sm font-semibold text-white"
            style={{ background: '#16a34a' }}
          >
            العودة إلى القائمة
          </button>
        </div>
      </div>
    );
  }

  // ── phase === 'list' ────────────────────────────────────────────
  return (
    <div className="p-6 max-w-3xl mx-auto" dir="rtl">
      <header className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <CalendarRange className="w-6 h-6 text-emerald-400" />
          <div>
            <h1 className="text-lg font-bold text-slate-100">ترقيم المواسم الورقيّة</h1>
            <p className="text-xs text-slate-400">
              رسم الحقل → بيانات الموسم → مرفق الدفتر → تسليم للقبول المُصدَّق
            </p>
          </div>
        </div>
        <button
          onClick={startNew}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white"
          style={{ background: '#16a34a' }}
        >
          <MapPinned className="w-4 h-4" /> ترقيم موسم جديد
        </button>
      </header>

      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold text-slate-300">مسودّات بانتظار القبول</h2>
        <button
          onClick={() => void refreshList()}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loadingList ? 'animate-spin' : ''}`} /> تحديث
        </button>
      </div>

      {listError && (
        <div
          className="px-3 py-2 rounded-lg text-sm mb-3"
          style={{ background: '#450a0a22', border: '1px solid #dc262633', color: '#f87171' }}
        >
          {listError}
        </div>
      )}

      {!listError && drafts.length === 0 && !loadingList && (
        <p className="text-sm text-slate-500 py-6 text-center">
          لا مسودّات بعد — ابدأ ترقيم موسم جديد.
        </p>
      )}

      <ul className="space-y-2">
        {drafts.map((d) => (
          <li
            key={d.id}
            className="flex items-center justify-between px-3 py-2.5 rounded-lg"
            style={{ background: '#1e293b', border: '1px solid #334155' }}
          >
            <div className="text-sm text-slate-200">
              <div className="font-medium">{d.season_label || `موسم ${d.field_id.slice(0, 8)}`}</div>
              <div className="text-[11px] text-slate-400">
                {d.observed_at_from} → {d.observed_at_to}
                {d.has_logbook ? ' · دفتر مرفوع' : ' · بلا دفتر'}
              </div>
            </div>
            <span
              className="text-[11px] px-2 py-0.5 rounded-full"
              style={{ background: '#334155', color: '#cbd5e1' }}
            >
              مسودّة
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-700/50 pb-1">
      <dt className="text-slate-400 text-xs">{k}</dt>
      <dd className="text-slate-100">{v}</dd>
    </div>
  );
}
