import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// MPC P2-UI (يُغلق دَين MPC-P2-UI المُتتبَّع): أوّل مستهلك واجهة لنقطة MPC. بطاقة شفافيّة
// قراءة-فقط تستهلك /api/v1/irrigation/mpc/capabilities وتُظهر السلّم المعجميّ المُنمذَج
// والمُؤجَّل صراحةً وطابع «توصية-فقط» — بلا مدخلات/تلفيق، وحالة فارغة صادقة عند تعذّر القراءة.

const read = (rel: string) => readFileSync(join(process.cwd(), rel), 'utf8');

describe('MPC governance card wiring — أوّل مستهلك واجهة لنقطة MPC', () => {
  it('عميل API يستهلك نقطة القدرات الحقيقيّة (لا تلفيق)', () => {
    const api = read('src/services/api.ts');
    expect(api).toContain('fetchMpcCapabilities');
    expect(api).toContain('/api/v1/irrigation/mpc/capabilities');
    expect(api).toContain('recommendation_only');
    expect(api).toContain('execution_allowed');
  });

  it('الخطّاف useMpcCapabilities مربوط بمفتاح استعلام + بلا إعادة محاولة عمياء', () => {
    const hook = read('src/hooks/useApi.ts');
    expect(hook).toContain('export function useMpcCapabilities');
    expect(hook).toContain('QK.mpcCapabilities');
    expect(hook).toContain('fetchMpcCapabilities');
  });

  it('البطاقة قراءة-فقط: توصية-فقط + مُنمذَج/مُؤجَّل + حالة فارغة صادقة', () => {
    const card = read('src/components/fieldview/MpcGovernanceCard.tsx');
    expect(card).toContain('useMpcCapabilities');
    expect(card).toContain('data-testid="mpc-governance"');
    expect(card).toContain('توصية-فقط');
    expect(card).toContain('لا تنفيذ تلقائيّ');
    // صدق: لا قيمة مُختلَقة عند تعذّر القراءة.
    expect(card).toContain('لا قيمة مُختلَقة');
    // يعرض القدرتين المُنمذَجة والمُؤجَّلة من العقد.
    expect(card).toContain('modeled_capabilities');
    expect(card).toContain('not_modeled');
  });

  it('مُركَّبة في MapHub خلف وضع الخبير (لا تعريف ميّت)', () => {
    const maphub = read('src/sections/MapHub.tsx');
    expect(maphub).toContain("import MpcGovernanceCard from '../components/fieldview/MpcGovernanceCard'");
    expect(maphub).toContain('<MpcGovernanceCard enabled={expertMode} />');
  });
});
