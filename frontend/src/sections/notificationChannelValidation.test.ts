import { describe, it, expect } from 'vitest';
import { invalidEnabledChannels } from './NotificationSettingsPage';
import type { NotificationPreferences } from '../services/api';

const base: NotificationPreferences = {
  email_enabled: false, email_address: '',
  sms_enabled: false, sms_number: '',
  push_enabled: false, push_token: '',
  whatsapp_enabled: false, whatsapp_number: '',
  event_types: [], min_severity: null,
};

// continuation-2 #10: لا تُحفَظ قناة مُفعّلة بلا هدف صالح.
describe('invalidEnabledChannels', () => {
  it('لا شيء عندما تكون كلّ القنوات مُطفأة', () => {
    expect(invalidEnabledChannels(base)).toEqual([]);
  });

  it('يرصد بريداً مُفعّلاً بعنوان غير صالح', () => {
    expect(invalidEnabledChannels({ ...base, email_enabled: true, email_address: 'not-an-email' })).toContain('البريد الإلكترونيّ');
    expect(invalidEnabledChannels({ ...base, email_enabled: true, email_address: '' })).toContain('البريد الإلكترونيّ');
  });

  it('يقبل بريداً/هاتفاً/رمزاً صالحاً', () => {
    expect(invalidEnabledChannels({
      ...base,
      email_enabled: true, email_address: 'a@b.com',
      sms_enabled: true, sms_number: '+967771234567',
      whatsapp_enabled: true, whatsapp_number: '967 77 123 4567',
      push_enabled: true, push_token: 'fcm-abc',
    })).toEqual([]);
  });

  it('يرصد هاتفاً/واتساب/رمزاً مُفعّلاً بلا هدف', () => {
    expect(invalidEnabledChannels({ ...base, sms_enabled: true, sms_number: 'abc' })).toContain('رقم SMS');
    expect(invalidEnabledChannels({ ...base, whatsapp_enabled: true, whatsapp_number: '' })).toContain('رقم واتساب');
    expect(invalidEnabledChannels({ ...base, push_enabled: true, push_token: '   ' })).toContain('رمز جهاز Push');
  });
});
