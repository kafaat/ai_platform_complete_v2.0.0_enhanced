import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = process.cwd();
const read = (p: string) => readFileSync(join(root, p), 'utf8');
const auth = read('src/hooks/useAuth.ts');
const main = read('src/main.tsx');
const api = read('src/hooks/useApi.ts');
const duck = read('src/services/duckdb.ts');

// Continuation-5 F5-01/F5-05: تبديل المستأجِر/الخروج يجب أن يُفرّغ كاش React Query
// وسياق الحقل ومثيل DuckDB — فلا تبقى بيانات مستأجِرٍ سابق قابلةً للقراءة/التصدير.
describe('F5-01/F5-05 — tenant switch/logout resets all private client state', () => {
  it('main.tsx subscribes to the auth store and clears cache + field context + DuckDB on tenant change', () => {
    expect(main).toContain('useAuthStore.subscribe(');
    expect(main).toContain('queryClient.clear()');
    expect(main).toContain('clearSelectedField()');
    expect(main).toContain('resetDuckDB()');
    // عند فقد الهويّة (خروج) نقطع WebSocket.
    expect(main).toContain('wsService.disconnect()');
  });

  it('duckdb service exposes resetDuckDB that terminates the shared singleton', () => {
    expect(duck).toContain('export async function resetDuckDB');
    expect(duck).toContain('dbPromise = null');
    expect(duck).toContain('.terminate()');
  });
});

// F5-02: مصدر مستأجِر واحد متّسق — login يحمل tenant_id على user، وsetTenant يزامنه،
// فلا تقرأ أيّ hook (user?.tenant_id) مستأجِراً قديماً/'default' بعد دخول أو تبديل.
describe('F5-02 — single consistent active-tenant source', () => {
  it('login attaches tenant_id to the user object', () => {
    const loginBlock = auth.slice(auth.indexOf('login: async'), auth.indexOf('signup: async'));
    expect(loginBlock).toContain('tenant_id: tenantId');
  });

  it('setTenant syncs user.tenant_id with the canonical tenantId', () => {
    const block = auth.slice(auth.indexOf('setTenant: (id: string) => {'), auth.indexOf('refreshUser: async'));
    expect(block).toContain('...u, tenant_id: id');
    expect(block).toContain('set({ tenantId: id, user });');
  });
});

// F5-01/F5-03: مفتاح المهامّ مُنطاق بالمستأجِر، وطفرة الإكمال تُبطِل الاستعلام المشترك.
describe('F5-01/F5-03 — task query is tenant-scoped and invalidated on mutation', () => {
  it('QK.tasks includes the tenant in the key', () => {
    expect(api).toContain("tasks:            (tid: string, fid?: string) => ['tasks', tid, fid ?? 'all']");
  });

  it('useCompleteTask invalidates the tenant-scoped tasks query on success', () => {
    const block = api.slice(api.indexOf('export function useCompleteTask'), api.indexOf('export function useCompleteTask') + 700);
    expect(block).toContain('onSuccess');
    expect(block).toContain("invalidateQueries({ queryKey: ['tasks', tid] })");
  });
});
