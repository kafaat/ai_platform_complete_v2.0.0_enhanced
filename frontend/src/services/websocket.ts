// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — services/websocket.ts
// خدمة الإشعارات الفورية عبر WebSocket
//   ✅ اتصال تلقائي + إعادة اتصال تدريجية
//   ✅ إشعارات المتصفح (Notification API)
//   ✅ استماع لـ 6 أنواع أحداث NATS
//   ✅ Toast notifications في الواجهة
// ═══════════════════════════════════════════════════════════════

type EventType =
  | 'satellite' | 'weather_alert' | 'pest_alert'
  | 'irrigation_rec' | 'fertilizer_rec' | 'low_stock'
  | 'task_assigned' | 'economic_analysis';

type Handler = (data: Record<string, unknown>) => void;

// نتيجة الإرسال (P0.2): بدل bool صامت نُعيد حالة صريحة كي يعرف مُستدعو الأوامر
// المُغيِّرة للحالة (ريّ/صمام/مضخّة) مصير أمره — أُرسل فوراً، أم طُوبِر، أم
// أُسقط الأقدم لإفساح مكان (فقد بيانات صريح)، أم فشل التسلسل ولم يُحفَظ.
//   'sent'       — كُتبت إلى قناة OPEN فوراً.
//   'queued'     — القناة غير مفتوحة؛ حُفظت في الصندوق (يوجد متّسع).
//   'queue_full' — الصندوق ممتلئ؛ أُسقط الأقدم وحُفظت الجديدة (إشارة فقد صريحة).
//   'failed'     — تعذّر تسلسل الرسالة (JSON.stringify رمى) — لم تُحفظ.
export type SendResult = 'sent' | 'queued' | 'queue_full' | 'failed';

// قاعدة WebSocket: مرجعيّة البوّابة (nginx /ws/ يُوجِّه لخدمة الإشعارات :8123).
// الافتراضيّ مسار نسبيّ '/ws' يُحَلّ على مضيف الصفحة الحاليّ بمخطّط ws/wss الصحيح
// (يطابق توجيه nginx)، بلا منفذ مباشر مكشوف. يمكن تجاوزه بـVITE_WS_BASE_URL
// (نسبيّ مثل '/ws' أو مطلق مثل 'ws://localhost:8123/ws' للتطوير بلا بوّابة).
function resolveWsBase(): string {
  const raw = import.meta.env.VITE_WS_BASE_URL || '/ws';
  // مطلق بالفعل (ws://، wss://) ⇒ استخدمه كما هو.
  if (/^wss?:\/\//i.test(raw)) return raw.replace(/\/+$/, '');
  // نسبيّ ⇒ اشتقّ المخطّط/المضيف من الصفحة (https ⇒ wss).
  if (typeof window !== 'undefined') {
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    return `${scheme}://${window.location.host}${raw.startsWith('/') ? raw : `/${raw}`}`.replace(/\/+$/, '');
  }
  return `ws://localhost:8000${raw.startsWith('/') ? raw : `/${raw}`}`.replace(/\/+$/, '');
}
const WS_URL = `${resolveWsBase()}/notifications`;

class WebSocketService {
  private ws: WebSocket | null = null;
  private listeners = new Map<EventType, Handler[]>();
  private globalListeners: Handler[] = [];
  private userId: number | null = null;
  private reconnectAttempts = 0;
  private maxReconnects = 8;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private isConnecting = false;
  private pingInterval: ReturnType<typeof setInterval> | null = null;
  // صندوق صادر محدود (Phase 3): يحفظ الرسائل المُرسَلة بينما القناة ليست OPEN
  // (إعادة اتصال/إقلاع) ويُفرِّغها عند الفتح، بدل إسقاطها صامتةً. فقدان أمر
  // تشغيليّ (ريّ/صمام/مضخّة) صامتاً أخطر من تأخيره. محدود بسقفٍ لتجنّب نموّ
  // غير محدود؛ عند الامتلاء نُسقط الأقدم (نُبقي الأحدث، الأقرب للحالة الراهنة)
  // مع تحذير صريح فلا يكون الفقد خفيّاً.
  private outbox: string[] = [];
  private readonly maxOutbox = 100;

  connect(userId: number): void {
    if (this.isConnecting) return;
    this.userId = userId;

    // التوكن من sessionStorage (نفس مصدر الـ interceptor) — لا 'demo' احتياطيّ.
    // بلا توكن صالح: لا نفتح اتصالاً (كان يتّصل دائماً بـtoken=demo).
    const token = sessionStorage.getItem('sahool_access_token');
    if (!token) return;

    this.isConnecting = true;
    // التوكن لم يَعُد في الرابط (كان يتسرّب إلى سجلّات الوكلاء/الخوادم)؛ نرسله
    // الآن في أوّل رسالة (إطار auth) بعد فتح الاتصال. نُبقي user_id للتوجيه
    // والتوافق الخلفيّ (الخادم يتجاهله للمصادقة — يعتمد sub من الـJWT).
    const url = `${WS_URL}?user_id=${userId}`;

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        console.info('[WS] SAHOOL WebSocket connected');
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        // أوّلاً: أرسل إطار المصادقة قبل أيّ شيء آخر (التوكن في الرسالة الأولى).
        this.ws?.send(JSON.stringify({ type: 'auth', token }));
        // ثمّ فرّغ أيّ رسائل مُعلّقة طُوبِرت بينما كانت القناة مغلقة.
        this._flushOutbox();
        // Ping كل 30 ثانية للحفاظ على الاتصال
        this.pingInterval = setInterval(() => {
          if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30_000);
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as Record<string, unknown>;
          if (data.type === 'pong') return;
          const eventType = data.event_type as EventType;

          // Dispatch to type-specific listeners
          if (eventType && this.listeners.has(eventType)) {
            this.listeners.get(eventType)!.forEach(cb => cb(data));
          }
          // Dispatch to global listeners
          this.globalListeners.forEach(cb => cb(data));

          // Browser notification
          this._showBrowserNotif(data);
        } catch {
          // invalid JSON — ignore
        }
      };

      this.ws.onclose = (e) => {
        this.isConnecting = false;
        if (this.pingInterval) clearInterval(this.pingInterval);
        if (e.code !== 1000 && this.reconnectAttempts < this.maxReconnects) {
          const delay = Math.min(30_000, 2000 * Math.pow(1.5, this.reconnectAttempts));
          console.info(`[WS] Reconnecting in ${(delay/1000).toFixed(0)}s (attempt ${this.reconnectAttempts + 1})`);
          this.reconnectTimer = setTimeout(() => {
            this.reconnectAttempts++;
            this.connect(this.userId!);
          }, delay);
        }
      };

      this.ws.onerror = () => {
        this.isConnecting = false;
      };
    } catch (e) {
      this.isConnecting = false;
      console.warn('[WS] Connection failed (offline mode):', e);
    }
  }

  on(eventType: EventType, handler: Handler): () => void {
    if (!this.listeners.has(eventType)) this.listeners.set(eventType, []);
    this.listeners.get(eventType)!.push(handler);
    // Return unsubscribe
    return () => {
      const arr = this.listeners.get(eventType)!;
      this.listeners.set(eventType, arr.filter(h => h !== handler));
    };
  }

  onAny(handler: Handler): () => void {
    this.globalListeners.push(handler);
    return () => { this.globalListeners = this.globalListeners.filter(h => h !== handler); };
  }

  /**
   * يُرسل رسالة عبر القناة. عند كون القناة غير مفتوحة (إعادة اتصال/إقلاع) تُحفظ
   * في صندوق صادر محدود وتُفرَّغ عند الفتح، بدل إسقاطها صامتةً (Phase 3).
   * يعيد {@link SendResult}: 'sent' إن أُرسلت فوراً، 'queued' إن وُضِعت في الطابور
   * (مع متّسع)، 'queue_full' إن أُسقط الأقدم لإفساح مكان (فقد صريح)، 'failed' إن
   * تعذّر تسلسلها (لم تُحفظ).
   */
  send(data: Record<string, unknown>): SendResult {
    let payload: string;
    try {
      payload = JSON.stringify(data);
    } catch (e) {
      console.warn('[WS] Dropping unserializable message:', e);
      return 'failed';
    }
    if (this.ws?.readyState === WebSocket.OPEN) {
      // قد تُغلَق القناة بين فحص الحالة والإرسال (سباق) فيُرمى — نلتقط ونُعيد
      // الرسالة للطابور بدل فقدها صامتةً.
      try {
        this.ws.send(payload);
        return 'sent';
      } catch (e) {
        console.warn('[WS] send failed, re-queuing message:', e);
      }
    }
    // غير مفتوحة بعد: ضعها في الطابور لتُرسَل عند الفتح. عند الامتلاء أسقط الأقدم
    // (نُبقي الأحدث) مع تحذير صريح حتى لا يكون فقد الأوامر التشغيليّة خفيّاً.
    if (this.outbox.length >= this.maxOutbox) {
      this.outbox.shift();
      console.warn(`[WS] Outbox full (${this.maxOutbox}); dropped oldest queued message`);
      this.outbox.push(payload);
      return 'queue_full';
    }
    this.outbox.push(payload);
    return 'queued';
  }

  // يُفرّغ الصندوق الصادر بالترتيب عند فتح القناة. ما يفشل إرساله (إغلاق/سباق)
  // يُعاد لرأس الطابور ليُحاوَل عند الفتح التالي، فلا تُفقد رسائل بسبب إغلاق
  // أثناء التفريغ.
  private _flushOutbox(): void {
    if (!this.outbox.length) return;
    const pending = this.outbox;
    this.outbox = [];
    for (let i = 0; i < pending.length; i++) {
      if (this.ws?.readyState !== WebSocket.OPEN) {
        this.outbox.push(...pending.slice(i));
        break;
      }
      try {
        this.ws.send(pending[i]);
      } catch (e) {
        console.warn('[WS] flush send failed, re-queuing remaining:', e);
        this.outbox.push(...pending.slice(i));
        break;
      }
    }
  }

  disconnect(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.pingInterval)   clearInterval(this.pingInterval);
    this.ws?.close(1000, 'logout');
    this.ws = null;
    this.userId = null;
    this.reconnectAttempts = 0;
    this.isConnecting = false;
    // خروج صريح: نُسقط الرسائل المُعلّقة (لا نُعيد إرسالها لجلسة/مستخدم آخر).
    this.outbox = [];
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /** طلب إذن الإشعارات */
  async requestNotificationPermission(): Promise<boolean> {
    if (!('Notification' in window)) return false;
    if (Notification.permission === 'granted') return true;
    const result = await Notification.requestPermission();
    return result === 'granted';
  }

  private _showBrowserNotif(data: Record<string, unknown>): void {
    if (Notification.permission !== 'granted') return;
    const title   = String(data.title   || 'SAHOOL تنبيه');
    const message = String(data.message || '');
    const icon    = '/favicon.svg';
    try {
      const notif = new Notification(title, { body: message, icon, lang: 'ar', dir: 'rtl' });
      notif.onclick = () => { window.focus(); notif.close(); };
      setTimeout(() => notif.close(), 8000);
    } catch { /* denied or unsupported */ }
  }
}

export const wsService = new WebSocketService();

// ── Toast helper (رسائل التنبيه في الواجهة) ───────────────────
export type ToastItem = {
  id:      string;
  type:    'info' | 'success' | 'warning' | 'error';
  title:   string;
  message: string;
  time:    Date;
};

type ToastListener = (toasts: ToastItem[]) => void;

class ToastStore {
  private items: ToastItem[] = [];
  private listeners: ToastListener[] = [];

  add(type: ToastItem['type'], title: string, message: string, durationMs = 5000) {
    const item: ToastItem = { id: Math.random().toString(36).slice(2), type, title, message, time: new Date() };
    this.items = [item, ...this.items].slice(0, 8);
    this.notify();
    setTimeout(() => this.remove(item.id), durationMs);
  }

  remove(id: string) {
    this.items = this.items.filter(i => i.id !== id);
    this.notify();
  }

  subscribe(fn: ToastListener): () => void {
    this.listeners.push(fn);
    fn(this.items);
    return () => { this.listeners = this.listeners.filter(l => l !== fn); };
  }

  private notify() { this.listeners.forEach(l => l([...this.items])); }
  getAll() { return this.items; }
}

export const toastStore = new ToastStore();

// ── Auto-wire WS events → Toasts ──────────────────────────────
const EVENT_TOAST_MAP: Record<string, { emoji: string; type: ToastItem['type'] }> = {
  satellite:       { emoji:'🛰️',  type:'info' },
  weather_alert:   { emoji:'🌩️',  type:'warning' },
  pest_alert:      { emoji:'🐛',  type:'error' },
  irrigation_rec:  { emoji:'💧',  type:'info' },
  fertilizer_rec:  { emoji:'🌱',  type:'info' },
  low_stock:       { emoji:'📦',  type:'warning' },
  task_assigned:   { emoji:'✅',  type:'success' },
  economic_analysis:{ emoji:'💰', type:'success' },
};

wsService.onAny((data) => {
  const cfg = EVENT_TOAST_MAP[data.event_type as string];
  if (cfg) {
    toastStore.add(
      cfg.type,
      `${cfg.emoji} ${String(data.title || data.event_type)}`,
      String(data.message || ''),
    );
  }
});
