import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// حارس ساكن: بطاقة الأصناف (أوّل مستهلك واجهيّ لكتالوج PR #627) موصولة كاملةً —
// عميل API + صفحة + توجيه + صلاحيّة — وتُبرِز بوّابة الحوكمة reference_only_not_operational.
const root = process.cwd();
const api = readFileSync(join(root, 'src/services/api.ts'), 'utf8');
const page = readFileSync(join(root, 'src/sections/VarietyCatalogPage.tsx'), 'utf8');
const app = readFileSync(join(root, 'src/App.tsx'), 'utf8');
const routes = readFileSync(join(root, 'src/lib/routes.ts'), 'utf8');
const perms = readFileSync(join(root, 'src/lib/permissions.ts'), 'utf8');

describe('Variety catalog UI wiring (PR #627 follow-up)', () => {
  it('has API clients hitting the governed reference endpoints', () => {
    expect(api).toContain("kongApi\n    .get('/api/v1/varieties/food-grains'");
    expect(api).toContain('/api/v1/varieties/food-grains/${encodeURIComponent(varietyId)}');
    expect(api).toContain('reference_only_not_operational');
  });

  it('surfaces the reference-only governance gate and honest quality issues in the page', () => {
    expect(page).toContain('data-testid="variety-governance-badge"');
    expect(page).toContain('data-testid="variety-quality-issues"');
    expect(page).toContain('reference_only_not_operational');
  });

  it('is fully routed and permission-registered (no orphan page)', () => {
    expect(app).toContain("case 'varieties': return <VarietyCatalogPage />");
    expect(app).toContain("import('./sections/VarietyCatalogPage')");
    expect(routes).toContain("id: 'varieties'");
    expect(perms).toContain("'varieties'");
  });
});
