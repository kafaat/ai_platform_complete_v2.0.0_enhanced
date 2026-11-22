import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { readStoredTheme, useTheme } from './useTheme';

// Owner decision (22 Nov 2026, with the operations workspace refresh in #1568): a user who has
// never chosen a theme gets the light theme; a theme the user saved keeps winning.
describe('default theme', () => {
  afterEach(() => {
    vi.restoreAllMocks();
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

  it('is light when reading storage throws (private mode, blocked site data)', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError');
    });
    expect(readStoredTheme()).toBe('light');
  });

  it('is already the HTML default, so the first paint is light before any script runs', () => {
    // The CSP allows only same-origin scripts, so no inline script sets the theme early;
    // the attribute on <html> does, and it must stay equal to the hook's default.
    const html = readFileSync(join(process.cwd(), 'index.html'), 'utf-8');
    const tag = html.match(/<html\b[^>]*>/)?.[0] ?? '';
    expect(tag).toContain(`data-theme="${readStoredTheme()}"`);
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
