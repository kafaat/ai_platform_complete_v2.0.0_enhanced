// SpeakButton — زرّ استماع (TTS). يحوّل نصّاً عربيّاً إلى صوت يمنيّ عبر
// /tts/synthesize ويشغّله في المتصفّح. قيمة وصوليّة: قراءة التوصيات/التنبيهات
// لأمّيّي القراءة وضعاف البصر. صدق: تعذّر التوليد لا يُعطّل الواجهة (الزرّ يعود).
import { useEffect, useRef, useState } from 'react';
import { Volume2, Loader2, Square } from 'lucide-react';
import { synthesizeSpeech } from '../services/api';

export default function SpeakButton({ text, className }: { text: string; className?: string }) {
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);

  // إلغاء عنوان الـBlob وتصفير المراجع — يتفادى تراكم blobs في الجلسات الطويلة.
  const cleanup = () => {
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
    audioRef.current = null;
  };

  useEffect(() => {
    // تنظيف عند إزالة المكوّن.
    return () => {
      audioRef.current?.pause();
      cleanup();
    };
  }, []);

  const speak = async () => {
    if (playing) {
      audioRef.current?.pause();
      cleanup();
      setPlaying(false);
      return;
    }
    if (!text.trim() || loading) return;
    setLoading(true);
    try {
      const blob = await synthesizeSpeech(text);
      cleanup();
      const url = URL.createObjectURL(blob);
      urlRef.current = url;
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => { setPlaying(false); cleanup(); };
      audio.onerror = () => { setPlaying(false); cleanup(); };
      await audio.play();
      setPlaying(true);
    } catch {
      // تعذّر التوليد الصوتيّ — نتجاهل بهدوء (لا نُعطّل التجربة).
      cleanup();
      setPlaying(false);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      type="button"
      onClick={speak}
      title="استماع"
      aria-label={playing ? 'إيقاف الاستماع' : 'استماع'}
      className={className ?? 'inline-flex items-center gap-1 text-xs text-slate-400 hover:text-emerald-400'}
    >
      {loading ? (
        <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
      ) : playing ? (
        <Square className="w-4 h-4" aria-hidden="true" />
      ) : (
        <Volume2 className="w-4 h-4" aria-hidden="true" />
      )}
      {playing ? 'إيقاف' : 'استماع'}
    </button>
  );
}
