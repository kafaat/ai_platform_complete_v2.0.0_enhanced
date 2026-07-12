import { describe, expect, it } from 'vitest';
import { readFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const root = dirname(fileURLToPath(import.meta.url));
const chatbot = readFileSync(join(root, 'ChatbotPage.tsx'), 'utf8');
// بعد تفكيك ai_agronomist، منطق الأدلّة يعيش في ai_evidence_runtime.py (main.py يعيد التصدير).
const runtime = readFileSync(join(root, '../../../services/ai_agronomist/ai_evidence_runtime.py'), 'utf8');

describe('Chatbot AI evidence transparency v49', () => {
  it('renders evidence sources separately from generated answer text', () => {
    expect(chatbot).toContain('data-testid="ai-evidence-sources"');
    expect(chatbot).toContain('data-testid="ai-evidence-ids"');
    expect(chatbot).toContain('data-testid="ai-readiness-warnings"');
    expect(chatbot).toContain('evidence_sources?: AiEvidenceSource[]');
  });

  it('passes source metadata returned by the AI runtime into bot messages', () => {
    expect(chatbot).toContain('evidenceSources: Array.isArray(data.evidence_sources)');
    expect(chatbot).toContain('generationProvider: data.generation_provider');
    expect(chatbot).toContain('readinessWarnings: Array.isArray(data.ai_context_pack_readiness?.warnings)');
  });

  it('grounds generation with the two-year field AI context pack', () => {
    expect(runtime).toContain('_ai_context_memory_lines');
    expect(runtime).toContain('_field_memory_evidence_ids');
    expect(runtime).toContain('evidence_sources');
    expect(runtime).toContain('ai_context_pack_readiness');
  });
});
