import { useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { RefreshCw, Search, Sprout, Layers, ChevronLeft, Plus } from 'lucide-react';
import { useFields } from '../hooks/useApi';
import { useFieldContextStore } from '../hooks/useFieldContext';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';
import { EmptyState, ErrorState, LoadingState } from '../components/StateViews';
import { toFieldOption } from '../lib/fields';

export function num(v: unknown): number | null {
  // القيم الغائبة (null/undefined) أو السلسلة الفارغة ⇒ null (تُعرَض «—»)، لا صفر.
  // حرج: Number('') يساوي 0 لا NaN، فبدون هذا الحارس يظهر مؤشّر غير متوفّر كـ«0.00»
  // مضلِّلاً (NDVI غير محسوب ≠ NDVI=0). الصفر الحقيقيّ يبقى يُعرَض كما هو.
  if (v == null) return null;
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  const s = String(v).trim();
  if (s === '') return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function text(v: unknown, fallback = '—') {
  const s = String(v ?? '').trim();
  return s || fallback;
}

export default function MyFieldsPage() {
  const { data, isLoading, isError, refetch, isFetching } = useFields();
  const navigate = useNavigate();
  const setSelectedField = useFieldContextStore((s) => s.setSelectedField);
  const { user } = useAuthStore();
  const mutateAllowed = canMutate(user?.role);
  const [q, setQ] = useState('');
  const rawFields = (data?.fields ?? []) as Record<string, unknown>[];
  const fields = useMemo(() => rawFields.map((f) => ({ raw: f, opt: toFieldOption(f as any) })), [rawFields]);
  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return fields;
    return fields.filter(({ raw, opt }) =>
      [opt.name, opt.crop, raw.field_code, raw.region, raw.country]
        .map((x) => String(x ?? '').toLowerCase())
        .some((x) => x.includes(term)),
    );
  }, [fields, q]);

  const totalArea = fields.reduce((s, { raw }) => s + (num(raw.area_ha ?? raw.area) ?? 0), 0);
  const crops = new Set(fields.map(({ opt }) => opt.crop).filter(Boolean)).size;
  const ready = fields.filter(({ raw }) => String(raw.quality_grade ?? '').toUpperCase() === 'READY').length;

  if (isLoading) return <LoadingState message="جارٍ تحميل حقولك…" />;
  if (isError) return <ErrorState title="تعذّر تحميل حقولك" detail="تأكد من الاتصال أو صلاحية الجلسة." onRetry={() => refetch()} />;

  return (
    <div dir="rtl" className="p-4 md:p-6 space-y-4">
      <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 md:p-5">
        <div className="flex flex-col md:flex-row md:items-center gap-3 justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Layers className="w-6 h-6 text-emerald-400" />
              <h1 className="text-xl md:text-2xl font-bold text-slate-100">حقولي</h1>
            </div>
            <p className="text-sm text-slate-400 mt-1">كل الحقول الخاصة بالمستخدم في شاشة واحدة من مصدر الحقول المباشر.</p>
          </div>
          <div className="flex items-center gap-2">
            {mutateAllowed && (
              <button
                onClick={() => navigate('/fields/map-center?add=1')}
                className="inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-white hover:brightness-110"
                style={{ background: '#16a34a' }}
              >
                <Plus className="w-4 h-4" />
                حقل جديد
              </button>
            )}
            <button
              onClick={() => refetch()}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-emerald-900 px-3 py-2 text-sm text-emerald-300 hover:bg-emerald-950/40"
            >
              <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
              تحديث
            </button>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-4">
          <Kpi label="عدد الحقول" value={String(fields.length)} />
          <Kpi label="إجمالي المساحة" value={`${totalArea.toFixed(1)} هـ`} />
          <Kpi label="المحاصيل" value={String(crops)} hint={`جاهز: ${ready}`} />
        </div>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-3 flex items-center gap-2">
        <Search className="w-4 h-4 text-slate-500" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="ابحث باسم الحقل، المحصول، الكود، أو المنطقة…"
          className="w-full bg-transparent outline-none text-slate-100 placeholder:text-slate-500 text-sm"
        />
      </div>

      {fields.length === 0 ? (
        <EmptyState title="لا توجد حقول بعد" hint="أضف الحقول أولاً ليبدأ مسار الموسم والتوصيات." />
      ) : filtered.length === 0 ? (
        <EmptyState title="لا توجد نتائج مطابقة" hint="جرّب كلمة بحث أخرى." />
      ) : (
        <FieldsTable
          rows={filtered}
          onOpen={(fieldId) => {
            // يثبت الحقل النشط في السياق المشترك ثم يفتح النمط الحالي للخريطة/CDSE.
            // MapHub يقرأ selectedFieldId عبر useSelectedField ويعرض بلاطات cdse-tiles
            // ومؤشرات الحقل المختار دون إدخال مسار جديد أو كسر النمط الحالي.
            setSelectedField(fieldId);
            navigate(`/fields/map-center?field_id=${encodeURIComponent(fieldId)}&index=ndvi&source=my-fields&weather=1`, {
              state: { fieldId, openCdse: true, indicator: 'ndvi', from: 'my-fields', showWeather: true },
            });
          }}
        />
      )}
    </div>
  );
}

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="text-lg font-bold text-slate-100 mt-1">{value}</div>
      {hint && <div className="text-xs text-slate-500 mt-1">{hint}</div>}
    </div>
  );
}

function FieldsTable({
  rows,
  onOpen,
}: {
  rows: Array<{ raw: Record<string, unknown>; opt: { id: string; name: string; crop?: string } }>;
  onOpen: (fieldId: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-950/70">
      <div className="hidden md:block overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-900/80 text-slate-400">
            <tr>
              <Th>الحقل</Th>
              <Th>المحصول</Th>
              <Th>المساحة</Th>
              <Th>NDVI</Th>
              <Th>الموقع</Th>
              <Th>الحالة</Th>
              <Th>فتح</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {rows.map(({ raw, opt }) => (
              <FieldRow key={opt.id} raw={raw} opt={opt} onOpen={onOpen} />
            ))}
          </tbody>
        </table>
      </div>

      <div className="md:hidden divide-y divide-slate-800">
        {rows.map(({ raw, opt }) => (
          <FieldMobileRow key={opt.id} raw={raw} opt={opt} onOpen={onOpen} />
        ))}
      </div>
    </div>
  );
}

function Th({ children }: { children: ReactNode }) {
  return <th className="px-4 py-3 text-right font-semibold whitespace-nowrap">{children}</th>;
}

function Td({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <td className={`px-4 py-3 align-middle ${className}`}>{children}</td>;
}

function FieldRow({
  raw,
  opt,
  onOpen,
}: {
  raw: Record<string, unknown>;
  opt: { id: string; name: string; crop?: string };
  onOpen: (fieldId: string) => void;
}) {
  const area = num(raw.area_ha ?? raw.area);
  const ndvi = num(raw.ndvi);
  const quality = text(raw.quality_grade, 'PENDING');
  const health = text(raw.health_summary_ar, 'لا توجد قراءة حديثة');
  const needs = quality !== 'READY';
  return (
    <tr
      role="button"
      tabIndex={0}
      onClick={() => onOpen(opt.id)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onOpen(opt.id); }}
      className="cursor-pointer bg-slate-950/30 hover:bg-emerald-950/20 focus:outline-none focus:bg-emerald-950/30"
      title="فتح خريطة الحقل ومؤشرات CDSE وطبقة الطقس/الرياح"
    >
      <Td>
        <div className="font-bold text-slate-100">{opt.name}</div>
        <div className="text-xs text-slate-500 mt-1">{text(raw.field_code)}</div>
      </Td>
      <Td>
        <span className="inline-flex items-center gap-2 text-slate-300">
          <Sprout className="w-4 h-4 text-emerald-400" />
          {text(opt.crop || raw.crop || raw.crop_ar, 'محصول غير محدد')}
        </span>
      </Td>
      <Td className="text-slate-100 font-semibold whitespace-nowrap">{area != null ? `${area.toFixed(1)} هـ` : '—'}</Td>
      <Td className="text-slate-100 font-semibold whitespace-nowrap">{ndvi != null ? ndvi.toFixed(2) : '—'}</Td>
      <Td className="text-slate-300">{text(raw.region ?? raw.country)}</Td>
      <Td>
        <div className="flex flex-col gap-1">
          <span className={`w-fit text-xs px-2 py-1 rounded-full border ${needs ? 'border-amber-900 text-amber-300 bg-amber-950/30' : 'border-emerald-900 text-emerald-300 bg-emerald-950/30'}`}>
            {quality}
          </span>
          <span className="text-xs text-slate-500 max-w-xs truncate">{health}</span>
        </div>
      </Td>
      <Td>
        <span className="inline-flex items-center gap-1 text-emerald-300 text-xs whitespace-nowrap">
          الخريطة وCDSE والطقس/الرياح
          <ChevronLeft className="w-4 h-4" />
        </span>
      </Td>
    </tr>
  );
}

function FieldMobileRow({
  raw,
  opt,
  onOpen,
}: {
  raw: Record<string, unknown>;
  opt: { id: string; name: string; crop?: string };
  onOpen: (fieldId: string) => void;
}) {
  const area = num(raw.area_ha ?? raw.area);
  const ndvi = num(raw.ndvi);
  const quality = text(raw.quality_grade, 'PENDING');
  const needs = quality !== 'READY';
  return (
    <button
      type="button"
      onClick={() => onOpen(opt.id)}
      className="w-full text-right p-4 hover:bg-emerald-950/20 focus:outline-none focus:bg-emerald-950/30"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-bold text-slate-100 text-lg">{opt.name}</div>
          <div className="text-sm text-slate-400 mt-1 flex items-center gap-2">
            <Sprout className="w-4 h-4" />
            {text(opt.crop || raw.crop || raw.crop_ar, 'محصول غير محدد')}
          </div>
        </div>
        <span className={`text-xs px-2 py-1 rounded-full border ${needs ? 'border-amber-900 text-amber-300 bg-amber-950/30' : 'border-emerald-900 text-emerald-300 bg-emerald-950/30'}`}>
          {quality}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 mt-4 text-sm">
        <Mini label="المساحة" value={area != null ? `${area.toFixed(1)} هـ` : '—'} />
        <Mini label="NDVI" value={ndvi != null ? ndvi.toFixed(2) : '—'} />
        <Mini label="الموقع" value={text(raw.region ?? raw.country)} />
        <Mini label="الكود" value={text(raw.field_code)} />
      </div>
      <div className="mt-3 inline-flex items-center gap-1 text-emerald-300 text-xs">
        فتح الخريطة وCDSE والطقس/الرياح
        <ChevronLeft className="w-4 h-4" />
      </div>
    </button>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-900/70 p-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-slate-100 font-semibold mt-1 truncate">{value}</div>
    </div>
  );
}
