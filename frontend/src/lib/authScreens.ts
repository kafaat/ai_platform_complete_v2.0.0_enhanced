// Pre-authentication screens, derived from the URL.
//
// The auth service mails password-reset links, and the owner-setup link of a newly
// provisioned tenant, as `/reset-password?token=…` (services/auth/main.py send_reset_email,
// services/auth/routers/tenants.py). Invitation links carry `?token=` too. So the path
// decides: /reset-password with a token opens the new-password step; a token on any other
// path stays an invitation, so existing invitation links keep working.
export type AuthScreen = 'login' | 'signup' | 'forgot-password' | 'reset-password' | 'accept-invitation';

export const RESET_PASSWORD_PATH = '/reset-password';

function normalise(pathname: string): string {
  return pathname.replace(/\/+$/, '') || '/';
}

export function authScreenFor(pathname: string, search: string): AuthScreen {
  const path = normalise(pathname);
  const token = new URLSearchParams(search).get('token');
  if (path === RESET_PASSWORD_PATH) return token ? 'reset-password' : 'forgot-password';
  if (token !== null) return 'accept-invitation';
  if (path === '/signup') return 'signup';
  if (path === '/forgot-password') return 'forgot-password';
  return 'login';
}

/** The reset token of a /reset-password link, or '' anywhere else. */
export function resetTokenFor(pathname: string, search: string): string {
  if (normalise(pathname) !== RESET_PASSWORD_PATH) return '';
  return new URLSearchParams(search).get('token') ?? '';
}
