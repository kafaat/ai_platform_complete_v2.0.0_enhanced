// ═══════════════════════════════════════════════════════════════
// SAHOOL — الإعداد (Setup Cabin) · وجهة «الإعداد» في القشرة الموحّدة
// ───────────────────────────────────────────────────────────────
// نظرة عامّة موحّدة (قراءة فقط) على تهيئة المزرعة: المزرعة + الحقول + المعدّات +
// الأجهزة + الدور والوصول + التفضيلات. تملأ آخر وجهة «قيد الإنشاء» في القشرة
// الموحّدة (UnifiedCabin). تجسيد UI_DESIGN_SPEC_UNIFIED.md (وجهة الإعداد).
//
// صدق البيانات: كلّ الأرقام من المصادر الحقيقيّة — المزارع من useFarms، الحقول
// من useSelectedField، المعدّات من useEquipment، الأجهزة من useDevices، والدور من
// useAuthStore. لا تلفيق: غياب القيمة يُعرَض «—»/«غير متاح»/«لا بيانات» صراحةً.
// الحالات (تحميل/خطأ/فراغ) صريحة لكلّ قسم. هذه نظرة عامّة للقراءة فقط — التعديل
// يبقى في الأقسام الكلاسيكيّة (إدارة الحقول/المعدّات/الأجهزة/الإعدادات).
// ═══════════════════════════════════════════════════════════════
import { useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  Sprout, MapPinned, Tractor, Cpu, ShieldCheck, SlidersHorizontal, Globe, Map as MapIcon, Wrench, Plus,
} from 'lucide-react';
import { useFarms, useEquipment, useDevices, QK } from '../hooks/useApi';
import { useSelectedField } from '../hooks/useSelectedField';
import { useAuthStore, UNAUTH_TENANT_KEY } from '../hooks/useAuth';
import { ROLE_LABEL_AR, normalizeRole, canAccess, canMutate, type Role } from '../lib/permissions';
import { kongApi, type FieldImportInput } from '../services/api';
import { loadSettings } from '../lib/appSettings';
import { toastStore } from '../services/websocket';
import FieldSetupWizard from '../components/fieldsetup/FieldSetupWizard';
import type { PageId } from '../App';
import {
  T, Card, Pill, Badge, SectionLabel, Row, StatGrid,
  FieldCabin, equipStatusAr, equipStatusTone, Button,
} from '../components/ds';

// رقم محلّيّ بالعربيّة أو «—» إن غاب — لا تلفيق صفر لقيمة غير متاحة.
const fmtArea = (n?: number | null) =>
  typeof n === 'number' && Number.isFinite(n) && n > 0 ? `${n.toLocaleString('ar')} هـ` : '—';

// قائمة معرّفات الصفحات الكاملة (لحساب عدد الصفحات المتاحة للدور). نشتقّها من
// الاتّحاد عبر تعداد صريح — لا انعكاس على النوع وقت التشغيل. مصدر واحد للحقيقة:
// permissions.canAccess هو الحَكَم؛ هنا فقط نُعدّ كم منها يُسمَح به للدور الحاليّ.
const ALL_PAGE_IDS: PageId[] = [
  'dashboard', 'unified-cabin', 'command', 'map-center', 'tasks-cabin', 'rec-flow',
  'hybrid-monitor', 'analyze-cabin', 'setup-cabin', 'field-app', 'hybrid-index', 'satellite',
  'fields', 'recommendations', 'irrigation', 'weather-advice', 'irrigation-ops',
  'pest-escalation', 'field-intelligence', 'spatial-indicators', 'devices', 'inventory',
  'equipment', 'tasks', 'activities', 'analytics', 'alerts', 'reports', 'master-data',
  'documents', 'governance', 'chatbot', 'settings',
];

// قراءة تفضيلات العميل المحفوظة محلّيّاً عبر الوحدة المُشترَكة lib/appSettings —
// نفس مفتاح SettingsPage ومنطقه الدفاعيّ. قراءة فقط هنا (SettingsPage هو الكاتب).

function idempotencyConfig(source: Record<string, unknown> | null | undefined) {
  const key = source?.idempotency_key;
  return key ? { headers: { 'Idempotency-Key': String(key) } } : undefined;
}

function withoutIdempotency<T extends Record<string, unknown>>(source: T): Omit<T, 'idempotency_key'> {
  const { idempotency_key: _idempotencyKey, ...body } = source;
  return body;
}

const LANG_AR: Record<string, string> = { ar: 'العربيّة', en: 'الإنجليزيّة' };
const MAP_AR: Record<string, string> = { satellite: 'قمر صناعيّ', street: 'شوارع', terrain: 'تضاريس' };

export default function SetupCabin() {
  const farmsQ = useFarms();
  const fieldsQ = useSelectedField();
  const equipQ = useEquipment();
  const devicesQ = useDevices();

  const farms = Array.isArray(farmsQ.data) ? farmsQ.data : [];
  const fields = fieldsQ.options;
  const equipment = Array.isArray(equipQ.data) ? equipQ.data : [];
  const devices = Array.isArray(devicesQ.data) ? devicesQ.data : [];

  const onlineDevices = devices.filter((d) => d.online).length;
  // المعدّات «تحتاج صيانة» من مصدر النغمة الموحّد (status.ts) لا قائمة محلّيّة.
  const needsService = equipment.filter((e) => ['warn', 'danger'].includes(equipStatusTone(e.status)));

  // الدور الحاليّ من المتجر — نُطبّعه ونحسب عدد الصفحات المتاحة عبر canAccess.
  const userRole = useAuthStore((s) => s.user?.role);
  const role: Role = normalizeRole(userRole);
  const accessibleCount = useMemo(
    () => ALL_PAGE_IDS.filter((p) => canAccess(userRole, p)).length,
    [userRole],
  );

  const prefs = useMemo(loadSettings, []);
  const langLabel = prefs.lang ? (LANG_AR[prefs.lang] ?? prefs.lang) : null;
  const mapLabel = prefs.map ? (MAP_AR[prefs.map] ?? prefs.map) : null;

  // ── إنشاء حقل جديد: نقطة دخول للمعالج المتسلسل القائم (FieldSetupWizard) ──
  // تفتح نفس المعالج الذي تستخدمه صفحة «إدارة الحقول» — لا تدفّق مكرّر. التعديل
  // محكوم بالدور (canMutate). المعالجات تعكس FieldManagementPage حرفيّاً:
  // POST /api/v1/fields للإنشاء و/fields/import للاستيراد، وتُرجِع سجلّ الخادم
  // كي يلتقط المعالج field_id. لا تلفيق ولا مسار حفظ جديد.
  const mutateAllowed = canMutate(userRole);
  const qc = useQueryClient();
  const tid = useAuthStore((s) => s.user)?.tenant_id ?? UNAUTH_TENANT_KEY;
  const [showWizard, setShowWizard] = useState(false);

  // بعد الإنشاء/الاستيراد نُبطِل كاش قائمة الحقول كي تُعيد SetupCabin الجلب
  // (useSelectedField يلفّ useFields ويربطه بسياق FieldView المشترك).
  const invalidateFields = () => qc.invalidateQueries({ queryKey: QK.fields(tid) });

  const handleWizardSaveField = async (data: any): Promise<Record<string, unknown>> => {
    const fieldPayload = {
      name: data.name, crop: data.crop,
      soil_type: data.soil_type ?? data.soil,
      manager: data.manager,
      field_code: data.field_code ?? null,
      water_source: data.water_source ?? null,
      irrigation_type: data.irrigation_type ?? null,
      pivot: data.pivot ?? null,
      ownership_type: data.ownership_type ?? null,
      country: data.country ?? null,
      region: data.region ?? null,
      geometry: data.geometry,
      idempotency_key: data.idempotency_key,
    };
    const r = await kongApi.post('/api/v1/fields', withoutIdempotency(fieldPayload), idempotencyConfig(fieldPayload));
    const rec = r.data as Record<string, unknown>;
    invalidateFields();
    toastStore.add('success', '✅ تم إضافة الحقل', `${data.name}`);
    return rec;
  };

  const handleWizardImportField = async (payload: FieldImportInput): Promise<Record<string, unknown>> => {
    const r = await kongApi.post('/api/v1/fields/import', withoutIdempotency(payload as unknown as Record<string, unknown>), idempotencyConfig(payload as unknown as Record<string, unknown>));
    const rec = r.data as Record<string, unknown>;
    invalidateFields();
    toastStore.add('success', '✅ تم استيراد الحقل', `${payload.name}`);
    return rec;
  };

  const handleWizardComplete = () => {
    setShowWizard(false);
    invalidateFields();
  };

  return (
    <FieldCabin
      eyebrow="الإعداد"
      title="إعداد المزرعة"
      subtitle="نظرة عامّة على التهيئة — مزرعة وحقول ومعدّات وأجهزة ووصول"
      headerRight={
        <Pill tone="info" icon={<SlidersHorizontal style={{ width: 12, height: 12 }} />}>
          {fields.length} حقل
        </Pill>
      }
      note={
        <>
          نظرة عامّة موحّدة (قراءة فقط) لتهيئة المزرعة — أرقام حقيقيّة من
          <code> /farms</code> و<code>/fields</code> و<code>/equipment</code> و<code>/devices</code>.
          التعديل يجري في الأقسام الكلاسيكيّة (إدارة الحقول/المعدّات/الأجهزة/الإعدادات) — لا نعرض
          هنا تحريراً مزيّفاً.
        </>
      }
    >
      {/* ── المزرعة ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={
            <Badge tone={farmsQ.isLoading ? 'neutral' : farmsQ.isError ? 'danger' : 'ok'}>
              {farmsQ.isLoading ? 'تحميل…' : farmsQ.isError ? 'خطأ' : `${farms.length} مزرعة`}
            </Badge>
          }
        >
          المزرعة
        </SectionLabel>
        {farmsQ.isLoading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل المزارع…</div>
        ) : farmsQ.isError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل المزارع.</div>
        ) : farms.length === 0 ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا مزارع مُسجّلة.</div>
        ) : (
          farms.map((f) => (
            <Row
              key={f.farm_id}
              icon={<Sprout style={{ width: 16, height: 16, color: T.green }} />}
              label={f.name || 'مزرعة'}
              value={
                <span className="inline-flex items-center gap-2">
                  <span style={{ fontSize: 11, color: T.muted }}>{f.location || '—'}</span>
                  <b style={{ color: T.ink, fontSize: 12 }}>{fmtArea(f.area_ha)}</b>
                </span>
              }
            />
          ))
        )}
      </Card>

      {/* ── الحقول ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={
            <span className="inline-flex items-center gap-1" style={{ color: T.muted, fontSize: 11 }}>
              <MapPinned style={{ width: 12, height: 12 }} /> {fields.length} حقل
            </span>
          }
        >
          الحقول
        </SectionLabel>
        {/* نقطة دخول بارزة: تفتح نفس معالج التهيئة المتسلسل (FieldSetupWizard) */}
        {mutateAllowed && (
          <div style={{ marginBottom: 10 }}>
            <Button
              onClick={() => setShowWizard(true)}
              full={false}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 14px', fontSize: 13 }}
            >
              <Plus style={{ width: 14, height: 14 }} /> إنشاء حقل جديد
            </Button>
          </div>
        )}
        {fieldsQ.isLoading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل الحقول…</div>
        ) : fieldsQ.isError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل الحقول.</div>
        ) : fields.length === 0 ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا حقول مُسجّلة.</div>
        ) : (
          <>
            <StatGrid
              cols={2}
              items={[
                { label: 'عدد الحقول', value: fields.length, icon: <MapPinned style={{ width: 16, height: 16, color: T.green }} /> },
                {
                  label: 'إجماليّ المساحة', value: fmtArea(fields.reduce((s, f) => s + (f.area || 0), 0) || null),
                  color: T.ink, icon: <Sprout style={{ width: 16, height: 16, color: T.green }} />,
                },
              ]}
            />
            <div style={{ marginTop: 8 }}>
              {fields.map((f) => (
                <Row
                  key={f.id}
                  icon={<MapPinned style={{ width: 14, height: 14, color: T.green }} />}
                  label={f.name}
                  value={
                    <span className="inline-flex items-center gap-2">
                      <span style={{ fontSize: 11, color: T.muted }}>{f.crop || '—'}</span>
                      <b style={{ color: T.ink, fontSize: 12 }}>{fmtArea(f.area || null)}</b>
                    </span>
                  }
                />
              ))}
            </div>
          </>
        )}
      </Card>

      {/* ── المعدّات ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={
            <Badge tone={equipQ.isLoading ? 'neutral' : equipQ.isError ? 'danger' : needsService.length ? 'warn' : 'ok'}>
              {equipQ.isLoading ? 'تحميل…' : equipQ.isError ? 'خطأ'
                : needsService.length ? `${needsService.length} تحتاج صيانة` : `${equipment.length} جاهزة`}
            </Badge>
          }
        >
          المعدّات
        </SectionLabel>
        {equipQ.isLoading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل المعدّات…</div>
        ) : equipQ.isError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل المعدّات.</div>
        ) : equipment.length === 0 ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا معدّات مُسجّلة.</div>
        ) : (
          <>
            <StatGrid
              cols={2}
              items={[
                { label: 'إجماليّ', value: equipment.length, icon: <Tractor style={{ width: 16, height: 16, color: T.brownSoft }} /> },
                {
                  label: 'تحتاج صيانة', value: needsService.length,
                  color: needsService.length ? T.warn : T.ok,
                  icon: <Wrench style={{ width: 16, height: 16, color: needsService.length ? T.warn : T.ok }} />,
                },
              ]}
            />
            <div style={{ marginTop: 8 }}>
              {equipment.map((e, i) => (
                <Row
                  key={e.equipment_id || i}
                  icon={<Tractor style={{ width: 16, height: 16, color: T.brownSoft }} />}
                  label={e.name || 'معدّة'}
                  value={<Pill tone={equipStatusTone(e.status)}>{equipStatusAr(e.status)}</Pill>}
                />
              ))}
            </div>
          </>
        )}
      </Card>

      {/* ── الأجهزة (IoT) ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={
            <span className="inline-flex items-center gap-1" style={{ color: T.muted, fontSize: 11 }}>
              <Cpu style={{ width: 12, height: 12 }} /> {devices.length} جهاز
            </span>
          }
        >
          الأجهزة
        </SectionLabel>
        {devicesQ.isLoading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل الأجهزة…</div>
        ) : devicesQ.isError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل الأجهزة.</div>
        ) : devices.length === 0 ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا أجهزة مُسجّلة.</div>
        ) : (
          <StatGrid
            cols={2}
            items={[
              { label: 'متّصلة', value: onlineDevices, color: onlineDevices ? T.ok : T.faint, icon: <Cpu style={{ width: 16, height: 16, color: onlineDevices ? T.ok : T.faint }} /> },
              { label: 'الإجماليّ', value: devices.length, color: T.ink, icon: <Cpu style={{ width: 16, height: 16, color: T.muted }} /> },
            ]}
          />
        )}
      </Card>

      {/* ── الدور والوصول ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={
            <span className="inline-flex items-center gap-1" style={{ color: T.muted, fontSize: 11 }}>
              <ShieldCheck style={{ width: 12, height: 12 }} /> الصلاحيّات
            </span>
          }
        >
          الدور والوصول
        </SectionLabel>
        <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
          <span style={{ fontSize: 13, color: T.ink, fontWeight: 600 }}>الدور الحاليّ</span>
          <Pill tone="info">{ROLE_LABEL_AR[role]}</Pill>
        </div>
        <Row
          icon={<ShieldCheck style={{ width: 16, height: 16, color: T.green }} />}
          label="الصفحات المتاحة لهذا الدور"
          value={<b style={{ color: T.ink }}>{accessibleCount} صفحة</b>}
        />
      </Card>

      {/* ── التفضيلات (محلّيّة، قراءة فقط) ── */}
      <Card pad={14}>
        <SectionLabel
          action={
            <span className="inline-flex items-center gap-1" style={{ color: T.muted, fontSize: 11 }}>
              <SlidersHorizontal style={{ width: 12, height: 12 }} /> محلّيّة
            </span>
          }
        >
          التفضيلات
        </SectionLabel>
        {!langLabel && !mapLabel ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>
            لا تفضيلات محفوظة بعد — تُضبَط في قسم «الإعدادات».
          </div>
        ) : (
          <div className="flex items-center" style={{ gap: 8, flexWrap: 'wrap' }}>
            <Pill tone="neutral" icon={<Globe style={{ width: 12, height: 12 }} />}>
              اللغة: {langLabel ?? '—'}
            </Pill>
            <Pill tone="neutral" icon={<MapIcon style={{ width: 12, height: 12 }} />}>
              الخريطة: {mapLabel ?? '—'}
            </Pill>
          </div>
        )}
      </Card>

      {/* معالج تهيئة الحقل المتسلسل — نفس المعالج المستخدم في «إدارة الحقول» */}
      {showWizard && (
        <FieldSetupWizard
          onSaveField={handleWizardSaveField}
          onImportField={handleWizardImportField}
          onComplete={handleWizardComplete}
          onCancel={() => setShowWizard(false)}
        />
      )}
    </FieldCabin>
  );
}
