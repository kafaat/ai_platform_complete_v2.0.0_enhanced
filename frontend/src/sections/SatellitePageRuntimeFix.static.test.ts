import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// نمط قراءة المصدر المعتمَد في المستودع (resolve(__dirname) بدل new URL(import.meta.url)
// الذي يفشل في vitest بـ«URL must be of scheme file»).
const hooks = readFileSync(resolve(__dirname, '../hooks/useApi.ts'), 'utf8');
const api = readFileSync(resolve(__dirname, '../services/api.ts'), 'utf8');

describe('Satellite runtime fixes', () => {
  it('تحليل الآن يستخدم imagery refresh القانوني لا vegetation /v1/analyze بمعرّف fld_*', () => {
    const m = hooks.match(/export function useAnalyzeVegetation\(\)[\s\S]*?\n}\n/);
    expect(m?.[0]).toContain('refreshFieldImagery(fieldId');
    expect(m?.[0]).not.toContain("vegetationApi.get('/v1/analyze'");
  });

  it('401 من خدمة ميزة لا يطرد المستخدم إلى تسجيل الدخول؛ الخروج القسري محصور في auth', () => {
    expect(api).toContain('const isAuthEndpoint');
    expect(api).toContain("url.startsWith('/auth/')");
    expect(api).toContain('if (isAuthEndpoint');
  });
});
