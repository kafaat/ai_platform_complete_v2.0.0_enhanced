// حارس انحدار: الدردشة يجب أن تستدعي وكيل المنصّة الحقيقيّ (/api/agent/query)
// لا الـproxy المفقود /api/chat (الذي كان يردّ 404 دائماً — لا route في nginx ولا router).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const src = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), 'ChatbotPage.tsx'),
  'utf8',
);

describe('ChatbotPage — نقطة الدردشة', () => {
  it('يستدعي وكيل المنصّة /api/agent/query', () => {
    expect(src).toContain("kongApi.post('/api/agent/query'");
  });

  it('لا يستدعي الـproxy المفقود /api/chat', () => {
    expect(src).not.toContain('/api/chat');
  });
});
