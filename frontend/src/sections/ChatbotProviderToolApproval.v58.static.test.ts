import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, 'ChatbotPage.tsx'), 'utf8');

describe('Chatbot provider-native tool approval UI v58 static guard', () => {
  it('renders actionable approval cards for pending tool approvals', () => {
    expect(source).toContain('data-testid="ai-approval-card"');
    expect(source).toContain('data-testid="ai-approval-approve"');
    expect(source).toContain('data-testid="ai-approval-deny"');
    expect(source).toContain('بانتظار موافقة');
  });

  it('keeps harness transparency visible with tool calls and approvals', () => {
    expect(source).toContain('data-testid="ai-harness-transparency"');
    expect(source).toContain('data-testid="ai-harness-tools"');
    expect(source).toContain('data-testid="ai-harness-approvals"');
  });
});
