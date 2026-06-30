import { readFileSync } from 'fs';
import { join } from 'path';
import { describe, expect, it } from 'vitest';

const root = process.cwd();
const chatbot = readFileSync(join(root, 'src/sections/ChatbotPage.tsx'), 'utf8');
const router = readFileSync(join(root, '../services/sahool-platform/api/routers/field_ai_context.py'), 'utf8');

describe('Chatbot AI context pack integration', () => {
  it('loads and injects the field AI context pack into chat requests', () => {
    expect(chatbot).toContain('ai-context-pack');
    expect(chatbot).toContain('ai_context_pack: aiContext');
    expect(chatbot).toContain('ai_context_summary_ar');
    expect(chatbot).toContain('سياق الحقل للذكاء');
  });

  it('keeps the context pack endpoint scoped to fields and two-year memory', () => {
    expect(router).toContain('/api/v1/fields/{field_id}/ai-context-pack');
    expect(router).toContain('days: int = Query(730');
    expect(router).toContain('weather_history');
    expect(router).toContain('imagery_timeline');
  });
});
