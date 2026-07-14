// اختبارات websocket — تثبّت السياسة المُحصَّنة (continuation-2 #1/#2/#3 + FE-09/FE-10):
//   • المتصفّح لا يُصدر أوامر تشغيليّة عبر WS (valve/pump/irrigation) — تُرفَض.
//   • أُطُر التحكّم/الاشتراك المسموح بها تُحفَظ في الصندوق ولا تُفرَّغ إلا بعد إقرار
//     مصادقة صريح (auth_ok/authenticated)، لا على مجرّد فتح القناة ولا على أوّل إطار وارد (FE-09).
//   • الرابط لا يحمل user_id ولا token — الهُويّة تُشتَقّ خادميّاً من الـJWT (FE-10).
//   • الأطر الواردة بلا event_type معروف (أو JSON فاسد) تُهمَل بلا توزيع.
// نحقن WebSocket وهميّاً (jsdom لا يوفّره).
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
  _open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }
  _message(obj: unknown) {
    this.onmessage?.({ data: JSON.stringify(obj) });
  }
  _raw(data: string) {
    this.onmessage?.({ data });
  }
}

(globalThis as unknown as { WebSocket: unknown }).WebSocket = MockWebSocket;

// يُستورد بعد حقن WebSocket حتى يلتقط الـsingleton المرجع الوهميّ.
import { wsService } from './websocket';

const AUTH_FRAME = JSON.stringify({ type: 'auth', token: 'test-jwt' });
const outboxOnly = (ws: MockWebSocket) => ws.sent.filter(m => m !== AUTH_FRAME);
// إقرار مصادقة الخادم = إطار إقرار صريح (auth_ok/authenticated) بعد الفتح — FE-09.
const ack = (ws: MockWebSocket) => ws._message({ type: 'auth_ok' });

beforeEach(() => {
  MockWebSocket.instances = [];
  wsService.disconnect();
  sessionStorage.setItem('sahool_access_token', 'test-jwt');
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  vi.spyOn(console, 'info').mockImplementation(() => {});
});

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe('WebSocket — الأوامر التشغيليّة ممنوعة عبر القناة (continuation-2 #2)', () => {
  it("يرفض valve/pump/irrigation وأيّ إطار بلا نوع تحكّم ('failed')", () => {
    wsService.connect(1);
    MockWebSocket.instances[0]._open();
    expect(wsService.send({ type: 'valve', state: 'open' })).toBe('failed');
    expect(wsService.send({ type: 'pump', id: 1 })).toBe('failed');
    expect(wsService.send({ type: 'irrigation', id: 9 })).toBe('failed');
    expect(wsService.send({ seq: 3 })).toBe('failed'); // بلا type
    // لم تُكتَب أيّ رسالة تشغيليّة على القناة.
    expect(outboxOnly(MockWebSocket.instances[0])).toHaveLength(0);
  });

  it("يسمح بأُطُر التحكّم/الاشتراك ويرسلها فوراً عند فتح القناة ومصادقتها ('sent')", () => {
    wsService.connect(1);
    const ws = MockWebSocket.instances[0];
    ws._open();
    ack(ws); // FE-09: لا كتابة فوريّة قبل الإقرار الصريح.
    expect(wsService.send({ type: 'subscribe', channel: 'field-42' })).toBe('sent');
    expect(outboxOnly(ws)).toContain(JSON.stringify({ type: 'subscribe', channel: 'field-42' }));
  });
});

describe('WebSocket — تفريغ الصندوق يتطلّب إقرار مصادقة صريح (FE-09/continuation-2 #1)', () => {
  it('لا يُفرّغ على مجرّد فتح القناة؛ يُفرّغ بعد إطار إقرار صريح', () => {
    expect(wsService.send({ type: 'subscribe', channel: 'a' })).toBe('queued');

    wsService.connect(1);
    const ws = MockWebSocket.instances[0];
    ws._open();
    // بعد الفتح: أُرسل إطار auth فقط، والصندوق لم يُفرَّغ بعد (بانتظار الإقرار).
    expect(outboxOnly(ws)).toHaveLength(0);

    ack(ws); // إقرار الخادم ⇒ التفريغ الآن.
    expect(outboxOnly(ws)).toEqual([JSON.stringify({ type: 'subscribe', channel: 'a' })]);
  });

  it('FE-09: إطار وارد ليس إقراراً لا يفتح البوّابة؛ فقط auth_ok/authenticated يُفرّغ', () => {
    expect(wsService.send({ type: 'subscribe', channel: 'a' })).toBe('queued');
    wsService.connect(1);
    const ws = MockWebSocket.instances[0];
    ws._open();

    // إطار وارد غير إقرار (كان "أوّل إطار" يكفي سابقاً) — يجب ألّا يُصادِق ولا يُفرّغ.
    ws._message({ type: 'notification', title: 'مُلفَّق' });
    ws._message({ event_type: 'pest_alert', title: 'آفة' }); // حتى حدث معروف: قبل الإقرار لا يُفرّغ
    expect(outboxOnly(ws)).toHaveLength(0);
    // القناة مفتوحة لكن غير مُصادَقة ⇒ الإرسال لا يزال يُطوَّر (لا يُكتَب فوراً).
    expect(wsService.send({ type: 'subscribe', channel: 'b' })).toBe('queued');
    expect(outboxOnly(ws)).toHaveLength(0);

    ack(ws); // إقرار صريح ⇒ يُفرَّغ ما تراكم بالترتيب.
    expect(outboxOnly(ws)).toEqual([
      JSON.stringify({ type: 'subscribe', channel: 'a' }),
      JSON.stringify({ type: 'subscribe', channel: 'b' }),
    ]);
  });

  it("FE-09: 'authenticated' مقبول أيضاً كإطار إقرار", () => {
    expect(wsService.send({ type: 'subscribe', channel: 'a' })).toBe('queued');
    wsService.connect(1);
    const ws = MockWebSocket.instances[0];
    ws._open();
    ws._message({ type: 'authenticated' });
    expect(outboxOnly(ws)).toEqual([JSON.stringify({ type: 'subscribe', channel: 'a' })]);
  });

  it('FE-09: بعد المصادقة، الإرسال على قناة مفتوحة يُكتَب فوراً (sent)', () => {
    wsService.connect(1);
    const ws = MockWebSocket.instances[0];
    ws._open();
    ack(ws);
    expect(wsService.send({ type: 'subscribe', channel: 'c' })).toBe('sent');
  });

  it('سقف الصندوق يُسقط الأقدم ويُبقي الأحدث (100)', () => {
    for (let i = 0; i < 100; i++) {
      expect(wsService.send({ type: 'subscribe', seq: i })).toBe('queued');
    }
    for (let i = 100; i < 105; i++) {
      expect(wsService.send({ type: 'subscribe', seq: i })).toBe('queue_full');
    }
    wsService.connect(1);
    const ws = MockWebSocket.instances[0];
    ws._open();
    ack(ws);
    const flushed = outboxOnly(ws);
    expect(flushed).toHaveLength(100);
    expect(flushed[0]).toBe(JSON.stringify({ type: 'subscribe', seq: 5 }));
    expect(flushed[99]).toBe(JSON.stringify({ type: 'subscribe', seq: 104 }));
  });

  it('disconnect يُسقط الرسائل المُعلّقة (لا تُسرَّب لجلسة لاحقة)', () => {
    wsService.send({ type: 'subscribe', channel: 'x' });
    wsService.disconnect();
    wsService.connect(1);
    const ws = MockWebSocket.instances[0];
    ws._open();
    ack(ws);
    expect(outboxOnly(ws)).toHaveLength(0);
  });
});

describe('WebSocket — لا مُعرّفات هُويّة في الرابط (FE-10)', () => {
  it('رابط الاتصال لا يحمل user_id ولا token — الهُويّة من الـJWT في إطار auth', () => {
    wsService.connect(42);
    const ws = MockWebSocket.instances[0];
    expect(ws.url).not.toContain('user_id');
    expect(ws.url).not.toContain('token');
    expect(ws.url).not.toContain('42');
    expect(ws.url).not.toContain('?'); // لا query string إطلاقاً
    // التوكن يُرسَل داخل إطار auth بعد الفتح، لا في الرابط.
    ws._open();
    expect(ws.sent[0]).toBe(JSON.stringify({ type: 'auth', token: 'test-jwt' }));
  });
});

describe('WebSocket — تحقّق الأطر الواردة (continuation-2 #3/#16)', () => {
  it('لا يوزّع إطاراً بلا event_type معروف، ولا يرمي على JSON فاسد', () => {
    const seen: unknown[] = [];
    wsService.onAny((d) => seen.push(d));
    wsService.connect(1);
    const ws = MockWebSocket.instances[0];
    ws._open();
    ack(ws); // أوّل رسالة (auth_ok) — ليست حدثاً معروفاً ⇒ لا توزيع.
    ws._message({ type: 'notification', title: 'مُلفَّق', message: 'x' }); // بلا event_type معروف
    ws._raw('{ this is not json'); // JSON فاسد — يجب ألّا يرمي
    expect(seen).toHaveLength(0);

    ws._message({ event_type: 'pest_alert', title: 'آفة', message: 'حقل 3' }); // معروف ⇒ يوزَّع
    expect(seen).toHaveLength(1);
  });
});
