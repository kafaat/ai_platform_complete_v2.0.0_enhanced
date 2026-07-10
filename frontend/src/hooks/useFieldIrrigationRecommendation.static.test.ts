import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

// حارس ثابت (source-scan) على عرف WS-D.2 — لا نُشغّل react-query هنا، بل نثبّت أنّ
// القارئ يستهدف النقطة الصحيحة ويعالج الحالات الثلاث بصدق (مطابقةً لعرف
// useSelectedField.static.test.ts: قراءة المصدر والتأكيد على محتواه).

const root = path.resolve(__dirname, '..');
const hookFile = path.join(root, 'hooks', 'useFieldIrrigationRecommendation.ts');
const cardFile = path.join(root, 'components', 'fieldview', 'IrrigationDecisionCard.tsx');
const mapHubFile = path.join(root, 'sections', 'MapHub.tsx');

const hookSrc = fs.readFileSync(hookFile, 'utf8');
const cardSrc = fs.readFileSync(cardFile, 'utf8');
const mapHubSrc = fs.readFileSync(mapHubFile, 'utf8');

describe('useFieldIrrigationRecommendation — targets the WS-D.2 endpoint', () => {
  it('POSTs to /api/v1/fields/{id}/irrigation-recommendation via the gateway', () => {
    expect(hookSrc).toContain('fields/${encodeURIComponent(fieldId as string)}/irrigation-recommendation');
    expect(hookSrc).toContain('kongApi');
    expect(hookSrc).toContain('.post(');
  });

  it('models the degraded contract as a discriminated union on status', () => {
    expect(hookSrc).toContain("status: 'recommendation_ready'");
    expect(hookSrc).toContain("status: 'insufficient_data'");
    expect(hookSrc).toContain("status: 'inconsistent_state'");
    // الحالتان المتدهورتان يجب ألّا تدّعيا وجود توصية (recommendation: null).
    expect(hookSrc).toMatch(/recommendation:\s*null/);
    // علم عدم المعايرة ثابت من الخادم.
    expect(hookSrc).toContain('calibrated: false');
  });

  it('fires with a fieldId; weather is optional (auto-fetched by the server, WS-D.2c)', () => {
    // بعد D.2c الطقس اختياريّ — الخادم يجلبه آليّاً؛ التفعيل يحتاج fieldId فقط.
    expect(hookSrc).toContain('enabled: enabled && !!fieldId');
    expect(hookSrc).not.toContain('enabled: enabled && !!fieldId && !!weather');
    expect(hookSrc).toContain('retry: false');
  });

  it('models the D.2c/d contract (dependency_unavailable + approval_state)', () => {
    expect(hookSrc).toContain("status: 'dependency_unavailable'");
    expect(hookSrc).toContain('approval_state');
  });
});

describe('IrrigationDecisionCard — honestly handles the three statuses', () => {
  it('uses the hook and renders the candidate ownership note (not an executed task)', () => {
    expect(cardSrc).toContain('useFieldIrrigationRecommendation');
    expect(cardSrc).toContain('توصية مرشَّحة — القرار النهائيّ لخدمة القرار');
    expect(cardSrc).toContain('اروِ');
    expect(cardSrc).toContain('أجّل');
  });

  it('renders degraded states for insufficient_data / inconsistent_state without fabricated numbers', () => {
    expect(cardSrc).toContain("data.status === 'insufficient_data'");
    expect(cardSrc).toContain('بيانات الاستنزاف ناقصة');
    expect(cardSrc).toContain('Dr>TAW');
    // دائماً: غير معايَر يمنيّاً + سرد الحدود.
    expect(cardSrc).toContain('غير معايَر يمنيّاً');
    expect(cardSrc).toContain('data.limitations');
  });

  it('is mounted as a real consumer inside the Field workspace (MapHub)', () => {
    expect(mapHubSrc).toContain("import IrrigationDecisionCard from '../components/fieldview/IrrigationDecisionCard'");
    expect(mapHubSrc).toContain('<IrrigationDecisionCard');
  });
});
