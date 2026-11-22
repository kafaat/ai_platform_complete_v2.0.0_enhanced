import { afterEach, describe, expect, it } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { readStoredTheme, useTheme } from './useTheme';

// Owner decision (22 Nov 2026, with the operations workspace refresh in #1568): a user who has
// never chosen a theme gets the light theme; a theme the user saved keeps winning.
describe('default theme', () => {
  afterEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('is light when nothing is stored', () => {
    expect(readStoredTheme()).toBe('light');
  });

  it('is light when the stored value is not a known theme', () => {
    window.localStorage.setItem('sahool-theme', 'neon');
    expect(readStoredTheme()).toBe('light');
  });

  it.each(['dark', 'light', 'cream'] as const)('keeps a saved %s choice', (saved) => {
    window.localStorage.setItem('sahool-theme', saved);
    expect(readStoredTheme()).toBe(saved);
  });

  it('applies the default to the document and saves a switch', () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');

    act(() => result.current.setTheme('dark'));
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(window.localStorage.getItem('sahool-theme')).toBe('dark');
  });
});
