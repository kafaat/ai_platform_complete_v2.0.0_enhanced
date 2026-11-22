import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { readStoredTheme, useTheme } from './useTheme';

const html = readFileSync(join(process.cwd(), 'index.html'), 'utf8');
const bootstrap = readFileSync(join(process.cwd(), 'public/theme-init.v1.js'), 'utf8');
// Exercise the shipped script itself before mounting React.
const firstPaint = () => new Function('window', 'document', bootstrap)(window, document);

// Owner decision (22 Nov 2026, with the operations workspace refresh in #1568): a user who has
// never chosen a theme gets the light theme; a theme the user saved keeps winning.
describe('default theme', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.setAttribute('data-theme', 'light');
  });
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it.each([null, '', 'neon', 'system', 'LIGHT'])('is light for absent or invalid preference %s', saved => {
    if (saved !== null) window.localStorage.setItem('sahool-theme', saved);
    firstPaint();
    expect(document.documentElement).toHaveAttribute('data-theme', 'light');
    expect(readStoredTheme()).toBe('light');
    expect(renderHook(useTheme).result.current.theme).toBe('light');
    expect(window.localStorage.getItem('sahool-theme')).toBe(saved);
  });

  it.each(['getter', 'getItem'] as const)('is light when the storage %s throws', failure => {
    const fail = () => {
      throw new DOMException('denied', 'SecurityError');
    };
    if (failure === 'getter') vi.spyOn(window, 'localStorage', 'get').mockImplementation(fail);
    else vi.spyOn(Storage.prototype, 'getItem').mockImplementation(fail);
    expect(firstPaint).not.toThrow();
    expect(readStoredTheme()).toBe('light');
    expect(renderHook(useTheme).result.current.theme).toBe('light');
    expect(document.documentElement).toHaveAttribute('data-theme', 'light');
  });

  it('has a light HTML fallback and loads the same-origin bootstrap before app scripts or styles', () => {
    const page = new DOMParser().parseFromString(html, 'text/html');
    expect(page.documentElement.getAttribute('data-theme')).toBe(readStoredTheme());
    const scripts = [...page.querySelectorAll('script, link[rel="stylesheet"]')];
    expect(scripts[0].getAttribute('src')).toBe('/theme-init.v1.js');
    expect(scripts[0].hasAttribute('async')).toBe(false);
    expect(scripts[0].hasAttribute('defer')).toBe(false);
    expect(scripts[0].hasAttribute('type')).toBe(false);
    expect(scripts[0].textContent).toBe('');
  });

  it.each(['dark', 'light', 'cream'] as const)('keeps a saved %s choice', (saved) => {
    window.localStorage.setItem('sahool-theme', saved);
    firstPaint();
    expect(document.documentElement).toHaveAttribute('data-theme', saved);
    expect(readStoredTheme()).toBe(saved);
    expect(renderHook(useTheme).result.current.theme).toBe(saved);
    expect(document.documentElement).toHaveAttribute('data-theme', saved);
    expect(window.localStorage.getItem('sahool-theme')).toBe(saved);
  });

  it('applies the default, saves a switch, and restores it before the next mount', () => {
    firstPaint();
    const { result, unmount } = renderHook(useTheme);
    expect(result.current.theme).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');

    act(() => result.current.setTheme('dark'));
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(window.localStorage.getItem('sahool-theme')).toBe('dark');
    unmount();
    document.documentElement.setAttribute('data-theme', 'light');
    firstPaint();
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
    expect(renderHook(useTheme).result.current.theme).toBe('dark');
  });

  it('still changes the current theme when writing storage fails', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Storage full', 'QuotaExceededError');
    });
    const { result } = renderHook(useTheme);
    act(() => result.current.setTheme('cream'));
    expect(result.current.theme).toBe('cream');
    expect(document.documentElement).toHaveAttribute('data-theme', 'cream');
  });
});
