import { describe, expect, it } from 'vitest';
import { evaluateDesignSystemGovernance } from './designSystemGovernance';

describe('evaluateDesignSystemGovernance', () => {
  it('يعطي نتيجة عالية عند اكتمال token domains وقواعد الوكيل', () => {
    const result = evaluateDesignSystemGovernance();
    expect(result.score).toBeGreaterThanOrEqual(90);
    expect(result.missingDomains).toEqual([]);
    expect(result.agentRules.some((rule) => rule.includes('CSS variables'))).toBe(true);
  });
});
