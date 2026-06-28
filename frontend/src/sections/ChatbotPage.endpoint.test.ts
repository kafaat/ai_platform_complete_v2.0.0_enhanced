// حارس انحدار: الدردشة يجب أن تستدعي AI Agronomist Runtime الحقيقيّ
// (/api/ai-agronomist/chat)، لا الـproxy المفقود /api/chat ولا مسار الوكيل القديم.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const src = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), 'ChatbotPage.tsx'),
  'utf8',
);

describe('ChatbotPage — نقطة الدردشة', () => {
  it('يستدعي AI Agronomist Runtime /api/ai-agronomist/chat', () => {
    expect(src).toContain("kongApi.post('/api/ai-agronomist/chat'");
  });

  it('لا يستدعي الـproxy المفقود /api/chat ولا مسار /api/agent/query القديم', () => {
    expect(src).not.toContain('/api/chat');
    expect(src).not.toContain("kongApi.post('/api/agent/query'");
  });
});
