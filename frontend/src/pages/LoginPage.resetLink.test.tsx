// The reset link (/reset-password?token=…) opens the new-password step with the link's token,
// and asking for a reset now promises a link, matching what the auth service mails.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const confirmPasswordReset = vi.fn();
const requestPasswordReset = vi.fn();
vi.mock('../hooks/useAuth', () => ({
  useAuthStore: () => ({ login: vi.fn(), loginDemo: vi.fn() }),
}));
vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/api')>()),
  confirmPasswordReset: (...args: unknown[]) => confirmPasswordReset(...args),
  requestPasswordReset: (...args: unknown[]) => requestPasswordReset(...args),
}));

import LoginPage from './LoginPage';

afterEach(() => vi.clearAllMocks());

describe('LoginPage reset link', () => {
  it('sets the new password with the token from the link, without asking for it', async () => {
    confirmPasswordReset.mockResolvedValue({ message: 'ok' });
    window.history.replaceState(null, '', '/reset-password?token=link-token-1&lang=ar');
    const { container } = render(<LoginPage initialView="reset-confirm" initialToken="link-token-1" />);
    expect(screen.getByText('تعيين كلمة مرور جديدة')).toBeTruthy();
    expect(screen.queryByLabelText(/رمز إعادة التعيين/)).toBeNull();
    const password = container.querySelector('#reset-new-password') as HTMLInputElement;
    fireEvent.change(password, { target: { value: 'Strong#Pass1' } });
    fireEvent.change(container.querySelector('#reset-confirm-password') as HTMLInputElement, {
      target: { value: 'Strong#Pass1' },
    });
    fireEvent.click(screen.getByRole('button', { name: /تأكيد كلمة المرور الجديدة/ }));
    // The secret leaves the address bar as soon as it is held in state; other parameters stay.
    expect(window.location.search).toBe('?lang=ar');
    await waitFor(() => expect(confirmPasswordReset).toHaveBeenCalledWith('link-token-1', 'Strong#Pass1'));
    expect(await screen.findByText('تم تغيير كلمة المرور بنجاح')).toBeTruthy();
  });

  it('refuses a confirmation that does not match, without calling the server', async () => {
    window.history.replaceState(null, '', '/reset-password?token=link-token-2&lang=ar');
    const { container } = render(<LoginPage initialView="reset-confirm" initialToken="link-token-2" />);
    fireEvent.change(container.querySelector('#reset-new-password') as HTMLInputElement, {
      target: { value: 'Strong#Pass1' },
    });
    fireEvent.change(container.querySelector('#reset-confirm-password') as HTMLInputElement, {
      target: { value: 'Strong#Pass2' },
    });
    fireEvent.click(screen.getByRole('button', { name: /تأكيد كلمة المرور الجديدة/ }));
    expect(await screen.findByText('كلمتا المرور غير متطابقتين')).toBeTruthy();
    expect(confirmPasswordReset).not.toHaveBeenCalled();
  });

  it('promises a link, not a code, and asks the user to open it', async () => {
    requestPasswordReset.mockResolvedValue({ message: 'إذا كان البريد مسجلاً، ستصلك رسالة' });
    render(<LoginPage initialView="reset-request" initialEmail="a@b.co" />);
    expect(screen.getByText(/سنرسل رابط إعادة تعيين صالحاً 30 دقيقة/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /إرسال الرابط/ }));
    await waitFor(() => expect(requestPasswordReset).toHaveBeenCalledWith('a@b.co'));
    expect(await screen.findByText(/افتح رابط إعادة التعيين في البريد/)).toBeTruthy();
    expect(screen.queryByLabelText(/رمز إعادة التعيين/)).toBeNull();
    expect(screen.queryByText(/رمز إعادة تعيين صالحاً/)).toBeNull();
  });
});
