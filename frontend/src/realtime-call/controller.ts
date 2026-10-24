import { CallApi, type Session, validateSession } from './api';
export interface AudioTrack { stop(): void; }
export interface CallRoom {
  connect(url: string, token: string): Promise<void>;
  disconnect(): Promise<void> | void;
  publish(track: AudioTrack): Promise<void>;
  onDisconnected(callback: () => void): void;
  onReconnecting(callback: () => void): void;
}
export interface CallMedia { room(): CallRoom; microphone(): Promise<AudioTrack>; }
/** Owns capture even while permission, connect and publish promises are pending. */
export class CallController {
  private epoch = 0;
  private captureEpoch = 0;
  private capturePending = false;
  private room?: CallRoom;
  private track?: AudioTrack;
  private session?: Session;
  private timer?: ReturnType<typeof setTimeout>;
  constructor(private api: CallApi, private media: CallMedia, private changed: (value: string) => void) {}
  async join(field: string): Promise<boolean> {
    if (this.room || this.session) throw new Error('الجلسة قائمة بالفعل');
    const epoch = ++this.epoch;
    this.changed('جارٍ إنشاء الجلسة');
    const session = await this.api.create(field);
    if (epoch !== this.epoch) { await this.api.close(session.session_id).catch(() => {}); return false; }
    this.session = session;
    try {
      validateSession(session, field);
      this.timer = setTimeout(() => { void this.leave(); }, Math.max(0, session.expires_at * 1000 - Date.now()));
      const room = this.media.room(); this.room = room;
      room.onDisconnected(() => { void this.leave(); });
      room.onReconnecting(() => { this.mute(); this.changed('إعادة الاتصال — الميكروفون مغلق'); });
      await room.connect(session.url, session.participant_token);
      if (epoch !== this.epoch) { await room.disconnect(); return false; }
      if (Date.now() >= session.expires_at * 1000) { await this.leave(); return false; }
      this.changed('متصل — الميكروفون مغلق');
      return true;
    } catch (error) { await this.leave(); throw error; }
  }
  async enableMicrophone(): Promise<void> {
    if (!this.room || !this.session || Date.now() >= this.session.expires_at * 1000) throw new Error('الجلسة غير متاحة');
    if (this.track || this.capturePending) return;
    const epoch = this.epoch; const captureEpoch = this.captureEpoch; const room = this.room;
    this.capturePending = true;
    let track: AudioTrack;
    try { track = await this.media.microphone(); } finally { this.capturePending = false; }
    if (epoch !== this.epoch || captureEpoch !== this.captureEpoch || room !== this.room || !this.session || Date.now() >= this.session.expires_at * 1000) { track.stop(); return; }
    // Retain before the awaited publication: leave can stop this track immediately.
    this.track = track;
    try {
      await room.publish(track);
      if (epoch !== this.epoch || captureEpoch !== this.captureEpoch || this.track !== track || !this.session || Date.now() >= this.session.expires_at * 1000) { track.stop(); if (this.track === track) this.track = undefined; return; }
      this.changed('الميكروفون يعمل');
    } catch (error) { track.stop(); if (this.track === track) this.track = undefined; throw error; }
  }
  mute(): void { this.captureEpoch++; this.track?.stop(); this.track = undefined; }
  async leave(keepalive = false): Promise<void> {
    ++this.epoch; ++this.captureEpoch; clearTimeout(this.timer); this.timer = undefined;
    this.track?.stop(); this.track = undefined;
    const room = this.room; const session = this.session;
    this.room = undefined; this.session = undefined;
    // Do not await network work before stopping physical capture.
    const closing = session ? this.api.close(session.session_id, keepalive).catch(() => {}) : Promise.resolve();
    try { await room?.disconnect(); } finally { await closing; this.changed('انتهت الجلسة'); }
  }
}
