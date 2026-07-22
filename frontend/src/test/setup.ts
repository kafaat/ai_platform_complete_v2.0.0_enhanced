// إعداد بيئة الاختبار — يُحمّل مُطابِقات jest-dom (toBeInTheDocument …)
// ويُنظّف شجرة DOM بعد كلّ اختبار لتفادي تسرّب الحالة بين الاختبارات.
import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// Keep the CI suite fail-closed for two warning classes that indicate tests are
// no longer observing the same update/route behavior as the browser. Other
// console output remains untouched so application error-path tests can still
// exercise and report their intended diagnostics.
const originalConsoleError = console.error.bind(console);
const originalConsoleWarn = console.warn.bind(console);

function renderedConsoleMessage(args: unknown[]): string {
  return args.map((value) => (typeof value === 'string' ? value : String(value))).join(' ');
}

console.error = (...args: unknown[]) => {
  const message = renderedConsoleMessage(args);
  if (message.includes('not wrapped in act(...)')) {
    throw new Error(`Forbidden React test warning: ${message}`);
  }
  originalConsoleError(...args);
};

console.warn = (...args: unknown[]) => {
  const message = renderedConsoleMessage(args);
  if (message.includes('React Router Future Flag Warning')) {
    throw new Error(`Forbidden React Router test warning: ${message}`);
  }
  originalConsoleWarn(...args);
};

afterEach(() => {
  cleanup();
});
