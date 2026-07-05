import { useState } from 'react';
import {
  Briefcase, BookOpen, ShieldCheck, Store, FileText, Wrench,
  AlertTriangle, Calculator,
} from 'lucide-react';
import { useAuthStore } from '../hooks/useAuth';
import { useSelectedField } from '../hooks/useSelectedField';
import { canManage } from '../lib/permissions';
import { T, toneColors } from '../components/ds';
import {
  costsByFieldTotal, dash, feasibilityTone, fmtNum, readinessSummary,
  roleChangeTone, settingLabel, sharingScopeLabelAr, thirdPartyTypeLabelAr,
  whoCanTone,
  type FeasibilityResult, type FieldCostRow, type RoleChangePreview,
  type SettingRow, type WhoCanResult,
} from '../lib/managerConsole';
import {
  useAutowritePreview, useCostCategories, useCostsByField, useCropClassificationReadiness,
  useCropGap, useDataReadiness, useErpProjection, useFailuresCheck, useFeasibility,
  useGenerateShareKey, useInventoryProjection, usePermissionMatrix, usePreviewRoleChange,
  useProvisionTenant, useReportBuild, useSettings, useSnapshotEvidence, useWhoCan,
  useWorkOrderFromRecommendation,
} from '../hooks/useManagerConsole';

/** كونسول المدير: واجهة موحّدة لنقاط الإدارة اليتيمة (P3) — جدوى اقتصاديّة/تكاليف،
 *  إسقاطات دفتر العمليّات، حوكمة الصلاحيّات (استبطان قراءة فقط)، فجوة السوق، بناء
 *  التقارير، وعمليّات (أمر عمل من توصية/مفتاح مشاركة/إعدادات/قرينة كاميرا/اكتمال
 *  بيانات/فحص فشل). مقصور على owner/manager (canManage) — تلميح صادق؛ الخادم يفرض
 *  الصلاحيّة فعليّاً. 404 ⇒ «غير مُفعَّل» بصدق (لا خطأ مُفزِع). */
export default function ManagerConsolePage() {
  const { user } = useAuthStore();
  const allowed = canManage(user?.role);
  const [tab, setTab] = useState<TabId>('economics');

  if (!allowed) {
    // بوّابة صادقة: لا نعرض بيانات إدارة لغير المالك/المدير (الخادم يردّ 403 أصلاً).
    return (
      <div className="p-4 text-sm" style={{ color: T.muted }}>
        هذه الصفحة مقصورة على المالك/المدير — دورك الحاليّ لا يخوّل كونسول الإدارة.
      </div>
    );
  }

  return (
    <div className="p-4 flex flex-col gap-3" dir="rtl" data-testid="manager-console">
      <h1 className="inline-flex items-center gap-2 text-lg font-bold" style={{ color: T.ink }}>
        <Briefcase className="w-5 h-5 text-emerald-300" aria-hidden="true" /> كونسول المدير
      </h1>

      {/* شريط تبويب — قسم واحد نشط في كلّ مرّة (هوكاته تُستدعى عند تفعيله فقط) */}
      <div className="flex flex-wrap gap-1.5" role="tablist">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(t.id)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[12px] font-semibold"
              style={{
                border: `1px solid ${active ? '#14532d' : T.line}`,
                color: active ? '#86efac' : T.muted,
                background: active ? 'rgba(20,83,45,.25)' : 'rgba(2,6,23,.35)',
              }}
            >
              <Icon className="w-3.5 h-3.5" aria-hidden="true" /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === 'economics' && <EconomicsSection />}
      {tab === 'ledger' && <LedgerSection />}
      {tab === 'rbac' && <RbacSection />}
      {tab === 'market' && <MarketSection />}
      {tab === 'reports' && <ReportsSection />}
      {tab === 'ops' && <OpsSection />}

      <div className="inline-flex items-center gap-1.5 text-[11px]" style={{ color: T.faint }}>
        <AlertTriangle className="w-3.5 h-3.5" aria-hidden="true" />
        القيم من مسارات الإدارة الحيّة — «—» تعني غياب القيمة لا صفراً، و«غير مُفعَّل» تعني ميزة خلف علم/راوتر غير مُركَّب.
      </div>
    </div>
  );
}

type TabId = 'economics' | 'ledger' | 'rbac' | 'market' | 'reports' | 'ops';
const TABS: { id: TabId; label: string; icon: typeof Briefcase }[] = [
  { id: 'economics', label: 'الاقتصاد', icon: Calculator },
  { id: 'ledger', label: 'إسقاطات الدفتر', icon: BookOpen },
  { id: 'rbac', label: 'حوكمة الصلاحيّات', icon: ShieldCheck },
  { id: 'market', label: 'السوق', icon: Store },
  { id: 'reports', label: 'التقارير', icon: FileText },
  { id: 'ops', label: 'العمليّات', icon: Wrench },
];

// ═══ القسم ١: الاقتصاد ═══════════════════════════════════════════════════════
function EconomicsSection() {
  const cats = useCostCategories();
  const costs = useCostsByField();
  const feasM = useFeasibility();
  const [f, setF] = useState({ area_ha: '', yield_t_per_ha: '', price_per_t: '', total_cost: '' });

  const costsData = arr<FieldCostRow>(costs.data);
  const feas = feasM.data as FeasibilityResult | undefined;
  const feasReady = f.area_ha !== '' && f.yield_t_per_ha !== '' && f.price_per_t !== '';

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      <Panel title="جدوى المحصول" icon={Calculator}>
        <Muted>هل سأربح؟ الإيراد − التكاليف = صافي الربح. تقدير إرشادي بمدخلاتك (POST).</Muted>
        <div className="grid grid-cols-2 gap-1.5 mt-1.5">
          <Num label="المساحة (هـ)" v={f.area_ha} on={(v) => setF({ ...f, area_ha: v })} />
          <Num label="الغلّة (طن/هـ)" v={f.yield_t_per_ha} on={(v) => setF({ ...f, yield_t_per_ha: v })} />
          <Num label="السعر (/طن)" v={f.price_per_t} on={(v) => setF({ ...f, price_per_t: v })} />
          <Num label="إجماليّ التكلفة" v={f.total_cost} on={(v) => setF({ ...f, total_cost: v })} />
        </div>
        <button
          type="button"
          disabled={!feasReady || feasM.isPending}
          onClick={() => feasM.mutate({
            area_ha: Number(f.area_ha), yield_t_per_ha: Number(f.yield_t_per_ha),
            price_per_t: Number(f.price_per_t),
            ...(f.total_cost !== '' ? { total_cost: Number(f.total_cost) } : {}),
          })}
          className="mt-2 px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
          style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}
        >
          {feasM.isPending ? 'جارٍ الحساب…' : 'احسب الجدوى'}
        </button>
        {feasM.isError && <Muted>تعذّر الحساب — تحقّق من المدخلات.</Muted>}
        {feas && !feas.disabled && feas.supported !== false && (
          <div className="mt-2 text-[12px] flex flex-col gap-0.5" style={{ color: T.ink }}>
            <ToneChip tone={feasibilityTone(feas)} text={feas.verdict_ar ?? feas.message_ar ?? '—'} />
            <div>الإيراد المتوقّع: <b>{fmtNum(feas.expected_revenue)}</b></div>
            {feas.complete && <div>صافي الربح: <b>{fmtNum(feas.net_profit)}</b> · الهامش: <b>{fmtNum(feas.profit_margin_pct, 1)}٪</b></div>}
          </div>
        )}
        {feas?.disabled && <DisabledNote />}
        {feas && feas.supported === false && <Muted>{dash(feas.message_ar)}</Muted>}
      </Panel>

      <Panel title="بنود التكلفة القياسيّة" icon={BookOpen}>
        {cats.isLoading ? <Muted>جارٍ القراءة…</Muted>
          : isDisabled(cats.data) ? <DisabledNote />
          : cats.data?.categories?.length ? (
            <div className="flex flex-wrap gap-1.5">
              {cats.data.categories.map((c) => (
                <span key={c.key} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.muted }}>{c.name_ar}</span>
              ))}
            </div>
          ) : <Muted>تعذّرت القراءة.</Muted>}
        {cats.data?.note_ar && <div className="text-[10px] mt-1" style={{ color: T.faint }}>{cats.data.note_ar}</div>}
      </Panel>

      <Panel title="التكلفة لكلّ حقل" icon={Briefcase}>
        {costs.isLoading ? <Muted>جارٍ القراءة…</Muted>
          : isDisabled(costs.data) ? <DisabledNote />
          : (
            <>
              <div className="text-[12px]" style={{ color: T.ink }}>الإجماليّ: <b>{fmtNum(costsByFieldTotal(costsData))}</b> · حقول: <b>{costsData.length}</b></div>
              <div className="flex flex-col gap-0.5 mt-1">
                {costsData.slice(0, 6).map((r) => (
                  <div key={r.field_id} className="text-[11px] flex justify-between" style={{ color: T.muted }}>
                    <span>{dash(r.field_id)}</span><b>{fmtNum(r.total_usd)}</b>
                  </div>
                ))}
                {costsData.length === 0 && <Muted>لا تكاليف مُسجَّلة (لا صفوف).</Muted>}
              </div>
            </>
          )}
      </Panel>
    </div>
  );
}

// ═══ القسم ٢: إسقاطات دفتر العمليّات ═════════════════════════════════════════
function LedgerSection() {
  const [seasonId, setSeasonId] = useState('');
  const [applied, setApplied] = useState<string | null>(null);
  const erp = useErpProjection(applied);
  const inv = useInventoryProjection(applied);
  const autoM = useAutowritePreview();
  const [ao, setAo] = useState({ occurred_on: '', operation_type: '' });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-2">
        <Txt label="معرّف الموسم (season_id)" v={seasonId} on={setSeasonId} wide />
        <button
          type="button"
          disabled={!seasonId}
          onClick={() => setApplied(seasonId || null)}
          className="px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
          style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}
        >اعرض الإسقاطات</button>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Panel title="إسقاط ERP (معاينة)" icon={BookOpen}>
          <Muted>إسقاط ماليّ قابل للترحيل لاحقاً — لا يُرسِل شيئاً إلى ERP (synced=false).</Muted>
          {!applied ? <Muted>أدخل معرّف موسم واعرض.</Muted>
            : erp.isLoading ? <Muted>جارٍ القراءة…</Muted>
            : isDisabled(erp.data) ? <DisabledNote />
            : erp.isError ? <Muted>تعذّرت القراءة (تحقّق من ANALYTICS_VIEW).</Muted>
            : <JsonBlock data={erp.data} />}
        </Panel>

        <Panel title="إسقاط المخزون (معاينة)" icon={BookOpen}>
          <Muted>خصم مخزون من سجلات المواد فقط — لا يكتب في inventory-service.</Muted>
          {!applied ? <Muted>أدخل معرّف موسم واعرض.</Muted>
            : inv.isLoading ? <Muted>جارٍ القراءة…</Muted>
            : isDisabled(inv.data) ? <DisabledNote />
            : inv.isError ? <Muted>تعذّرت القراءة (تحقّق من ANALYTICS_VIEW).</Muted>
            : <JsonBlock data={inv.data} />}
        </Panel>

        <Panel title="معاينة الكتابة التلقائيّة" icon={Calculator}>
          <Muted>كيف يتحوّل حدث عمليّة إلى سجلّ رقابي — لا يحفظ شيئاً (would_persist علَم فقط).</Muted>
          <div className="grid grid-cols-2 gap-1.5 mt-1.5">
            <Txt label="تاريخ الحدث (YYYY-MM-DD)" v={ao.occurred_on} on={(v) => setAo({ ...ao, occurred_on: v })} />
            <Txt label="نوع العمليّة" v={ao.operation_type} on={(v) => setAo({ ...ao, operation_type: v })} />
          </div>
          <button
            type="button"
            disabled={!ao.occurred_on || !ao.operation_type || autoM.isPending}
            onClick={() => autoM.mutate({ occurred_on: ao.occurred_on, operation_type: ao.operation_type })}
            className="mt-2 px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
            style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}
          >{autoM.isPending ? 'جارٍ…' : 'عايِن'}</button>
          {autoM.isError && <Muted>تعذّرت المعاينة.</Muted>}
          {autoM.data && (isDisabled(autoM.data) ? <DisabledNote /> : <JsonBlock data={autoM.data} />)}
        </Panel>
      </div>
    </div>
  );
}

// ═══ القسم ٣: حوكمة الصلاحيّات (استبطان قراءة فقط) ════════════════════════════
function RbacSection() {
  const matrix = usePermissionMatrix();
  const [perm, setPerm] = useState('');
  const [permApplied, setPermApplied] = useState<string | null>(null);
  const whoCan = useWhoCan(permApplied);
  const [roles, setRoles] = useState({ current_role: 'worker', new_role: 'manager' });
  const preview = usePreviewRoleChange(roles.current_role, roles.new_role);
  const who = whoCan.data as WhoCanResult | undefined;
  const prev = preview.data as RoleChangePreview | undefined;

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      <Panel title="مصفوفة الصلاحيّات" icon={ShieldCheck}>
        <Muted>كلّ دور × كلّ صلاحيّة — شفافيّة الحوكمة (AUDIT_VIEW).</Muted>
        {matrix.isLoading ? <Muted>جارٍ القراءة…</Muted>
          : isDisabled(matrix.data) ? <DisabledNote />
          : matrix.isError ? <Muted>تعذّرت القراءة (تحقّق من AUDIT_VIEW).</Muted>
          : matrix.data ? (
            <>
              <div className="text-[12px]" style={{ color: T.ink }}>
                أدوار: <b>{arrLen(matrix.data.roles)}</b> · صلاحيّات: <b>{dash(matrix.data.total_permissions as number)}</b> · حرجة: <b>{arrLen(matrix.data.safety_critical_permissions)}</b>
              </div>
              <JsonBlock data={matrix.data.matrix} />
            </>
          ) : <Muted>تعذّرت القراءة.</Muted>}
      </Panel>

      <Panel title="من يقدر على صلاحيّة؟" icon={ShieldCheck}>
        <Muted>الاستعلام العكسي الأمنيّ — أدخل رمز الصلاحيّة (مثل PESTICIDE_APPROVE).</Muted>
        <div className="flex items-end gap-1.5 mt-1.5">
          <Txt label="الصلاحيّة" v={perm} on={setPerm} wide />
          <button type="button" disabled={!perm} onClick={() => setPermApplied(perm || null)}
            className="px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
            style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}>استعلم</button>
        </div>
        {permApplied && (whoCan.isLoading ? <Muted>جارٍ القراءة…</Muted>
          : isDisabled(who) ? <DisabledNote />
          : whoCan.isError ? <Muted>تعذّرت القراءة (422 لصلاحيّة مجهولة).</Muted>
          : who ? (
            <div className="mt-1.5 text-[12px]" style={{ color: T.ink }}>
              <ToneChip tone={whoCanTone(who)} text={who.is_safety_critical ? 'حرجة (سلامة)' : 'عاديّة'} />
              <div className="mt-0.5">الأدوار: <b>{(who.roles_with_permission ?? []).join('، ') || '—'}</b></div>
              {who.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{who.note_ar}</div>}
            </div>
          ) : null)}
      </Panel>

      <Panel title="معاينة تغيير الدور" icon={ShieldCheck}>
        <Muted>ما يُكتسَب/يُفقَد قبل التطبيق — لا يُطبّق شيئاً (USER_CHANGE_ROLE).</Muted>
        <div className="grid grid-cols-2 gap-1.5 mt-1.5">
          <Sel label="من دور" v={roles.current_role} on={(v) => setRoles({ ...roles, current_role: v })} opts={ROLE_OPTS} />
          <Sel label="إلى دور" v={roles.new_role} on={(v) => setRoles({ ...roles, new_role: v })} opts={ROLE_OPTS} />
        </div>
        {preview.isLoading ? <Muted>جارٍ القراءة…</Muted>
          : isDisabled(prev) ? <DisabledNote />
          : preview.isError ? <Muted>تعذّرت القراءة.</Muted>
          : prev ? (
            <div className="mt-1.5 text-[12px]" style={{ color: T.ink }}>
              {prev.error_ar ? <ToneChip tone="danger" text={prev.error_ar} /> : (
                <>
                  <ToneChip tone={roleChangeTone(prev)} text={prev.warning_ar ?? '—'} />
                  <div className="mt-0.5">مكتسَبة: <b>{dash(prev.gained_count)}</b> · مفقودة: <b>{dash(prev.lost_count)}</b></div>
                </>
              )}
            </div>
          ) : null}
      </Panel>
    </div>
  );
}
const ROLE_OPTS = ['owner', 'manager', 'agronomist', 'worker', 'viewer'];

// ═══ القسم ٤: السوق ═════════════════════════════════════════════════════════
function MarketSection() {
  const [zone, setZone] = useState('');
  const [applied, setApplied] = useState<string | null>(null);
  const gap = useCropGap(applied);
  const readiness = useCropClassificationReadiness(applied);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-2">
        <Txt label="مفتاح المنطقة (zone_key)" v={zone} on={setZone} wide />
        <button type="button" disabled={!zone} onClick={() => setApplied(zone || null)}
          className="px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
          style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}>حلّل المنطقة</button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <Panel title="فجوة السوق وتركّز المحاصيل" icon={Store}>
          <Muted>تشبّع/فرص من حقول المنصّة المشتركة — اتجاه نسبيّ لا سعر (RECOMMENDATION_VIEW).</Muted>
          {!applied ? <Muted>أدخل مفتاح منطقة.</Muted>
            : gap.isLoading ? <Muted>جارٍ القراءة…</Muted>
            : isDisabled(gap.data) ? <DisabledNote />
            : gap.isError ? <Muted>تعذّرت القراءة.</Muted>
            : <JsonBlock data={gap.data} />}
        </Panel>
        <Panel title="جاهزيّة تصنيف المحاصيل" icon={Store}>
          <Muted>عيّنات التدريب المتاحة (محصول معروف + حدود GPS) — البوّابة نحو فجوة أشمل.</Muted>
          {!applied ? <Muted>أدخل مفتاح منطقة.</Muted>
            : readiness.isLoading ? <Muted>جارٍ القراءة…</Muted>
            : isDisabled(readiness.data) ? <DisabledNote />
            : readiness.isError ? <Muted>تعذّرت القراءة.</Muted>
            : <JsonBlock data={readiness.data} />}
        </Panel>
      </div>
    </div>
  );
}

// ═══ القسم ٥: التقارير ═══════════════════════════════════════════════════════
function ReportsSection() {
  const buildM = useReportBuild();
  const { options: fieldOptions, isLoading: fieldsLoading, isError: fieldsError, fieldId: activeFieldId, setFieldId: setActiveFieldId } = useSelectedField();
  const [r, setR] = useState({ title: '', field_ids: activeFieldId ?? '', format: 'csv' });
  const spec = buildM.data;

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Panel title="بناء مواصفة تقرير" icon={FileText}>
        <Muted>يبني مواصفة مُتحقَّقاً منها من اختيارك — المواصفة فقط لا بيانات مُجمَّعة (FIELD_VIEW).</Muted>
        <div className="flex flex-col gap-1.5 mt-1.5">
          <Txt label="العنوان" v={r.title} on={(v) => setR({ ...r, title: v })} wide />
          {fieldWrap('الحقول', (
            <select
              multiple
              value={r.field_ids.split(',').map((x) => x.trim()).filter(Boolean)}
              disabled={fieldsLoading || fieldsError || fieldOptions.length === 0}
              onChange={(e) => {
                const ids = Array.from(e.currentTarget.selectedOptions).map((o) => o.value).filter(Boolean);
                const first = ids[0];
                if (first) setActiveFieldId(first, { source: 'user' });
                setR({ ...r, field_ids: ids.join(',') });
              }}
              className="rounded-lg px-2 py-1 text-[12px] min-h-[4.5rem] disabled:opacity-60"
              style={inputStyle}
            >
              {fieldOptions.map((f) => <option key={f.id} value={f.id}>{f.name}{f.crop && f.crop !== '—' ? ` · ${f.crop}` : ''}</option>)}
            </select>
          ), true)}
          <Sel label="الصيغة" v={r.format} on={(v) => setR({ ...r, format: v })} opts={['csv', 'json', 'pdf']} />
        </div>
        <button
          type="button"
          disabled={buildM.isPending}
          onClick={() => buildM.mutate({
            title: r.title || undefined,
            field_ids: r.field_ids.split(',').map((s) => s.trim()).filter(Boolean),
            format: r.format,
          })}
          className="mt-2 px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
          style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}
        >{buildM.isPending ? 'جارٍ البناء…' : 'ابنِ المواصفة'}</button>
        {buildM.isError && <Muted>تعذّر البناء (422 لاختيار غير صالح بنيويّاً).</Muted>}
      </Panel>

      <Panel title="نتيجة المواصفة" icon={FileText}>
        {!spec ? <Muted>ابنِ مواصفة لعرض النتيجة.</Muted>
          : isDisabled(spec) ? <DisabledNote />
          : (
            <>
              <div className="text-[12px]" style={{ color: T.ink }}>
                حقول محلولة: <b>{arrLen(spec.resolved_fields)}</b> · تحذيرات: <b>{arrLen(spec.warnings)}</b>
              </div>
              {arr<string>(spec.warnings).map((w, i) => (
                <div key={i} className="text-[11px]" style={{ color: '#fdba74' }}>⚠ {w}</div>
              ))}
              <JsonBlock data={spec.spec} />
            </>
          )}
      </Panel>
    </div>
  );
}

// ═══ القسم ٦: العمليّات ══════════════════════════════════════════════════════
function OpsSection() {
  const { options: fieldOptions, isLoading: fieldsLoading, isError: fieldsError, fieldId: activeFieldId, setFieldId: setActiveFieldId } = useSelectedField();
  const managerFieldSelect = (value: string, onChange: (v: string) => void, label = 'الحقل') => fieldWrap(label, (
    <select
      value={value}
      disabled={fieldsLoading || fieldsError || fieldOptions.length === 0}
      onChange={(e) => { const v = e.target.value; onChange(v); if (v) setActiveFieldId(v, { source: 'user' }); }}
      className="rounded-lg px-2 py-1 text-[12px] disabled:opacity-60"
      style={inputStyle}
    >
      <option value="">اختر الحقل</option>
      {fieldOptions.map((f) => <option key={f.id} value={f.id}>{f.name}{f.crop && f.crop !== '—' ? ` · ${f.crop}` : ''}</option>)}
    </select>
  ));
  const woM = useWorkOrderFromRecommendation();
  const keyM = useGenerateShareKey();
  const snapM = useSnapshotEvidence();
  const readyM = useDataReadiness();
  const failM = useFailuresCheck();
  const tenantM = useProvisionTenant();
  const [tenant, setTenant] = useState({ owner_email: '', owner_full_name: '', tenant_name: '' });
  const [settingsScope, setSettingsScope] = useState('');
  const settings = useSettings(settingsScope || null);
  const settingsData = arr<SettingRow>(settings.data);

  const [wo, setWo] = useState({ field_id: activeFieldId ?? '', recommendation: '{}' });
  const [key, setKey] = useState({ scope: 'read', third_party_name: '', third_party_type: '', expires_in_days: '30' });
  const [snap, setSnap] = useState({ snapshot_id: '', camera_id: '', field_id: activeFieldId ?? '', media_uri: '', captured_at: '' });
  const [ready, setReady] = useState('');
  const [fail, setFail] = useState({ cloud_pct: '', days_since_observation: '', weather_hours_since_update: '' });
  const keyData = keyM.data as Record<string, unknown> | undefined;

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {/* أمر عمل من توصية — كتابة فعليّة (persist-first ثمّ حدث) */}
      <Panel title="أمر عمل من توصية" icon={Wrench}>
        <Muted>يحوّل توصية إلى أمر عمل (FOES) ويُثبّته — persisted=true فقط عند إدراج صفّ.</Muted>
        <div className="flex flex-col gap-1.5 mt-1.5">
          {managerFieldSelect(wo.field_id, (v) => setWo({ ...wo, field_id: v }), 'الحقل')}
          <Area label="التوصية (JSON)" v={wo.recommendation} on={(v) => setWo({ ...wo, recommendation: v })} />
        </div>
        <button type="button" disabled={!wo.field_id || woM.isPending}
          onClick={() => woM.mutate({ field_id: wo.field_id, recommendation: parseJson(wo.recommendation) })}
          className="mt-2 px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
          style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}>{woM.isPending ? 'جارٍ…' : 'أنشئ أمر العمل'}</button>
        {woM.isError && <Muted>تعذّر الإنشاء.</Muted>}
        {woM.data && (isDisabled(woM.data) ? <DisabledNote /> : <JsonBlock data={woM.data} />)}
      </Panel>

      {/* مفتاح مشاركة — يُعرَض الـplaintext مرّة واحدة */}
      <Panel title="توليد مفتاح مشاركة" icon={ShieldCheck}>
        <Muted>يُعرَض المفتاح مرّة واحدة فقط — الحفظ في DB يحتاج تفعيل الخادم (USER_INVITE).</Muted>
        <div className="grid grid-cols-2 gap-1.5 mt-1.5">
          <Sel label="النطاق" v={key.scope} on={(v) => setKey({ ...key, scope: v })} opts={['read', 'read_write']} />
          <Num label="صلاحيّة (أيّام)" v={key.expires_in_days} on={(v) => setKey({ ...key, expires_in_days: v })} />
          <Txt label="اسم الطرف" v={key.third_party_name} on={(v) => setKey({ ...key, third_party_name: v })} />
          <Sel label="نوع الطرف" v={key.third_party_type} on={(v) => setKey({ ...key, third_party_type: v })} opts={['', 'advisor', 'dealer', 'ministry', 'researcher', 'other']} />
        </div>
        <button type="button" disabled={keyM.isPending}
          onClick={() => keyM.mutate({
            scope: key.scope,
            third_party_name: key.third_party_name || undefined,
            third_party_type: key.third_party_type || undefined,
            expires_in_days: Number(key.expires_in_days) || 30,
          })}
          className="mt-2 px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
          style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}>{keyM.isPending ? 'جارٍ…' : 'ولّد المفتاح'}</button>
        {keyM.isError && <Muted>تعذّر التوليد (422 لنطاق/نوع غير صالح).</Muted>}
        {keyData && !isDisabled(keyData) && (
          <div className="mt-1.5 text-[11px] flex flex-col gap-0.5" style={{ color: T.ink }}>
            <div>المفتاح: <b className="break-all" style={{ color: '#fbbf24' }}>{dash(keyData.key_plaintext as string)}</b></div>
            <div>النطاق: <b>{sharingScopeLabelAr(keyData.scope as string)}</b> · النوع: <b>{thirdPartyTypeLabelAr(keyData.third_party_type as string | null)}</b></div>
            <div style={{ color: T.faint }}>{dash(keyData.note_ar as string)}</div>
          </div>
        )}
        {keyData && isDisabled(keyData) && <DisabledNote />}
      </Panel>

      {/* تهيئة مستأجِر جديد — إعداد B2B (admin المنصّة فقط عبر /auth/tenants) */}
      <Panel title="تهيئة مستأجِر جديد" icon={ShieldCheck}>
        <Muted>يُنشئ مؤسّسة جديدة + أوّل مالك (الدور owner يُفرَض خادميّاً). لا كلمة مرور هنا —
          يُصدَر رابط إعادة تعيين يضبط به المالك كلمته. يتطلّب دور admin المنصّة (403 لغيره).</Muted>
        <div className="flex flex-col gap-1.5 mt-1.5">
          <Txt label="بريد المالك" v={tenant.owner_email} on={(v) => setTenant({ ...tenant, owner_email: v })} wide />
          <Txt label="اسم المالك" v={tenant.owner_full_name} on={(v) => setTenant({ ...tenant, owner_full_name: v })} wide />
          <Txt label="اسم المؤسّسة (اختياريّ)" v={tenant.tenant_name} on={(v) => setTenant({ ...tenant, tenant_name: v })} wide />
        </div>
        <button type="button"
          disabled={!tenant.owner_email.trim() || tenant.owner_full_name.trim().length < 2 || tenantM.isPending}
          onClick={() => tenantM.mutate({
            owner_email: tenant.owner_email.trim(),
            owner_full_name: tenant.owner_full_name.trim(),
            ...(tenant.tenant_name.trim() ? { tenant_name: tenant.tenant_name.trim() } : {}),
          })}
          className="mt-2 px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
          style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}>
          {tenantM.isPending ? 'جارٍ…' : 'هيّئ المستأجِر'}
        </button>
        {tenantM.isError && <Muted>تعذّرت التهيئة — قد تحتاج دور admin أو البريد مسجّل مسبقاً (409).</Muted>}
        {tenantM.data && (
          <div className="mt-1.5 text-[11px] flex flex-col gap-0.5" style={{ color: T.muted }}>
            <div>أُنشئ المالك: <b style={{ color: T.ink }}>{tenantM.data.email}</b> · الدور {tenantM.data.role}</div>
            {tenantM.data.reset_url && (
              <div>رابط ضبط كلمة المرور (يُعرَض مرّة): <span style={{ color: '#86efac', direction: 'ltr' }}>{tenantM.data.reset_url}</span></div>
            )}
          </div>
        )}
      </Panel>

      {/* الإعدادات (قراءة) */}
      <Panel title="إعدادات المستأجِر" icon={Wrench}>
        <Muted>القيم المحفوظة (SETTINGS_VIEW) — الكتابة عبر PUT (SETTINGS_MANAGE).</Muted>
        <Sel label="النطاق (تصفية)" v={settingsScope} on={setSettingsScope} opts={['', 'platform', 'farm', 'irrigation', 'notification']} />
        {settings.isLoading ? <Muted>جارٍ القراءة…</Muted>
          : isDisabled(settings.data) ? <DisabledNote />
          : (
            <div className="flex flex-col gap-0.5 mt-1">
              {settingsData.map((s) => (
                <div key={s.setting_id} className="text-[11px]" style={{ color: T.muted }}>{settingLabel(s)}</div>
              ))}
              {settingsData.length === 0 && <Muted>لا إعدادات محفوظة.</Muted>}
            </div>
          )}
      </Panel>

      {/* قرينة كاميرا */}
      <Panel title="قرينة لقطة كاميرا" icon={Wrench}>
        <Muted>يحوّل لقطة إلى قرينة ميدانيّة (وزن منخفض) — لا تشخيص آليّ (DEVICE_MANAGE).</Muted>
        <div className="grid grid-cols-2 gap-1.5 mt-1.5">
          <Txt label="معرّف اللقطة" v={snap.snapshot_id} on={(v) => setSnap({ ...snap, snapshot_id: v })} />
          <Txt label="معرّف الكاميرا" v={snap.camera_id} on={(v) => setSnap({ ...snap, camera_id: v })} />
          {managerFieldSelect(snap.field_id, (v) => setSnap({ ...snap, field_id: v }), 'الحقل')}
          <Txt label="وقت الالتقاط (ISO)" v={snap.captured_at} on={(v) => setSnap({ ...snap, captured_at: v })} />
          <Txt label="رابط الوسائط" v={snap.media_uri} on={(v) => setSnap({ ...snap, media_uri: v })} wide />
        </div>
        <button type="button" disabled={!snap.snapshot_id || !snap.camera_id || !snap.field_id || !snap.media_uri || !snap.captured_at || snapM.isPending}
          onClick={() => snapM.mutate({ ...snap })}
          className="mt-2 px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
          style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}>{snapM.isPending ? 'جارٍ…' : 'اربط كقرينة'}</button>
        {snapM.isError && <Muted>تعذّر الربط.</Muted>}
        {snapM.data && (isDisabled(snapM.data) ? <DisabledNote /> : <JsonBlock data={snapM.data} />)}
      </Panel>

      {/* اكتمال البيانات */}
      <Panel title="اكتمال البيانات" icon={Calculator}>
        <Muted>ما المتاح الآن، ما المحجوب، وما التالي الأعلى أثراً — أدخل الحقول المتوفّرة.</Muted>
        <Txt label="الحقول المتوفّرة (مفصولة بفاصلة)" v={ready} on={setReady} wide />
        <button type="button" disabled={!ready.trim() || readyM.isPending}
          onClick={() => readyM.mutate({ provided_fields: ready.split(',').map((s) => s.trim()).filter(Boolean) })}
          className="mt-2 px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
          style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}>{readyM.isPending ? 'جارٍ…' : 'قيّم'}</button>
        {readyM.isError && <Muted>تعذّر التقييم.</Muted>}
        {readyM.data && !isDisabled(readyM.data) && (
          <div className="mt-1.5 text-[12px]" style={{ color: T.ink }}>
            {(() => { const s = readinessSummary(readyM.data); return <>أعلى مستوى: <b>{s.level}</b> · متاح: <b>{s.available}</b> · محجوب: <b>{s.blocked}</b></>; })()}
          </div>
        )}
        {readyM.data && isDisabled(readyM.data) && <DisabledNote />}
      </Panel>

      {/* فحص الفشل */}
      <Panel title="فحص أنماط الفشل" icon={AlertTriangle}>
        <Muted>يفحص السحب/الطقس القديم/التربة — أدخل ما توفّر (كلّه اختياريّ).</Muted>
        <div className="grid grid-cols-2 gap-1.5 mt-1.5">
          <Num label="سحابة ٪" v={fail.cloud_pct} on={(v) => setFail({ ...fail, cloud_pct: v })} />
          <Num label="أيّام منذ الرصد" v={fail.days_since_observation} on={(v) => setFail({ ...fail, days_since_observation: v })} />
          <Num label="ساعات منذ تحديث الطقس" v={fail.weather_hours_since_update} on={(v) => setFail({ ...fail, weather_hours_since_update: v })} />
        </div>
        <button type="button" disabled={failM.isPending}
          onClick={() => failM.mutate({
            cloud_pct: numOrNull(fail.cloud_pct),
            days_since_observation: numOrNull(fail.days_since_observation),
            weather_hours_since_update: numOrNull(fail.weather_hours_since_update),
          })}
          className="mt-2 px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
          style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}>{failM.isPending ? 'جارٍ…' : 'افحص'}</button>
        {failM.isError && <Muted>تعذّر الفحص.</Muted>}
        {failM.data && !isDisabled(failM.data) && (
          <div className="mt-1.5 text-[12px]" style={{ color: T.ink }}>حالات فشل مكتشَفة: <b>{dash(failM.data.count as number)}</b></div>
        )}
        {failM.data && isDisabled(failM.data) && <DisabledNote />}
      </Panel>
    </div>
  );
}

// ═══ مساعِدات عرض مشتركة (تعكس نمط AdminRuntimePage) ═════════════════════════

function Panel({ title, icon: Icon, children }: { title: string; icon: typeof Briefcase; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
      <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
        <Icon className="w-4 h-4 text-emerald-300" aria-hidden="true" /> {title}
      </div>
      <div className="flex flex-col gap-0.5">{children}</div>
    </section>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <div className="text-[11px]" style={{ color: T.muted }}>{children}</div>;
}

/** حالة «غير مُفعَّل» صادقة (404 ⇒ ميزة خلف علم/راوتر غير مُركَّب) — لا خطأ مُفزِع. */
function DisabledNote() {
  return <div className="text-[11px]" style={{ color: '#fdba74' }}>غير مُفعَّل — الميزة خلف علم أو الراوتر غير مُركَّب على الخادم.</div>;
}

/** وسم نغمة مُلوَّن (يعتمد toneColors من ds؛ المجهول محايد). */
function ToneChip({ tone, text }: { tone: ReturnType<typeof feasibilityTone>; text: string }) {
  const c = toneColors(tone);
  return <span className="inline-block text-[11px] px-2 py-0.5 rounded-full font-semibold" style={{ color: c.fg, background: c.bg }}>{text}</span>;
}

function JsonBlock({ data }: { data: unknown }) {
  return <pre className="text-[10px] mt-1 overflow-x-auto" style={{ color: T.faint }}>{JSON.stringify(data, null, 1)}</pre>;
}

// حقول إدخال بسيطة بنمط داكن موحَّد
const inputStyle: React.CSSProperties = { border: `1px solid ${T.line}`, background: 'rgba(15,23,42,.45)', color: T.ink };
function fieldWrap(label: string, node: React.ReactNode, wide?: boolean) {
  return (
    <label className={`flex flex-col gap-0.5 text-[10px] ${wide ? 'col-span-2' : ''}`} style={{ color: T.faint }}>
      {label}
      {node}
    </label>
  );
}
function Txt({ label, v, on, wide }: { label: string; v: string; on: (v: string) => void; wide?: boolean }) {
  return fieldWrap(label, <input type="text" value={v} onChange={(e) => on(e.target.value)} className="rounded-lg px-2 py-1 text-[12px]" style={inputStyle} />, wide);
}
function Num({ label, v, on }: { label: string; v: string; on: (v: string) => void }) {
  return fieldWrap(label, <input type="number" value={v} onChange={(e) => on(e.target.value)} className="rounded-lg px-2 py-1 text-[12px]" style={inputStyle} />);
}
function Area({ label, v, on }: { label: string; v: string; on: (v: string) => void }) {
  return fieldWrap(label, <textarea rows={3} value={v} onChange={(e) => on(e.target.value)} className="rounded-lg px-2 py-1 text-[11px] font-mono" style={inputStyle} />, true);
}
function Sel({ label, v, on, opts }: { label: string; v: string; on: (v: string) => void; opts: string[] }) {
  return fieldWrap(label, (
    <select value={v} onChange={(e) => on(e.target.value)} className="rounded-lg px-2 py-1 text-[12px]" style={inputStyle}>
      {opts.map((o) => <option key={o} value={o}>{o === '' ? '—' : o}</option>)}
    </select>
  ));
}

// ── مساعِدات نقيّة صغيرة (محليّة للعرض) ──
function isDisabled(v: unknown): boolean {
  return !!v && typeof v === 'object' && (v as { disabled?: boolean }).disabled === true;
}
/** يُرجِع مصفوفة آمنة من بيانات قد تكون {disabled} أو غير مصفوفة. */
function arr<T>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : [];
}
function arrLen(v: unknown): number {
  return Array.isArray(v) ? v.length : 0;
}
function parseJson(s: string): Record<string, unknown> {
  try { const o = JSON.parse(s); return o && typeof o === 'object' ? o : {}; } catch { return {}; }
}
function numOrNull(s: string): number | null {
  return s.trim() === '' ? null : Number(s);
}
