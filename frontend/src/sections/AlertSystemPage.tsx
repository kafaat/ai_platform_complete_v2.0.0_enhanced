// ═══════════════════════════════════════════════════════════════
// SAHOOL — AlertSystemPage (مربوط ببيانات حيّة)
// كان يعرض INITIAL_ALERTS ثابتة. الآن: تنبيهات حيّة من useAlerts (/v1/alerts)،
// إقرار يُثبَّت على الخادم (useAcknowledgeAlert) تفاؤليّاً، حالات موحّدة
// (StateViews)، وأزرار محكومة بالدور (RBAC: المُشاهِد لا يُقِرّ/يحذف).
// ═══════════════════════════════════════════════════════════════
import { useState, type CSSProperties } from 'react';
import { FixedSizeList, type ListChildComponentProps } from 'react-window';
import { CheckCircle, AlertTriangle, AlertOctagon, Info, Check, X, Zap, Play } from 'lucide-react';
import { useAlerts, useAcknowledgeAlert, useEvaluateAlerts, useRunAllAlerts } from '../hooks/useApi';
import { useFieldOptions } from '../hooks/useFieldOptions';
import type { AlertRecord } from '../services/api';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';

type Severity = 'critical' | 'high' | 'medium' | 'low';

// أسماء أنواع التنبيهات (v36) بالعربيّة — للعرض حين لا يُرسَل عنوان.
const TYPE_LABELS: Record<string, string> = {
  low_moisture: 'رطوبة منخفضة',
  heavy_rain:   'أمطار غزيرة',
  disease_risk: 'خطر مرض',
  heat_stress:  'إجهاد حراريّ',
  frost_risk:   'خطر صقيع',
  other:        'تنبيه',
};

const SEVERITY_CONFIG: Record<Severity, { label: string; icon: typeof Info; color: string; bg: string; border: string }> = {
  critical: { label: 'حرج',   icon: AlertOctagon,  color: '#dc2626', bg: '#1a0000', border: '#dc262633' },
  high:     { label: 'عالي',  icon: AlertTriangle, color: '#f97316', bg: '#1a0800', border: '#f9731633' },
  medium:   { label: 'متوسط', icon: AlertTriangle, color: '#f59e0b', bg: '#1a1000', border: '#f59e0b33' },
  low:      { label: 'منخفض', icon: Info,          color: '#38bdf8', bg: '#00101a', border: '#38bdf833' },
};

const SEV_MAP: Record<string, Severity> = {
  critical: 'critical', high: 'high', warning: 'medium', medium: 'medium', low: 'low', info: 'low',
};
const normSev = (s?: string): Severity => SEV_MAP[(s ?? '').toLowerCase()] ?? 'low';

// تفتراض القائمة (react-window): قوائم قصيرة تُعرَض كما هي (لا تغيير سلوك للحالة
// الشائعة)؛ الأطول من العتبة تُفترَض لتفادي إثقال DOM على الأجهزة الضعيفة (سياق
// سهول). ROW_H ثابت ⇒ تُحدَّد رسالة البطاقة بسطرين (line-clamp) ليطابق كلّ صفّ.
const VIRTUALIZE_THRESHOLD = 30;
const ROW_GAP = 12; // مطابِق لـ space-y-3
const ROW_H = 116; // ارتفاع الصفّ الثابت (بطاقة ~104 + فجوة)
const _CLAMP2: CSSProperties = {
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical',
  overflow: 'hidden',
};

function relTime(ts?: string): string {
  if (!ts) return '';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return '';
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return 'الآن';
  if (mins < 60) return `منذ ${mins} دقيقة`;
  const h = Math.round(mins / 60);
  if (h < 24) return `منذ ${h} ساعة`;
  return `منذ ${Math.round(h / 24)} يوم`;
}

export function AlertSystemPage() {
  const { user } = useAuthStore();
  const mutateAllowed = canMutate(user?.role);
  const { data, isLoading, isError, refetch } = useAlerts();
  const ackMut = useAcknowledgeAlert();
  const evalMut = useEvaluateAlerts();
  const runAllMut = useRunAllAlerts();
  const { options: fieldOptions } = useFieldOptions();

  const [filter, setFilter] = useState<string>('all');
  const [showAcknowledged, setShowAcknowledged] = useState(false);
  const [ackIds, setAckIds] = useState<Set<string>>(new Set());
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());
  const [evalFieldId, setEvalFieldId] = useState<string>('');
  const [evalNote, setEvalNote] = useState<string>('');
  const [runAllNote, setRunAllNote] = useState<string>('');

  // قائمة الحقول لمنتقي التقييم — مُطبَّعة عبر useFieldOptions (مصدر واحد).
  const runEvaluate = () => {
    if (!mutateAllowed || !evalFieldId || evalMut.isPending) return;
    setEvalNote('');
    evalMut.mutate(evalFieldId, {
      onSuccess: (res) => {
        const c = res.created.length;
        const s = res.skipped_existing;
        setEvalNote(
          c === 0 && s === 0
            ? 'لا تنبيهات جديدة — ظروف الحقل ضمن الحدود الطبيعيّة.'
            : `أُنشئ ${c} تنبيه${s > 0 ? ` (مع تجاوز ${s} موجوداً مسبقاً)` : ''}.`
        );
        refetch();
      },
      onError: () => {
        setEvalNote('تعذّر التقييم — قد يكون الطقس أو الخدمة غير متاح حاليّاً. حاول لاحقاً.');
      },
    });
  };

  const runAll = () => {
    if (!mutateAllowed || runAllMut.isPending) return;
    setRunAllNote('');
    runAllMut.mutate(undefined, {
      onSuccess: (res) => {
        const parts = [
          `فُحص ${res.fields_total} حقل`,
          `أُنشئ ${res.created_total} تنبيه`,
        ];
        if (res.skipped_total > 0) parts.push(`تجاوز ${res.skipped_total} موجوداً`);
        if (res.fields_failed > 0) parts.push(`تعذّر ${res.fields_failed} حقل`);
        setRunAllNote(parts.join(' · ') + '.');
        refetch();
      },
      onError: () => {
        setRunAllNote('تعذّر تشغيل التقييم لكلّ الحقول — قد تكون الخدمة غير متاحة. حاول لاحقاً.');
      },
    });
  };

  // useAlerts ترجع AlertRecord[] مباشرةً من sahool-platform (v36) — لا { alerts }.
  const apiAlerts: AlertRecord[] = data ?? [];

  const alerts = apiAlerts
    .map((a, i) => ({ a, id: String(a.alert_id ?? i) }))
    .filter(({ id }) => !dismissedIds.has(id))
    .map(({ a, id }) => ({
      id,
      severity: normSev(a.severity),
      title: (a.title_ar || TYPE_LABELS[a.alert_type] || 'تنبيه').toString(),
      message: (a.message_ar || '').toString(),
      field: (a.field_id || '').toString(),
      time: relTime(a.created_at ?? undefined),
      // ندمج حالة الخادم (status) مع إقرار الجلسة التفاؤليّ (وإلّا ظهر المُقَرّ كغير مُقَرّ).
      acknowledged: ackIds.has(id) || a.status === 'acknowledged' || a.status === 'resolved',
    }));

  const filtered = alerts.filter(a =>
    (filter === 'all' || a.severity === filter) &&
    (showAcknowledged || !a.acknowledged)
  );

  const acknowledge = (id: string) => {
    if (!mutateAllowed) return;
    setAckIds(prev => new Set(prev).add(id)); // تفاؤليّ
    ackMut.mutate(id);                          // تثبيت على الخادم (best-effort)
  };
  const dismiss = (id: string) => {
    if (!mutateAllowed) return;
    setDismissedIds(prev => new Set(prev).add(id));
  };

  const counts: Record<Severity, number> = { critical: 0, high: 0, medium: 0, low: 0 };
  alerts.filter(a => !a.acknowledged).forEach(a => { counts[a.severity]++; });
  const activeCount = alerts.filter(a => !a.acknowledged).length;

  if (isLoading) return <LoadingState message="جارٍ تحميل التنبيهات…" />;
  if (isError) return <ErrorState title="تعذّر تحميل التنبيهات" onRetry={() => refetch()} />;

  // بطاقة التنبيه — مُستخرَجة كي يتشاركها المسارُ المسطّح (قوائم قصيرة) والمُفترَض
  // (react-window). clamp=true في المسار المُفترَض يحدّ الرسالة بسطرين فيثبُت الارتفاع.
  const renderAlertCard = (a: (typeof filtered)[number], clamp: boolean) => {
    const cfg = SEVERITY_CONFIG[a.severity];
    const Icon = cfg.icon;
    return (
      <div className="rounded-xl p-4 border transition-all"
        style={{
          background: a.acknowledged ? '#1e293b' : cfg.bg,
          borderColor: a.acknowledged ? '#334155' : cfg.border,
          opacity: a.acknowledged ? 0.6 : 1,
          ...(clamp ? { height: ROW_H - ROW_GAP, overflow: 'hidden' } : {}),
        }}>
        <div className="flex items-start gap-3">
          <Icon className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: cfg.color }} aria-hidden="true" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-semibold text-slate-100 text-sm">{a.title}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: `${cfg.color}22`, color: cfg.color }}>{cfg.label}</span>
              {a.acknowledged && <span className="text-[10px] text-emerald-500">✓ مُعترف بها</span>}
            </div>
            {a.message && <p className="text-xs text-slate-300 mb-2" style={clamp ? _CLAMP2 : undefined}>{a.message}</p>}
            <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
              {a.field && <span>📍 {a.field}</span>}
              {a.time && <span>⏱ {a.time}</span>}
            </div>
          </div>
          {mutateAllowed && !a.acknowledged && (
            <div className="flex gap-1.5">
              <button onClick={() => acknowledge(a.id)} title="إقرار"
                className="p-1.5 rounded-lg hover:bg-emerald-950 text-slate-400 hover:text-emerald-400 transition-colors">
                <Check className="w-4 h-4" />
              </button>
              <button onClick={() => dismiss(a.id)} title="إخفاء"
                className="p-1.5 rounded-lg hover:bg-red-950 text-slate-400 hover:text-red-400 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100">نظام التنبيهات</h2>
          <p className="text-sm text-slate-400">{activeCount} تنبيه نشط</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
          <input type="checkbox" checked={showAcknowledged} onChange={e => setShowAcknowledged(e.target.checked)}
            className="w-4 h-4 accent-emerald-500" />
          عرض المُعترف بها
        </label>
      </div>

      {/* تقييم تلقائيّ: يُولّد تنبيهات من ظروف الحقل الحيّة (FIELD_EDIT فقط) */}
      {mutateAllowed && (
        <div className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }}>
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-4 h-4 text-amber-400" />
            <span className="text-sm font-semibold text-slate-200">تقييم تلقائيّ للتنبيهات</span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={evalFieldId}
              onChange={e => { setEvalFieldId(e.target.value); setEvalNote(''); }}
              className="flex-1 min-w-[180px] rounded-lg px-3 py-2 text-sm text-slate-200 bg-slate-800 border border-slate-700"
            >
              <option value="">— اختر حقلاً —</option>
              {fieldOptions.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
            <button
              onClick={runEvaluate}
              disabled={!evalFieldId || evalMut.isPending}
              className="flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold text-slate-900 bg-amber-400 hover:bg-amber-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Zap className="w-4 h-4" />
              {evalMut.isPending ? 'جارٍ التقييم…' : 'تقييم التنبيهات الآن'}
            </button>
          </div>
          {fieldOptions.length === 0 && (
            <p className="text-[11px] text-slate-500 mt-2">لا حقول متاحة — أضِف حقلاً من «إدارة الحقول» أوّلاً.</p>
          )}
          {evalNote && (
            <p className="text-xs mt-2" style={{ color: evalMut.isError ? '#f87171' : '#34d399' }}>{evalNote}</p>
          )}

          {/* تشغيل دفعيّ: تقييم تنبيهات كلّ الحقول دفعةً (نفس مسار الجدولة الدوريّة) */}
          <div className="mt-3 pt-3 border-t" style={{ borderColor: '#334155' }}>
            <button
              onClick={runAll}
              disabled={runAllMut.isPending || fieldOptions.length === 0}
              className="flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold text-slate-100 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Play className="w-4 h-4" />
              {runAllMut.isPending ? 'جارٍ التقييم لكلّ الحقول…' : 'تشغيل تقييم التنبيهات لكلّ الحقول'}
            </button>
            {runAllNote && (
              <p className="text-xs mt-2" style={{ color: runAllMut.isError ? '#f87171' : '#34d399' }}>{runAllNote}</p>
            )}
          </div>
        </div>
      )}

      {/* Severity summary */}
      <div className="grid grid-cols-4 gap-3">
        {(Object.entries(SEVERITY_CONFIG) as [Severity, (typeof SEVERITY_CONFIG)[Severity]][]).map(([key, cfg]) => {
          const Icon = cfg.icon;
          return (
            <button key={key} onClick={() => setFilter(filter === key ? 'all' : key)}
              className="rounded-xl p-3 border text-center transition-all hover:scale-[1.02]"
              style={{ background: filter === key ? cfg.bg : '#1e293b', borderColor: filter === key ? cfg.color : '#334155' }}>
              <Icon className="w-5 h-5 mx-auto mb-1" style={{ color: cfg.color }} />
              <div className="text-xl font-bold" style={{ color: cfg.color }}>{counts[key]}</div>
              <div className="text-[10px] text-slate-400">{cfg.label}</div>
            </button>
          );
        })}
      </div>

      {/* Alert list — مسطّح للقوائم القصيرة، مُفترَض (react-window) للطويلة */}
      {filtered.length === 0 ? (
        <EmptyState
          icon={<CheckCircle className="w-10 h-10 text-emerald-700" />}
          title="لا توجد تنبيهات نشطة 🎉"
          hint={apiAlerts.length === 0 ? 'لا تنبيهات واردة من الخدمة حاليّاً' : undefined}
        />
      ) : filtered.length <= VIRTUALIZE_THRESHOLD ? (
        <div className="space-y-3">
          {filtered.map(a => <div key={a.id}>{renderAlertCard(a, false)}</div>)}
        </div>
      ) : (
        <FixedSizeList
          height={Math.min(filtered.length * ROW_H, 640)}
          itemCount={filtered.length}
          itemSize={ROW_H}
          width="100%"
        >
          {({ index, style }: ListChildComponentProps) => {
            const a = filtered[index];
            return (
              <div style={style} key={a.id}>
                <div style={{ paddingBottom: ROW_GAP }}>{renderAlertCard(a, true)}</div>
              </div>
            );
          }}
        </FixedSizeList>
      )}
    </div>
  );
}
export default AlertSystemPage;
