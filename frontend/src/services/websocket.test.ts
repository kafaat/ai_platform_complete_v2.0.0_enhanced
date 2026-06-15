// اختبارات websocket — تثبّت الصندوق الصادر المحدود (Phase 3): الرسائل المُرسَلة
// أثناء انغلاق القناة تُحفظ وتُفرَّغ عند الفتح بدل فقدها صامتةً، مع سقفٍ يُسقط
// الأقدم عند الامتلاء. نحقن WebSocket وهميّاً (jsdom لا يوفّره).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: MockWebSocket[] = [];

  readyState = MockWebSocket.CONNECTING;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }
  send(payload: string) { this.sent.push(payload); }
  close() { this.readyState = MockWebSocket.CLOSED; }
  // فتح مُتحكَّم به من الاختبار.
  _open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
(globalThis as any).WebSocket = MockWebSocket;

// يُستورد بعد حقن WebSocket حتى يلتقط الـsingleton المرجع الوهميّ.
import { wsService } from './websocket';

// إطار المصادقة (#241/#236): connect() يتطلّب توكناً في sessionStorage ولا يفتح
// اتصالاً بدونه، ويُرسل {type:'auth',token} كأوّل رسالة عند الفتح. نضبط توكناً في
// كلّ اختبار ونُصفّي إطار auth من المُرسَل كي نتحقّق من الصندوق الصادر فقط.
const AUTH_FRAME = JSON.stringify({ type: 'auth', token: 'test-jwt' });
const outboxOnly = (ws: MockWebSocket) => ws.sent.filter(m => m !== AUTH_FRAME);

beforeEach(() => {
  MockWebSocket.instances = [];
  wsService.disconnect(); // يُفرّغ الطابور وأيّ حالة سابقة
  sessionStorage.setItem('sahool_access_token', 'test-jwt');
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  vi.spyOn(console, 'info').mockImplementation(() => {});
});

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe('WebSocketService outbox (Phase 3)', () => {
  it('يُرسل فوراً حين تكون القناة مفتوحة (يعيد true)', () => {
    wsService.connect(1);
    const ws = MockWebSocket.instances[0];
    ws._open();
    const ok = wsService.send({ type: 'valve', state: 'open' });
    expect(ok).toBe(true);
    expect(outboxOnly(ws)).toContain(JSON.stringify({ type: 'valve', state: 'open' }));
  });

  it('يحفظ الرسائل حين القناة غير مفتوحة ثمّ يُفرّغها عند الفتح (لا فقد صامت)', () => {
    // مُرسَلة قبل أيّ اتصال ⇒ تُحفظ (تعيد false) لا تُفقد.
    expect(wsService.send({ type: 'pump', id: 1 })).toBe(false);
    expect(wsService.send({ type: 'pump', id: 2 })).toBe(false);

    wsService.connect(1);
    const ws = MockWebSocket.instances[0];
    ws._open(); // التفريغ يحدث في onopen

    expect(outboxOnly(ws)).toEqual([
      JSON.stringify({ type: 'pump', id: 1 }),
      JSON.stringify({ type: 'pump', id: 2 }),
    ]);
  });

  it('عند امتلاء الطابور يُسقط الأقدم ويُبقي الأحدث (سقف 100)', () => {
    // 105 رسالة والقناة مغلقة ⇒ يبقى آخر 100 (تُسقط 0..4).
    for (let i = 0; i < 105; i++) wsService.send({ seq: i });

    wsService.connect(1);
    const ws = MockWebSocket.instances[0];
    ws._open();

    const flushed = outboxOnly(ws);
    expect(flushed).toHaveLength(100);
    expect(flushed[0]).toBe(JSON.stringify({ seq: 5 }));        // أقدم محفوظ
    expect(flushed[99]).toBe(JSON.stringify({ seq: 104 }));      // أحدث
  });

  it('disconnect يُسقط الرسائل المُعلّقة (لا تُسرَّب لجلسة لاحقة)', () => {
    wsService.send({ type: 'irrigation', id: 9 });
    wsService.disconnect();

    wsService.connect(1);
    const ws = MockWebSocket.instances[0];
    ws._open();

    expect(outboxOnly(ws)).toHaveLength(0);
  });
});
