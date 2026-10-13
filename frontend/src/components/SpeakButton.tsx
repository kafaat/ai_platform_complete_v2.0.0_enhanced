// SpeakButton — زرّ استماع (TTS). يحوّل نصّاً عربيّاً إلى صوت يمنيّ عبر
// /tts/synthesize ويشغّله في المتصفّح. قيمة وصوليّة: قراءة التوصيات/التنبيهات
// لأمّيّي القراءة وضعاف البصر. صدق: تعذّر التوليد لا يُعطّل الواجهة (الزرّ يعود).
import { useEffect, useRef, useState } from "react";
import { Volume2, Loader2, Square } from "lucide-react";
import { synthesizeSpeech } from "../services/api";

export default function SpeakButton({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [failedText, setFailedText] = useState<string | null>(null);
  const unavailable = failedText === text;
  const generationRef = useRef(0);
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
    generationRef.current += 1;
    audioRef.current?.pause();
    cleanup();
    setLoading(false);
    setPlaying(false);
    setFailedText(null);
    return () => {
      generationRef.current += 1;
      audioRef.current?.pause();
      cleanup();
    };
  }, [text]);

  const speak = async () => {
    if (playing) {
      generationRef.current += 1;
      audioRef.current?.pause();
      cleanup();
      setPlaying(false);
      return;
    }
    if (!text.trim() || loading) return;
    setFailedText(null);
    setLoading(true);
    const generation = ++generationRef.current;
    try {
      const blob = await synthesizeSpeech(text);
      if (generation !== generationRef.current) return;
      cleanup();
      const url = URL.createObjectURL(blob);
      urlRef.current = url;
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => {
        if (generation !== generationRef.current) return;
        setPlaying(false);
        cleanup();
      };
      audio.onerror = () => {
        if (generation !== generationRef.current) return;
        setPlaying(false);
        setFailedText(text);
        cleanup();
      };
      await audio.play();
      if (generation !== generationRef.current) {
        audio.pause();
        return;
      }
      setPlaying(true);
    } catch {
      if (generation !== generationRef.current) return;
      cleanup();
      setPlaying(false);
      setFailedText(text);
    } finally {
      if (generation === generationRef.current) setLoading(false);
    }
  };

  return (
    <button
      type="button"
      onClick={speak}
      title={unavailable ? "الصوت غير متاح؛ اقرأ التوصية المكتوبة" : "استماع"}
      aria-label={
        unavailable
          ? "الصوت غير متاح؛ اقرأ التوصية المكتوبة"
          : playing
            ? "إيقاف الاستماع"
            : "استماع"
      }
      className={
        className ??
        "inline-flex items-center gap-1 text-xs text-slate-400 hover:text-emerald-400"
      }
    >
      {loading ? (
        <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
      ) : playing ? (
        <Square className="w-4 h-4" aria-hidden="true" />
      ) : (
        <Volume2 className="w-4 h-4" aria-hidden="true" />
      )}
      <span aria-live="polite">
        {unavailable
          ? "الصوت غير متاح؛ اقرأ النص"
          : playing
            ? "إيقاف"
            : "استماع"}
      </span>
    </button>
  );
}
