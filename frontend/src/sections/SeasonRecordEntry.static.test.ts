// حارس ساكن لصفحة ترقيم المواسم (SEASON-RECORD-ENTRY-01 شريحة 3c).
// يفحص النصّ (لا يُصيّر المكوّن) للتأكّد من الأسلاك الحسّاسة:
//   • تستدعي النقاط الستّ عبر عميل season عبر kongApi على البادئة النسبيّة /api/v1/seasons.
//   • تعيد استخدام مكوّن رسم الحقل + قشرة الخطوات (لا تُعيد اختراعهما).
//   • تستمرّ عبر draft_key (نفس مفتاح تكرار النقطة الخلفيّة).
//   • لا تسرّب المسار الداخليّ /internal/seasons (البوّابة تعيد الكتابة — العميل يجهله).
//   • القبول يمرّ عبر acceptSeason (مسار القبول المُصدَّق) لا نداء يدويّ.
//   • مُسجَّلة في سجلّ المسارات وقائمة صلاحيّات الصفحات (وإلّا لا تُعرَض/لا تُوجَّه).
import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(__dirname, '..');
const pageSrc = fs.readFileSync(path.join(root, 'sections/SeasonRecordEntryPage.tsx'), 'utf8');
const apiSrc = fs.readFileSync(path.join(root, 'services/api/season.ts'), 'utf8');
const storeSrc = fs.readFileSync(path.join(root, 'lib/seasonDraftStorage.ts'), 'utf8');
const routesSrc = fs.readFileSync(path.join(root, 'lib/routes.ts'), 'utf8');
const permsSrc = fs.readFileSync(path.join(root, 'lib/permissions.ts'), 'utf8');
const appSrc = fs.readFileSync(path.join(root, 'App.tsx'), 'utf8');

describe('SeasonRecordEntry — API client wiring', () => {
  it('season client hits the relative /api/v1/seasons prefix via kongApi (nginx-routed)', () => {
    expect(apiSrc).toContain("from './client'");
    expect(apiSrc).toContain("kongApi.post<");
    expect(apiSrc).toMatch(/['"`]\/api\/v1\/seasons/);
  });

  it('season client exposes the ten endpoints (six core + events/harvest/costs/detail)', () => {
    for (const fn of [
      'createSeasonDraft',
      'patchSeasonDraft',
      'uploadSeasonLogbook',
      'getSeasonLogbookUrl',
      'acceptSeason',
      'listSeasons',
      // SEASON-ENTRY-EVENTS-UI (opens SIM-GOLDEN)
      'addSeasonEvent',
      'setSeasonHarvest',
      'addSeasonCost',
      'getSeasonDetail',
    ]) {
      expect(apiSrc).toContain(`export const ${fn}`);
    }
  });

  it('logbook upload sends raw file bytes (not FormData) so magic-byte detection works', () => {
    expect(apiSrc).toContain('/logbook');
    expect(apiSrc).not.toContain('FormData');
  });

  it('the internal path is never referenced from the browser (gateway rewrites it)', () => {
    expect(apiSrc).not.toContain('/internal/seasons');
    expect(pageSrc).not.toContain('/internal/seasons');
  });
});

describe('SeasonRecordEntry — page reuse + flow', () => {
  it('reuses the field-draw component and the step shell (no re-invention)', () => {
    expect(pageSrc).toContain("import AddFieldWithMap from '../components/AddFieldWithMap'");
    expect(pageSrc).toContain("import StepShell from '../components/fieldsetup/StepShell'");
  });

  it('drives the full flow through the season client + submit-for-accept', () => {
    expect(pageSrc).toContain('createSeasonDraft');
    expect(pageSrc).toContain('uploadSeasonLogbook');
    expect(pageSrc).toContain('acceptSeason'); // submit-for-accept hits the attested path
    expect(pageSrc).toContain('listSeasons');
  });

  it('persists a draft across sessions via draft_key', () => {
    expect(pageSrc).toContain("from '../lib/seasonDraftStorage'");
    expect(pageSrc).toContain('draft_key');
    expect(storeSrc).toContain('newDraftKey');
    expect(storeSrc).toContain('localStorage');
  });

  it('surfaces accept 403/401 honestly (owner/expert only) — no silent swallow', () => {
    expect(pageSrc).toContain('apiErrorMessage');
    expect(pageSrc).toMatch(/owner\/expert|مالك|خبير/);
  });
});

describe('SeasonRecordEntry — registration', () => {
  it('is registered in the route registry and lazy-loaded in App', () => {
    expect(routesSrc).toContain("id: 'season-record-entry'");
    expect(appSrc).toContain('SeasonRecordEntryPage');
    expect(appSrc).toContain("case 'season-record-entry'");
  });

  it('is in the RBAC page allow-list (else the guard blocks it)', () => {
    expect(permsSrc).toContain("'season-record-entry'");
  });
});
