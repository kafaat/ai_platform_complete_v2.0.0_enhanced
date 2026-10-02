// SpeakButton — زرّ استماع (TTS). يحوّل نصّاً عربيّاً إلى صوت يمنيّ عبر
// /tts/synthesize ويشغّله في المتصفّح. قيمة وصوليّة: قراءة التوصيات/التنبيهات
// لأمّيّي القراءة وضعاف البصر. صدق: تعذّر التوليد لا يُعطّل الواجهة (الزرّ يعود)، وسببُه
// يُعرض بلغة المزارع (رفضُ سياسة البيانات · انتهاء الجلسة · الخدمة) بدل أن يُبتلَع بصمت.
import { useEffect, useRef, useState } from 'react';
import { Volume2, Loader2, Square } from 'lucide-react';
import { synthesizeSpeech } from '../services/api';
import { ttsErrorMessage } from '../lib/fieldHealthSpeech';

export default function SpeakButton({
  text,
  className,
  label = 'استماع',
  disabled = false,
}: {
  text: string;
  className?: string;
  label?: string;
  disabled?: boolean;
}) {
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
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
    if (!text.trim() || loading || disabled) return;
    setErrorText(null);
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
    } catch (err) {
      // تعذّر التوليد الصوتيّ — الواجهة تبقى، والسببُ يُعرض (لا يُبتلَع).
      cleanup();
      setPlaying(false);
      setErrorText(await ttsErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={speak}
        disabled={disabled}
        title={label}
        aria-label={playing ? 'إيقاف الاستماع' : label}
        className={className ?? 'inline-flex items-center gap-1 text-xs text-slate-400 hover:text-emerald-400'}
      >
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
        ) : playing ? (
          <Square className="w-4 h-4" aria-hidden="true" />
        ) : (
          <Volume2 className="w-4 h-4" aria-hidden="true" />
        )}
        {playing ? 'إيقاف' : label}
      </button>
      {errorText && (
        <span role="status" className="text-xs text-amber-600">
          {errorText}
        </span>
      )}
    </span>
  );
}
