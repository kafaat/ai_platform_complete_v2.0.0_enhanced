import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { RESET_PASSWORD_PATH, authScreenFor, resetTokenFor } from './authScreens';

describe('authScreenFor', () => {
  it.each([
    ['/reset-password', '?token=abc', 'reset-password'],
    ['/reset-password/', '?token=abc', 'reset-password'],
    ['/reset-password', '', 'forgot-password'],
    ['/reset-password', '?token=', 'forgot-password'],
    ['/', '?token=abc', 'accept-invitation'],
    ['/login', '?token=abc', 'accept-invitation'],
    ['/accept-invitation', '?token=abc', 'accept-invitation'],
    ['/signup', '?token=abc', 'accept-invitation'],
    ['/signup', '', 'signup'],
    ['/forgot-password', '', 'forgot-password'],
    ['/login', '', 'login'],
    ['/fields/42/workspace', '', 'login'],
  ])('%s%s → %s', (pathname, search, expected) => {
    expect(authScreenFor(pathname, search)).toBe(expected);
  });

  it('hands the token only to a /reset-password link', () => {
    expect(resetTokenFor('/reset-password', '?token=t-1')).toBe('t-1');
    expect(resetTokenFor('/', '?token=t-1')).toBe('');
    expect(resetTokenFor('/accept-invitation', '?token=t-1')).toBe('');
  });
});

// The links come from the auth service. If either email changes its path, the web app must
// change with it, or the link lands on the wrong screen (it used to open the invitation page).
describe('the auth service links that the web app must route', () => {
  const services = join(process.cwd(), '..', 'services', 'auth');
  const links = [
    ['password-reset email', join(services, 'main.py')],
    ['tenant-owner setup email', join(services, 'routers', 'tenants.py')],
  ];

  it.each(links)('%s opens the new-password step', (_name, file) => {
    const source = readFileSync(file, 'utf8');
    const match = /FRONTEND_URL[^}]*\}(\/[\w-]+)\?token=\{/.exec(source);
    expect(match, `${file} no longer builds a ?token= link`).not.toBeNull();
    const path = match![1];
    expect(path).toBe(RESET_PASSWORD_PATH);
    expect(authScreenFor(path, '?token=from-email')).toBe('reset-password');
    expect(resetTokenFor(path, '?token=from-email')).toBe('from-email');
  });
});
