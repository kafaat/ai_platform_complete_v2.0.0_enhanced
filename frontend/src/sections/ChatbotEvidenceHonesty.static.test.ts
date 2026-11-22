import { describe, expect, it } from 'vitest';
import { readFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const root = dirname(fileURLToPath(import.meta.url));
const chatbot = readFileSync(join(root, 'ChatbotPage.tsx'), 'utf8');

describe('Chatbot shows what the answer rests on', () => {
  it('renders citations, review notices and declared retrieval absence', () => {
    for (const id of ['ai-citations', 'ai-advisory-notices', 'ai-rag-unavailable', 'ai-unverified-references', 'ai-source-badge', 'ai-audit-not-persisted']) {
      expect(chatbot).toContain(`data-testid="${id}"`);
    }
    expect(chatbot).toContain('citations: citationsFromAnnotations(data.annotations)');
    expect(chatbot).toContain('notices: advisoryNotices(data.advisory)');
    expect(chatbot).toContain('ragUnavailableText(data.rag_available, data.rag_unavailable_reason)');
    expect(chatbot).toContain('auditNotPersisted: auditNotPersistedText(data.audit_event)');
    expect(chatbot).toContain("confidenceCalibrated: data.confidence_calibrated === true");
  });

  it('does not badge every answer with sources it may not have had', () => {
    expect(chatbot).not.toContain('SAHOOL AI Runtime · RAG/KG/Field Memory');
    expect(chatbot).toContain('sourceBadgeText(msg.evidenceSources)');
  });

  it('does not promise prescriptions the evidence-only runtime never returns', () => {
    expect(chatbot).not.toContain('توصيات التسميد والمكافحة');
    expect(chatbot).not.toContain('متى أري الحقل اليوم؟');
    expect(chatbot).not.toContain('ما احتياجات التسميد للقمح الآن؟');
    expect(chatbot).not.toMatch(/id:'welcome', role:'assistant', source:'ai-runtime'/);
  });
});
