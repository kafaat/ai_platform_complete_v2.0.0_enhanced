import { describe, expect, it } from 'vitest';
import { errorBudgetColor, releaseGateBadge } from './globalScaleRuntime';

describe('globalScaleRuntime contracts', () => {
  it('classifies release gates', () => {
    expect(releaseGateBadge(true, [])).toBe('ready');
    expect(releaseGateBadge(false, ['dr'])).toBe('blocked');
    expect(releaseGateBadge(false, ['cost'])).toBe('needs-review');
  });

  it('maps error budget status to badge color', () => {
    expect(errorBudgetColor('healthy')).toBe('green');
    expect(errorBudgetColor('watch')).toBe('amber');
    expect(errorBudgetColor('freeze_releases')).toBe('red');
  });
});
