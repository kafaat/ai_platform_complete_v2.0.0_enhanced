import { describe, expect, it } from 'vitest';

describe('frontend test warning guard', () => {
  it('fails closed on React updates outside act', () => {
    expect(() => console.error('An update to Example inside a test was not wrapped in act(...).'))
      .toThrow(/Forbidden React test warning/);
  });

  it('fails closed on React Router compatibility warnings', () => {
    expect(() => console.warn('React Router Future Flag Warning: enable the compatibility flag'))
      .toThrow(/Forbidden React Router test warning/);
  });
});
