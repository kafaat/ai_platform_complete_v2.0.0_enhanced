// وضع العرض التجريبيّ يجب أن يبقى ظاهراً بكلّ عرض شاشة: شريط التنقّل يُظهره عند التوسيع فقط،
// فشريط السياق يحمل الشارة دائماً حين isDemoMode.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';

const auth = vi.hoisted(() => ({ isDemoMode: false }));
vi.mock('../../hooks/useAuth', () => ({
  useAuthStore: (sel?: (s: typeof auth) => unknown) => (sel ? sel(auth) : auth),
}));
vi.mock('../ConnectionStatus', () => ({ default: () => null }));
vi.mock('../ThemeToggle', () => ({ default: () => null }));

import ContextBar from './ContextBar';

const renderBar = () => render(
  <MemoryRouter><ContextBar onMenu={() => {}} theme="dark" setTheme={() => {}} /></MemoryRouter>,
);

afterEach(cleanup);

describe('ContextBar demo badge', () => {
  it('shows the demo badge in demo mode', () => {
    auth.isDemoMode = true;
    renderBar();
    expect(screen.getByRole('status')).toHaveTextContent('تجريبي');
  });

  it('shows no badge outside demo mode', () => {
    auth.isDemoMode = false;
    renderBar();
    expect(screen.queryByText(/تجريبي/)).not.toBeInTheDocument();
  });
});
