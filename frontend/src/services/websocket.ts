// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — services/websocket.ts
// خدمة الإشعارات الفورية عبر WebSocket
//   ✅ اتصال تلقائي + إعادة اتصال تدريجية
//   ✅ إشعارات المتصفح (Notification API)
//   ✅ استماع لـ 6 أنواع أحداث NATS
//   ✅ Toast notifications في الواجهة
// ═══════════════════════════════════════════════════════════════

import { getAccessToken } from '../lib/authStorage';

type EventType =
  | 'satellite' | 'weather_alert' | 'pest_alert'
  | 'irrigation_rec' | 'fertilizer_rec' | 'low_stock'
  | 'task_assigned' | 'economic_analysis';

type Handler = (data: Record<string, unknown>) => void;

const WS_URL = import.meta.env.VITE_WS_URL || `ws://${typeof window !== 'undefined' ? window.location.host : 'localhost:8000'}/ws/notifications`;

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
    this.isConnecting = true;

    // إصلاح: التوكن مخزّن في sessionStorage (lib/authStorage)، لا localStorage —
    // القراءة السابقة من localStorage كانت تُرجِع فارغاً دائماً فتسقط على 'demo'،
    // فيتصل WS لكلّ مستخدم مُصادَق بتوكن وهميّ بدل توكنه الحقيقيّ.
    const token = getAccessToken() || 'demo';
    const url   = `${WS_URL}?token=${token}&user_id=${userId}`;

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        console.info('[WS] SAHOOL WebSocket connected');
        this.isConnecting = false;
        this.reconnectAttempts = 0;
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
   * يعيد true إن أُرسلت فوراً، وfalse إن وُضِعت في الطابور (أو أُسقطت عند الامتلاء).
   */
  send(data: Record<string, unknown>): boolean {
    let payload: string;
    try {
      payload = JSON.stringify(data);
    } catch (e) {
      console.warn('[WS] Dropping unserializable message:', e);
      return false;
    }
    if (this.ws?.readyState === WebSocket.OPEN) {
      // قد تُغلَق القناة بين فحص الحالة والإرسال (سباق) فيُرمى — نلتقط ونُعيد
      // الرسالة للطابور بدل فقدها صامتةً.
      try {
        this.ws.send(payload);
        return true;
      } catch (e) {
        console.warn('[WS] send failed, re-queuing message:', e);
      }
    }
    // غير مفتوحة بعد: ضعها في الطابور لتُرسَل عند الفتح. عند الامتلاء أسقط الأقدم
    // (نُبقي الأحدث) مع تحذير صريح حتى لا يكون فقد الأوامر التشغيليّة خفيّاً.
    if (this.outbox.length >= this.maxOutbox) {
      this.outbox.shift();
      console.warn(`[WS] Outbox full (${this.maxOutbox}); dropped oldest queued message`);
    }
    this.outbox.push(payload);
    return false;
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
