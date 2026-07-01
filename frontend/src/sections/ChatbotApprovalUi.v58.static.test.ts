import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

describe('ChatbotPage approval UI V58', () => {
  const source = readFileSync('src/sections/ChatbotPage.tsx', 'utf8');

  it('renders explicit approval cards and approve/deny controls for pending harness actions', () => {
    expect(source).toContain('data-testid="ai-approval-card"');
    expect(source).toContain('data-testid="ai-approval-approve"');
    expect(source).toContain('data-testid="ai-approval-deny"');
    expect(source).toContain('decideApproval');
  });

  it('posts decisions to governed ai-agronomist approval endpoints', () => {
    expect(source).toContain('/api/ai-agronomist/approvals/${decision}');
    expect(source).toContain('approval,');
    expect(source).toContain("reason: decision === 'deny'");
  });
});
